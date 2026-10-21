"""Orchestrator agent: plans the investigation and decides whether more evidence is needed."""

from __future__ import annotations

from ..schemas import IncidentBrief, InvestigationPlan, OrchestratorDecision
from ..state import InvestigationState, render_analysis, render_critique
from .base import Agent


class OrchestratorAgent(Agent):
    role = "orchestrator"
    output_schema = InvestigationPlan
    instructions = """
You are the incident commander coordinating a production incident investigation. You do not query
telemetry yourself; you delegate tasks to specialists:
- observability: logs (query_logs) and metrics (query_metrics) to characterise symptoms, error
  signatures, onset times and anomalies;
- dependency: change history (deployments, config changes, feature flags, infra events), the service
  dependency graph with health checks, and past incident postmortems, to find triggering changes and
  propagation paths.
Separate reasoning and critic agents analyse the evidence after each round of tasks.

When PLANNING: list plausible explanations for the alert, then create 2-4 tasks that gather evidence able
to discriminate between them. Give each task a precise objective and focus services. Tasks without
depends_on run in parallel; use depends_on only when a task truly needs another task's findings first.

When DECIDING whether to continue: continue only if specific missing evidence could change the leading
conclusion and budget remains. Turn useful critic requests into precise tasks (you may merge, sharpen or
drop them). Stop when the ranking is well supported, or when further queries cannot reduce the
uncertainty - an inconclusive outcome is acceptable and better than a guess.
"""

    def plan(self, brief: IncidentBrief) -> InvestigationPlan:
        return self.complete(f"TASK: plan the investigation.\n\nINCIDENT\n{brief.render()}", InvestigationPlan)

    def decide(self, state: InvestigationState, rounds_left: int, tool_calls_left: int) -> OrchestratorDecision:
        tasks = "\n".join(
            f"- {t.id} [{t.agent}] {t.status.value}: {t.objective}" for t in state.tasks.values()
        )
        user = (
            f"TASK: decide whether to continue the investigation.\n\nINCIDENT\n{state.brief.render()}\n\n"
            f"TASKS SO FAR\n{tasks}\n\n"
            f"CURRENT HYPOTHESIS ANALYSIS\n{render_analysis(state.analysis)}\n\n"
            f"CRITIQUE\n{render_critique(state.critique)}\n\n"
            f"KNOWN DATA GAPS\n" + ("\n".join(f"- {g}" for g in state.data_gaps()) or "none") + "\n\n"
            f"Remaining budget: {rounds_left} round(s), {tool_calls_left} tool calls."
        )
        return self.complete(user, OrchestratorDecision)
