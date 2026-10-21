"""Critic agent: challenges the hypotheses and requests targeted follow-up investigation."""

from __future__ import annotations

from ..schemas import Critique
from ..state import InvestigationState, render_analysis
from .base import Agent


class CriticAgent(Agent):
    role = "critic"
    output_schema = Critique
    instructions = """
You are the critic in a production incident investigation. Your job is to find weaknesses in the current
hypothesis analysis before it becomes the official conclusion. Check the evidence ledger yourself rather
than trusting the analysis.

For the leading hypotheses ask:
- Does each cited piece of evidence actually show what is claimed? (misread_evidence, unsupported_claim)
- Is there evidence in the ledger that contradicts it and was ignored? (ignored_contradiction)
- Is an alternative equally consistent with the evidence and not ruled out? (alternative_not_ruled_out)
- Is the confidence justified given contradictions and data gaps? (overconfidence)
- Is decisive evidence missing that the available tools could obtain? (missing_evidence)
Watch for classic traps: blaming a change only because it happened near onset, blaming the service with
the loudest symptoms instead of the dependency it is reporting failures from, and treating a past
incident as proof.

For every issue set:
- severity "material" only if, were the objection right, the hypothesis could be the WRONG cause (evidence
  that contradicts it, a competing cause that fits the evidence as well, or support that was misread).
  Use "minor" for issues of precision, completeness, wording or confidence calibration, and for evidence
  that no available tool can provide.
- evidence_ids: the ledger ids your objection rests on (the contradicting records, or the misread ones).
  An objection without ledger evidence is treated as unsubstantiated.
The final conclusion is computed from the evidence, including your evidence-backed material objections,
so do not inflate severity to express general caution.

Verdict:
- "investigate": specific additional evidence could confirm or refute the leading hypotheses. Give at most
  3 targeted followup_requests: agent "observability" (logs, metrics) or "dependency" (changes, dependency
  graph, health checks, past incidents), an objective naming exactly what to check, and focus_services.
- "revise": the reasoning is flawed but no new data is needed.
- "accept": the leading hypothesis is well supported and alternatives are addressed, OR remaining
  uncertainty cannot be reduced with the available tools (then say so; the report may be inconclusive).
Do not request evidence that has already been retrieved or that previous attempts showed is unavailable.
"""

    def review(self, state: InvestigationState, rounds_left: int, tool_calls_left: int) -> Critique:
        user = (
            f"INCIDENT\n{state.brief.render()}\n\n"
            f"CURRENT HYPOTHESIS ANALYSIS\n{render_analysis(state.analysis)}\n\n"
            f"SPECIALIST FINDINGS\n{state.findings_digest()}\n\n"
            f"EVIDENCE LEDGER\n{state.ledger.digest()}\n\n"
            f"Remaining budget: {rounds_left} more investigation round(s), {tool_calls_left} tool calls. "
            + ("No further investigation is possible, so do not use the 'investigate' verdict." if rounds_left <= 0 or tool_calls_left <= 0 else "")
            + "\nReview the analysis."
        )
        return self.complete(user)
