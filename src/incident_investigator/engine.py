"""Investigation engine: runs the multi-agent collaboration under deterministic limits.

Flow per investigation:
  1. Orchestrator plans tasks (with optional dependencies).
  2. Ready tasks run in parallel waves on the observability / dependency specialists.
  3. Reasoning ranks competing hypotheses; Critic challenges them and may request follow-ups.
  4. Python checks hard stop conditions; otherwise the Orchestrator decides to stop or adds tasks.
  5. Reporting writes the report; Python applies the conclusive/inconclusive policy.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from .agents import (
    AgentOutputError,
    CriticAgent,
    DependencyAgent,
    ObservabilityAgent,
    OrchestratorAgent,
    ReasoningAgent,
    ReportingAgent,
    SpecialistAgent,
    assemble_report,
    sanitize_citations,
)
from .agents.reporting import consolidate_gaps, decide_conclusion, fallback_draft
from .config import Settings
from .llm_client import LLMClient, LLMError, MeteredLLM, UsageMeter
from .scenarios import Scenario
from .schemas import HypothesisAnalysis, IncidentReport, InvestigationPlan, TaskRequest
from .state import InvestigationState, RoundRecord, Task, TaskStatus
from .tools import ToolExecutor, build_tools


@dataclass
class RunResult:
    system: str
    incident_id: str
    report: IncidentReport | None
    usage: dict[str, Any]
    tool_stats: dict[str, Any]
    citations: dict[str, int]
    latency_s: float
    evidence_ids: list[str]
    state: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "system": self.system,
            "incident_id": self.incident_id,
            "error": self.error,
            "latency_s": self.latency_s,
            "usage": self.usage,
            "tool_stats": self.tool_stats,
            "citations": self.citations,
            "report": self.report.model_dump(mode="json") if self.report else None,
            "state": self.state,
        }


def fallback_plan(scenario: Scenario) -> InvestigationPlan:
    """Used only if the orchestrator cannot produce a valid plan: one broad task per specialist."""
    services = scenario.brief.affected_services
    return InvestigationPlan(
        incident_understanding="Fallback plan (orchestrator output unavailable).",
        tasks=[
            TaskRequest(agent="observability", objective="Characterise errors, latency and saturation on the alerting services and their onset times.", focus_services=services),
            TaskRequest(agent="dependency", objective="Find recent changes and map dependencies of the alerting services, including health checks.", focus_services=services),
        ],
    )


class MultiAgentInvestigator:
    system_name = "multi_agent"

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

        def llm(role: str) -> MeteredLLM:
            return MeteredLLM(self.client, meter, role)

        orchestrator = OrchestratorAgent(llm("orchestrator"), cfg, state.log)
        specialists: dict[str, SpecialistAgent] = {
            "observability": ObservabilityAgent(llm("observability"), cfg, state.log),
            "dependency": DependencyAgent(llm("dependency"), cfg, state.log),
        }
        reasoning = ReasoningAgent(llm("reasoning"), cfg, state.log)
        critic = CriticAgent(llm("critic"), cfg, state.log)
        reporter = ReportingAgent(llm("reporting"), cfg, state.log)

        state.plan = self._call(state, "orchestrator", "plan", lambda: orchestrator.plan(scenario.brief)) or fallback_plan(scenario)
        state.add_tasks(state.plan.tasks, "orchestrator", 1, cfg.max_tasks_per_round)
        state.log("orchestrator", "planned", tasks=[t.id for t in state.tasks.values()])

        round_no = 1
        while True:
            before = len(state.ledger)
            ran = self._run_round(state, specialists, executor)
            rec = RoundRecord(number=round_no, task_ids=ran, new_evidence=len(state.ledger) - before)
            state.rounds.append(rec)

            analysis = self._call(state, "reasoning", "analyze", lambda: reasoning.analyze(state))
            if analysis is not None:
                state.analysis = self._clean_analysis(analysis, state)
            rec.analysis = state.analysis

            rounds_left = cfg.max_rounds - round_no
            state.critique = self._call(state, "critic", "review", lambda: critic.review(state, rounds_left, executor.remaining()))
            rec.critique = state.critique
            if state.critique:
                state.record_citations(*sanitize_citations(state.critique, state.ledger))
                state.log("critic", "verdict", verdict=state.critique.verdict, requests=len(state.critique.followup_requests))

            reason = self._hard_stop(state, rec, round_no, executor)
            if reason is None:
                rec.decision = self._call(state, "orchestrator", "decide",
                                          lambda: orchestrator.decide(state, rounds_left, executor.remaining()))
                if rec.decision is None:
                    reason = "orchestrator_unavailable"
                elif rec.decision.action == "stop":
                    reason = "orchestrator_stopped"
                else:
                    created = state.add_tasks(rec.decision.new_tasks, "orchestrator", round_no + 1, cfg.max_tasks_per_round)
                    state.log("orchestrator", "continue", new_tasks=[t.id for t in created])
            if reason:
                state.termination_reason = reason
                state.log("engine", "terminated", reason=reason, round=round_no)
                break
            round_no += 1

        hypotheses = state.analysis.hypotheses if state.analysis else []
        decision = decide_conclusion(hypotheses, state.critique, cfg)
        state.log("engine", "conclusion", status=decision.status, reasons=decision.reasons)
        data_gaps, gaps_total = consolidate_gaps(executor.failure_notes(), state.data_gaps(), cfg.max_reported_gaps)
        draft = self._call(state, "reporting", "write", lambda: reporter.write(state, data_gaps, decision))
        if draft is None:
            draft = fallback_draft("reporting agent output unavailable")
        else:
            state.record_citations(*sanitize_citations(draft, state.ledger))
        report = assemble_report(system=self.system_name, model=self.client.model, brief=scenario.brief,
                                 hypotheses=hypotheses, draft=draft, decision=decision, data_gaps=data_gaps,
                                 data_gaps_total=gaps_total, termination_reason=state.termination_reason or "unknown")
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

    # -- helpers -----------------------------------------------------------------------------

    def _call(self, state: InvestigationState, actor: str, what: str, fn):
        """Run an agent step with bounded retries. Fatal provider errors (auth/billing) propagate."""
        for attempt in range(1, self.cfg.max_task_attempts + 1):
            try:
                return fn()
            except LLMError as exc:
                if exc.fatal:
                    raise
                state.log(actor, f"{what}_failed", attempt=attempt, error=str(exc)[:300])
            except AgentOutputError as exc:
                state.log(actor, f"{what}_failed", attempt=attempt, error=str(exc)[:300])
        return None

    def _run_round(self, state: InvestigationState, specialists: dict[str, SpecialistAgent], executor: ToolExecutor) -> list[str]:
        ran: list[str] = []
        while ready := state.ready_tasks():
            for t in ready:
                t.status = TaskStatus.RUNNING
            state.log("engine", "wave", tasks=[t.id for t in ready])
            with ThreadPoolExecutor(max_workers=self.cfg.parallel_workers) as pool:
                futures = [pool.submit(self._run_task, t, state, specialists[t.agent], executor) for t in ready]
                for f in futures:
                    f.result()  # re-raises fatal errors
            ran += [t.id for t in ready]
        return ran

    def _run_task(self, task: Task, state: InvestigationState, agent: SpecialistAgent, executor: ToolExecutor) -> None:
        while task.attempts < self.cfg.max_task_attempts:
            task.attempts += 1
            try:
                findings = agent.run_task(task, state, executor)
            except LLMError as exc:
                if exc.fatal:
                    task.status = TaskStatus.FAILED
                    task.error = str(exc)
                    raise
                task.error = str(exc)[:300]
            except AgentOutputError as exc:
                task.error = str(exc)[:300]
            else:
                state.record_citations(*sanitize_citations(findings, state.ledger))
                task.findings, task.status, task.error = findings, TaskStatus.DONE, None
                state.log(task.agent, "task_done", task=task.id, tool_calls=task.tool_calls)
                return
            state.log(task.agent, "task_attempt_failed", task=task.id, attempt=task.attempts, error=task.error)
        task.status = TaskStatus.FAILED

    def _clean_analysis(self, analysis: HypothesisAnalysis, state: InvestigationState) -> HypothesisAnalysis:
        state.record_citations(*sanitize_citations(analysis, state.ledger))
        seen: set[str] = set()
        for i, h in enumerate(analysis.hypotheses, 1):
            if h.id in seen:
                h.id = f"H{i}"
            seen.add(h.id)
        analysis.hypotheses.sort(key=lambda h: h.confidence, reverse=True)  # stable: ties keep the agent's order
        return analysis

    def _hard_stop(self, state: InvestigationState, rec: RoundRecord, round_no: int, executor: ToolExecutor) -> str | None:
        if state.critique is not None and state.critique.verdict == "accept":
            return "critic_accepted"
        if round_no >= self.cfg.max_rounds:
            return "max_rounds_reached"
        if executor.remaining() <= 0:
            return "tool_budget_exhausted"
        if round_no > 1 and rec.new_evidence == 0:
            return "no_new_evidence"
        return None
