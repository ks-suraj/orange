import json

import pytest

from fakes import ScriptedLLM, critic_script, orchestrator_handler, reasoning_handler, reporting_handler, specialist
from incident_investigator.agents import decide_conclusion
from incident_investigator.config import InvestigationSettings
from incident_investigator.engine import MultiAgentInvestigator
from incident_investigator.llm_client import LLMError
from incident_investigator.schemas import Critique, CritiqueIssue, Hypothesis, TaskRequest
from incident_investigator.state import InvestigationState


def run(settings, scenario, **handlers):
    llm = ScriptedLLM(handlers)
    return llm, MultiAgentInvestigator(llm, settings).investigate(scenario)


def test_full_collaboration_with_critic_feedback_loop(settings, s01):
    llm, result = run(settings, s01)
    state = result.state
    assert [t["agent"] for t in state["tasks"]][:2] == ["observability", "dependency"]
    # critic asked for a follow-up in round 1, the orchestrator scheduled it, critic accepted in round 2
    assert len(state["rounds"]) == 2
    assert state["rounds"][0]["critique"]["verdict"] == "investigate"
    assert state["tasks"][2]["round"] == 2 and state["tasks"][2]["status"] == "done"
    assert state["termination_reason"] == "critic_accepted"
    assert llm.count("reasoning") == 2 and llm.count("reporting") == 1
    assert result.report.status == "conclusive" and result.report.root_cause.service == "checkout-service"


def test_hallucinated_citations_are_removed_and_counted(settings, s01):
    _, result = run(settings, s01)
    report = result.report
    assert result.citations["invalid"] > 0  # L9999, X123, NOPE1 from the scripted model
    assert all(e in result.evidence_ids for h in report.ranked_hypotheses for e in h.supporting_evidence)
    # a "fact" whose only citation was invalid is demoted to an explicit unverified assumption
    assert any(a.startswith("(unverified") for a in report.assumptions)
    assert all(f.evidence_ids for f in report.observed_facts)


def test_first_round_tasks_run_in_parallel(settings, s01):
    _, result = run(settings, s01)
    waves = [e for e in result.state["trace"] if e["event"] == "wave"]
    assert waves[0]["tasks"] == ["T1", "T2"]


def test_task_dependencies_run_in_later_wave(settings, s01):
    def plan(messages, tools):
        if "TASK: plan" in messages[1]["content"]:
            return json.dumps({"incident_understanding": "x", "tasks": [
                {"key": "a", "agent": "observability", "objective": "find erroring service", "focus_services": ["checkout-service"]},
                {"key": "b", "agent": "dependency", "objective": "changes to it", "depends_on": ["a"]},
            ]})
        return json.dumps({"action": "stop", "rationale": "done"})
    _, result = run(settings, s01, orchestrator=plan, critic=critic_script(["revise"]))
    waves = [e["tasks"] for e in result.state["trace"] if e["event"] == "wave"]
    assert waves == [["T1"], ["T2"]]
    assert result.state["termination_reason"] == "orchestrator_stopped"


def test_max_rounds_terminates_a_critic_that_never_accepts(settings, s01):
    settings.investigation.max_rounds = 2
    _, result = run(settings, s01, critic=critic_script(["investigate"]))
    assert len(result.state["rounds"]) == 2
    assert result.state["termination_reason"] == "max_rounds_reached"


def test_no_new_evidence_stops_loop(settings, s01):
    # The orchestrator continues but schedules nothing new -> a revision-only round, then stop.
    _, result = run(settings, s01, critic=critic_script(["revise"]),
                    orchestrator=lambda m, t: orchestrator_handler()(m, t) if "TASK: plan" in m[1]["content"]
                    else json.dumps({"action": "continue", "rationale": "revise only", "new_tasks": []}))
    assert result.state["termination_reason"] == "no_new_evidence"
    assert len(result.state["rounds"]) == 2


def test_low_confidence_yields_inconclusive(settings, s01):
    _, result = run(settings, s01, reasoning=reasoning_handler(confidence=0.3))
    assert result.report.status == "inconclusive" and result.report.root_cause is None
    assert "below" in result.report.status_reason


def test_reporting_agent_cannot_downgrade_a_well_supported_conclusion(settings, s01):
    # The scripted reporting model asks for "inconclusive"; the decision is made before it runs and stands.
    llm, result = run(settings, s01, reporting=reporting_handler("inconclusive"))
    assert result.report.status == "conclusive"
    assert result.report.decision.verified_support
    reporting_prompt_has_determination = any(e["event"] == "conclusion" for e in result.state["trace"])
    assert reporting_prompt_has_determination


def test_critic_acceptance_does_not_rescue_an_ambiguous_incident(settings, s01):
    # Two near-equal hypotheses: the critic accepts, the reporting model says conclusive, still inconclusive.
    _, result = run(settings, s01, reasoning=reasoning_handler(confidence=0.62, runner_up=0.6),
                    critic=critic_script(["accept"]), reporting=reporting_handler("conclusive"))
    assert result.report.status == "inconclusive" and result.report.root_cause is None
    assert "not separated" in result.report.status_reason


def test_evidence_backed_material_contradictions_force_inconclusive(settings, s01):
    def contradicting(ids):
        return [{"hypothesis_id": "H1", "issue": "ignored_contradiction", "severity": "material",
                 "detail": "these records contradict H1", "evidence_ids": ids[5:12]}]
    _, result = run(settings, s01, critic=critic_script(["accept"], issues=contradicting))
    d = result.report.decision
    assert result.report.status == "inconclusive"
    assert d.contradiction_share > settings.investigation.max_contradiction_share and d.blocking_objections


def test_unsubstantiated_or_minor_objections_do_not_force_inconclusive(settings, s01):
    def cautious(ids):
        return [
            {"hypothesis_id": "H1", "issue": "ignored_contradiction", "severity": "material", "detail": "no ids given", "evidence_ids": ["BOGUS1"]},
            {"hypothesis_id": "H1", "issue": "overconfidence", "severity": "minor", "detail": "lower it", "evidence_ids": ids[:1]},
            {"hypothesis_id": "H2", "issue": "misread_evidence", "severity": "material", "detail": "about H2", "evidence_ids": ids[:2]},
        ]
    _, result = run(settings, s01, critic=critic_script(["revise"], issues=cautious))
    assert result.report.status == "conclusive"
    assert result.report.decision.non_blocking_objections == 3 and not result.report.decision.blocking_objections


def test_data_gaps_in_report_are_capped(settings, s01):
    settings.investigation.max_reported_gaps = 3
    many_gaps = specialist(lambda svcs: [("query_logs", {"service": svcs[-1]})])

    def gappy(messages, tools):
        out = many_gaps(messages, tools)
        if isinstance(out, list):
            return out
        payload = json.loads(out)
        words = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel"]
        payload["data_gaps"] = [f"{w} metrics for {w}-cluster unavailable" for w in words]
        return json.dumps(payload)
    _, result = run(settings, s01, observability=gappy)
    assert len(result.report.data_gaps) == 3 and result.report.data_gaps_total >= 8
    assert "omitted" in result.report.data_gaps[-1]


def test_failed_specialist_task_is_retried_then_recorded(settings, s01):
    _, result = run(settings, s01, dependency=lambda m, t: "garbage")
    dep = [t for t in result.state["tasks"] if t["agent"] == "dependency"][0]
    assert dep["status"] == "failed" and dep["attempts"] == settings.investigation.max_task_attempts
    assert any("failed" in g for g in result.report.data_gaps)
    assert result.report is not None  # the investigation degrades instead of crashing


def test_tool_failures_surface_as_data_gaps(settings):
    from incident_investigator.scenarios import load_scenario
    s08 = load_scenario("S08")  # query_logs always times out for payment-service
    _, result = run(settings, s08, observability=specialist(lambda svcs: [("query_logs", {"service": "payment-service"})]))
    assert any("query_logs(service=payment-service" in g and "timeout" in g for g in result.report.data_gaps)


def test_fatal_provider_error_aborts(settings, s01):
    def boom(messages, tools):
        raise LLMError("HTTP 401: bad key", status=401)
    with pytest.raises(LLMError):
        run(settings, s01, orchestrator=boom)


def test_usage_and_tool_stats_recorded(settings, s01):
    llm, result = run(settings, s01)
    assert result.usage["llm_calls"] == len(llm.calls)
    assert result.usage["prompt_tokens"] == 120 * len(llm.calls)
    assert set(result.usage["by_role"]) >= {"orchestrator", "observability", "dependency", "reasoning", "critic", "reporting"}
    assert result.tool_stats["tool_calls"] > 0


def test_task_graph_rejects_dangling_dependencies(s01):
    state = InvestigationState(brief=s01.brief)
    created = state.add_tasks([TaskRequest(agent="dependency", objective="x", depends_on=["missing", "T99"])], "o", 1, 4)
    assert created[0].depends_on == []
    capped = state.add_tasks([TaskRequest(agent="dependency", objective=str(i)) for i in range(6)], "o", 2, 4)
    assert len(capped) == 4


def _h(conf, n_support=2, contra=(), hid="H1"):
    return Hypothesis(id=hid, service="s", category="config_error", mechanism="m", confidence=conf,
                      supporting_evidence=[f"L{i}" for i in range(n_support)], contradicting_evidence=list(contra))


def _critique(*issues, verdict="revise"):
    return Critique(verdict=verdict, summary="s", issues=[CritiqueIssue(**i) for i in issues])


@pytest.mark.parametrize("hyps, critique, expected", [
    ([], None, "inconclusive"),
    ([_h(0.9)], None, "conclusive"),
    ([_h(0.4)], _critique(verdict="accept"), "inconclusive"),             # approval does not bypass criteria
    ([_h(0.9, n_support=1)], None, "inconclusive"),
    ([_h(0.7), _h(0.68, hid="H2")], None, "inconclusive"),
    ([_h(0.7), _h(0.3, hid="H2")], None, "conclusive"),
    ([_h(0.8, n_support=4, contra=["M1", "M2", "M3"])], None, "inconclusive"),  # 3/7 contradicting
    # one evidence-backed objection against strong support is weighed, not decisive
    ([_h(0.8, n_support=10)], _critique({"hypothesis_id": "H1", "issue": "ignored_contradiction", "severity": "material",
                                          "detail": "d", "evidence_ids": ["M9"]}), "conclusive"),
    # disputed support is removed: 3 supports, 2 disputed as misread -> 1 left
    ([_h(0.8, n_support=3)], _critique({"hypothesis_id": "H1", "issue": "misread_evidence", "severity": "material",
                                         "detail": "d", "evidence_ids": ["L0", "L1"]}), "inconclusive"),
    # material objection without evidence does not count
    ([_h(0.8, n_support=3)], _critique({"hypothesis_id": None, "issue": "alternative_not_ruled_out", "severity": "material",
                                         "detail": "d"}), "conclusive"),
])
def test_decide_conclusion_criteria(hyps, critique, expected):
    assert decide_conclusion(hyps, critique, InvestigationSettings()).status == expected
