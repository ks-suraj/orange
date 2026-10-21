"""Single-agent baseline: one LLM agent with all five tools and the same model, limits and output policy.

Fairness constraints relative to the multi-agent system:
- same model and provider settings, same tools and fault injection;
- the same total tool-call budget (INV_MAX_TOTAL_TOOL_CALLS) and repair attempts;
- the same hypothesis schema, citation validation and conclusive/inconclusive policy.
"""

from __future__ import annotations

import time

from ..agents.base import EVIDENCE_RULES, Agent, AgentOutputError, sanitize_citations
from ..agents.reasoning import CATEGORIES
from ..agents.reporting import REPORT_RULES, assemble_report, consolidate_gaps, decide_conclusion
from ..config import Settings
from ..engine import RunResult
from ..llm_client import LLMClient, LLMError, MeteredLLM, UsageMeter
from ..scenarios import Scenario
from ..schemas import BaselineReport
from ..state import InvestigationState
from ..tools import ALL_TOOLS, ToolExecutor, build_tools


class BaselineAgent(Agent):
    role = "baseline"
    output_schema = BaselineReport
    instructions = (
        f"""
You are an experienced on-call engineer investigating a production incident on your own. You have all the
tools: logs (query_logs), metrics (query_metrics), change history (get_change_history), the dependency
graph with health checks (get_dependencies) and past incidents (search_past_incidents).

Investigate until you can explain the incident or the budget runs out, then write the final report.
Include 2-4 competing root-cause hypotheses, best first, each with the single service or component where
the fault ORIGINATES, a category ({CATEGORIES}), mechanism, supporting and contradicting evidence ids,
assumptions and an honest confidence in [0, 1]. Consider temporal precedence, failure propagation along
dependencies, coincidental changes, conflicting signals and data gaps. Whether the report is conclusive is
decided afterwards by the same explicit criteria used for every system (confidence, verified support,
margin over the runner-up, share of contradicting evidence), so state confidences and contradictions honestly.
"""
        + EVIDENCE_RULES
        + REPORT_RULES
    )


class SingleAgentBaseline:
    system_name = "baseline"

    def __init__(self, client: LLMClient, settings: Settings):
        self.client = client
        self.settings = settings
        self.cfg = settings.investigation

    def investigate(self, scenario: Scenario) -> RunResult:
        started = time.perf_counter()
        cfg = self.cfg
        meter = UsageMeter()
        state = InvestigationState(brief=scenario.brief)
        executor = ToolExecutor(build_tools(), scenario.data, state.ledger, faults=scenario.faults,
                                max_retries=cfg.max_tool_retries, max_calls=cfg.max_total_tool_calls)
        agent = BaselineAgent(MeteredLLM(self.client, meter, "baseline"), cfg, state.log)
        user = (
            f"INCIDENT\n{scenario.brief.render()}\n\n"
            f"You may make at most {cfg.max_total_tool_calls} tool calls in total. Independent queries can be "
            "issued together in one turn."
        )
        try:
            output, used = agent.investigate(user, ALL_TOOLS, executor, cfg.max_total_tool_calls)
            state.termination_reason = "tool_budget_exhausted" if used >= cfg.max_total_tool_calls else "agent_finished"
        except (AgentOutputError, LLMError) as exc:
            # Same degradation as the multi-agent system: no valid output -> inconclusive report.
            if isinstance(exc, LLMError) and exc.fatal:
                raise
            output = BaselineReport(summary=f"Baseline output unavailable: {exc}")
            state.termination_reason = "agent_output_invalid"
        state.record_citations(*sanitize_citations(output, state.ledger))
        output.hypotheses.sort(key=lambda h: h.confidence, reverse=True)
        decision = decide_conclusion(output.hypotheses, None, cfg)  # the baseline has no critic
        data_gaps, gaps_total = consolidate_gaps(executor.failure_notes(), [], cfg.max_reported_gaps)
        report = assemble_report(system=self.system_name, model=self.client.model, brief=scenario.brief,
                                 hypotheses=output.hypotheses, draft=output, decision=decision, data_gaps=data_gaps,
                                 data_gaps_total=gaps_total, termination_reason=state.termination_reason)
        return RunResult(
            system=self.system_name,
            incident_id=scenario.brief.id,
            report=report,
            usage=meter.summary(),
            tool_stats=executor.stats(),
            citations=dict(state.citations),
            latency_s=round(time.perf_counter() - started, 3),
            evidence_ids=state.ledger.ids(),
            state=state.to_dict(),
        )
