import json

from fakes import ScriptedLLM, reasoning_handler
from incident_investigator.engine import RunResult
from incident_investigator.evaluation.baseline import SingleAgentBaseline
from incident_investigator.evaluation.metrics import GroundTruth, _service_matches, aggregate, grade, load_ground_truth
from incident_investigator.evaluation.runner import run_evaluation
from incident_investigator.scenarios import load_scenario, scenario_ids


def test_dataset_has_required_coverage():
    ids = scenario_ids()
    assert len(ids) >= 10
    truths = [load_ground_truth(i) for i in ids]
    tags = {t for gt in truths for t in gt.tags}
    assert {"tool_failure", "conflicting_evidence", "misleading_deploy"} <= tags
    assert sum(gt.expected_inconclusive for gt in truths) >= 1
    for gt in truths:
        sc = load_scenario(gt.incident_id)
        all_ids = {r["id"] for key in ("logs", "metrics", "changes", "past_incidents") for r in sc.data[key]}
        all_ids |= {r["id"] for r in sc.data["topology"]["edges"] + sc.data["topology"]["health"]}
        assert all(i in all_ids for g in gt.key_evidence + gt.misleading_evidence for i in g)
        assert gt.expected_inconclusive or (gt.root_cause_services and gt.root_cause_categories)


def test_service_matching():
    assert _service_matches("auth-service", ["auth-service"])
    assert _service_matches("auth-service (TLS listener)", ["auth-service"])
    assert not _service_matches("auth-service-v2", ["auth-service"])
    assert not _service_matches("payment-service -> payments-db", ["payment-service", "payments-db"])


def test_baseline_uses_same_tools_and_policy(settings, s01):
    llm = ScriptedLLM()
    result = SingleAgentBaseline(llm, settings).investigate(s01)
    assert result.system == "baseline" and result.report.system == "baseline"
    assert result.tool_stats["tool_calls"] == 2
    assert result.usage["by_role"].keys() == {"baseline"}
    assert result.report.status == "conclusive"


def test_baseline_invalid_output_degrades_to_inconclusive(settings, s01):
    result = SingleAgentBaseline(ScriptedLLM({"baseline": lambda m, t: "nonsense"}), settings).investigate(s01)
    assert result.report.status == "inconclusive" and result.state["termination_reason"] == "agent_output_invalid"


def _result(report_status="conclusive", service="checkout-service", category="deployment_regression"):
    from incident_investigator.schemas import ConclusionDecision, Hypothesis, IncidentReport
    h = Hypothesis(id="H1", service=service, category=category, mechanism="m", confidence=0.9, supporting_evidence=["C09"])
    report = IncidentReport(incident_id="S01", system="multi_agent", model="m", status=report_status, status_reason="r",
                            decision=ConclusionDecision(status=report_status, reasons=["r"]), confidence=0.9, summary="s", root_cause=h if report_status == "conclusive" else None,
                            ranked_hypotheses=[h], observed_facts=[], assumptions=[], inferred_conclusions=[],
                            remediation=[], open_questions=[], data_gaps=[], termination_reason="x")
    return RunResult(system="multi_agent", incident_id="S01", report=report, usage={"llm_calls": 3, "prompt_tokens": None},
                     tool_stats={"tool_calls": 4}, citations={"valid": 3, "invalid": 1}, latency_s=1.0, evidence_ids=["C09"])


def test_grading_rules():
    truth = GroundTruth(incident_id="S01", root_cause_services=["checkout-service"], root_cause_categories=["deployment_regression"],
                        key_evidence=[["C09"], ["L0001", "L0002"]], decoy_hypotheses=[{"service": "payments-db", "category": "resource_exhaustion"}])
    row = grade(_result(), truth)
    assert row["correct"] and row["top3"] and row["citation_validity"] == 0.75 and row["key_evidence_cited"] == 0.5
    assert row["prompt_tokens"] is None  # unreported usage is never turned into a number
    assert not grade(_result("inconclusive"), truth)["correct"]  # right lead, but abstained
    misled = grade(_result(service="payments-db", category="resource_exhaustion"), truth)
    assert not misled["correct"] and misled["misled"]
    inconclusive_truth = GroundTruth(incident_id="S10", expected_inconclusive=True)
    assert grade(_result("inconclusive"), inconclusive_truth)["correct"]
    assert not grade(_result(), inconclusive_truth)["correct"]


def test_errored_run_is_graded_wrong_and_counted():
    truth = GroundTruth(incident_id="S01", root_cause_services=["x"], root_cause_categories=["other"])
    bad = RunResult(system="baseline", incident_id="S01", report=None, usage={}, tool_stats={}, citations={},
                    latency_s=0.1, evidence_ids=[], error="LLMError: boom")
    rows = [grade(bad, truth)]
    summary = aggregate(rows)
    assert summary["baseline"]["errored_runs"] == 1 and summary["baseline"]["accuracy"] == 0.0


def test_runner_end_to_end_offline(settings, tmp_path):
    llm = ScriptedLLM({"reasoning": reasoning_handler(service="checkout-service")})
    summary = run_evaluation(systems=["multi_agent", "baseline"], scenario_ids=["S01", "S10"], repeats=1,
                             client=llm, settings=settings, out_dir=tmp_path, log=lambda s: None)
    assert set(summary["systems"]) == {"multi_agent", "baseline"}
    assert summary["systems"]["multi_agent"]["runs"] == 2
    assert (tmp_path / "summary.md").read_text(encoding="utf-8").startswith("# Evaluation summary")
    rows = json.loads((tmp_path / "rows.json").read_text(encoding="utf-8"))
    assert {r["incident_id"] for r in rows} == {"S01", "S10"}
    assert (tmp_path / "runs" / "S01_multi_agent_r1.md").exists()
