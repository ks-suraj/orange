"""Reasoning agent: builds and ranks competing root-cause hypotheses from all evidence."""

from __future__ import annotations

from ..schemas import HypothesisAnalysis, RootCauseCategory
from ..state import InvestigationState, render_analysis, render_critique
from .base import Agent

CATEGORIES = ", ".join(c.value for c in RootCauseCategory)


class ReasoningAgent(Agent):
    role = "reasoning"
    output_schema = HypothesisAnalysis
    instructions = f"""
You are the reasoning specialist in a production incident investigation. You receive the specialists'
findings and the full evidence ledger. Develop 2-4 COMPETING root-cause hypotheses and rank them.

For each hypothesis give: the single service or component where the fault ORIGINATES (an exact name from
the data, not where symptoms are loudest), a category ({CATEGORIES}), the causal mechanism, supporting
evidence ids, contradicting evidence ids, assumptions you rely on, and a confidence in [0, 1].

Reason explicitly about:
- temporal precedence: a cause must precede its effects; compare onset times precisely;
- propagation: callers of a failing dependency also fail, so trace errors to where they originate;
- coincidence: a change near onset is only a cause if its content plausibly explains the symptoms;
- conflicting signals: explain them or lower your confidence;
- data gaps: if key data could not be retrieved, confidence must reflect that.
Confidences are your honest degree of belief; they need not sum to 1, but a well-supported leading
hypothesis should be clearly separated from the alternatives, and if nothing is well supported every
confidence should be low. If a critique is provided, address each point in response_to_critique.
Cite only ids that appear in the evidence ledger. Do not list the same id as both supporting and
contradicting one hypothesis.
Be concise: mechanism in at most 3 sentences, the most direct evidence ids (usually no more than 10 per
list), at most 4 assumptions per hypothesis, reasoning in at most 8 sentences.
"""

    def analyze(self, state: InvestigationState) -> HypothesisAnalysis:
        user = (
            f"INCIDENT\n{state.brief.render()}\n\n"
            f"SPECIALIST FINDINGS\n{state.findings_digest()}\n\n"
            f"EVIDENCE LEDGER (id and content of every record retrieved)\n{state.ledger.digest()}\n\n"
        )
        if state.analysis is not None:
            user += f"YOUR PREVIOUS ANALYSIS\n{render_analysis(state.analysis)}\n\n"
        if state.critique is not None:
            user += f"CRITIQUE OF THE PREVIOUS ANALYSIS\n{render_critique(state.critique)}\n\n"
        user += "Produce the ranked hypothesis analysis."
        return self.complete(user)
