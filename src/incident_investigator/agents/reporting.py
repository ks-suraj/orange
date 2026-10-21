"""Reporting agent, the deterministic conclusion decision, and data-gap consolidation.

The conclusion (conclusive / inconclusive) is decided by `decide_conclusion` from explicit criteria
before the reporting agent runs; the agent is told the determination and explains it.
"""

from __future__ import annotations

import re
from collections import Counter

from ..config import InvestigationSettings
from ..schemas import ConclusionDecision, Critique, Hypothesis, IncidentBrief, IncidentReport, ReportDraft
from ..state import InvestigationState, render_analysis, render_critique
from .base import Agent

REPORT_RULES = """
Keep three kinds of statement strictly separate:
- observed_facts: what the data directly shows; each cites the evidence ids that show it.
- assumptions: things taken as true without direct evidence (e.g. "the health check does not exercise TLS").
- inferred_conclusions: conclusions reasoned from the facts, with evidence ids and a confidence.
Remediation must follow from the evidence: immediate mitigation, short_term fix and long_term prevention.
Be concise: summary in at most 6 sentences; at most 10 observed_facts, 6 assumptions, 6
inferred_conclusions, 8 remediation items and 6 open_questions, each one or two sentences.
"""

# Objections whose cited evidence counts against the leading hypothesis.
CONTRADICTION_ISSUES = {"ignored_contradiction", "alternative_not_ruled_out"}
# Objections whose cited evidence is disputed as support for the leading hypothesis.
DISPUTED_SUPPORT_ISSUES = {"misread_evidence", "unsupported_claim"}


class ReportingAgent(Agent):
    role = "reporting"
    output_schema = ReportDraft
    instructions = (
        """
You are the reporting specialist. Write the final incident report from the investigation record. Do not
introduce new hypotheses or evidence; report what the investigation established and how certain it is.

The SYSTEM DETERMINATION (conclusive or inconclusive) has already been made from explicit criteria:
the leading hypothesis's confidence, its verified supporting evidence, its margin over the runner-up, and
the share of contradicting evidence (including evidence-backed critic objections). Do not contradict it.
- If conclusive: state the root cause, and record remaining caveats as assumptions or open_questions.
- If inconclusive: explain which criteria were not met, give the leading candidates without asserting a
  cause, recommend safe mitigations, and list the checks that would settle it in open_questions.
"""
        + REPORT_RULES
    )

    def write(self, state: InvestigationState, data_gaps: list[str], decision: ConclusionDecision) -> ReportDraft:
        user = (
            f"INCIDENT\n{state.brief.render()}\n\n"
            f"SYSTEM DETERMINATION: {decision.status.upper()} - {'; '.join(decision.reasons)}\n\n"
            f"FINAL HYPOTHESIS ANALYSIS (ranked)\n{render_analysis(state.analysis)}\n\n"
            f"FINAL CRITIQUE\n{render_critique(state.critique)}\n\n"
            f"SPECIALIST FINDINGS\n{state.findings_digest()}\n\n"
            f"EVIDENCE LEDGER\n{state.ledger.digest()}\n\n"
            "DATA GAPS AND TOOL FAILURES\n" + ("\n".join(f"- {g}" for g in data_gaps) or "none") + "\n\n"
            f"The investigation stopped because: {state.termination_reason}.\nWrite the report."
        )
        return self.complete(user)


def decide_conclusion(hypotheses: list[Hypothesis], critique: Critique | None, cfg: InvestigationSettings) -> ConclusionDecision:
    """Decide conclusive vs inconclusive from explicit, evidence-based criteria.

    Critic objections act only through evidence: a material objection against the leading hypothesis that
    cites verified evidence either adds that evidence to the contradiction set (contradiction /
    alternative objections) or removes it from the verified support (misread / unsupported objections).
    An objection without verified evidence, a minor one, or one about another hypothesis is recorded but
    does not change the outcome. Critic approval does not bypass any criterion.
    """
    if not hypotheses:
        return ConclusionDecision(status="inconclusive", reasons=["no root-cause hypothesis was produced"])
    top = hypotheses[0]
    contradictions = list(dict.fromkeys(top.contradicting_evidence))
    disputed: list[str] = []
    blocking: list[str] = []
    non_blocking = 0
    for issue in critique.issues if critique else []:
        targets_top = issue.hypothesis_id in (None, top.id)
        kind = issue.issue
        relevant = kind in CONTRADICTION_ISSUES | DISPUTED_SUPPORT_ISSUES
        if not (targets_top and relevant and issue.severity == "material" and issue.evidence_ids):
            non_blocking += 1
            continue
        blocking.append(f"{kind}: {issue.detail[:160]} [{', '.join(issue.evidence_ids)}]")
        target = contradictions if kind in CONTRADICTION_ISSUES else disputed
        target.extend(e for e in issue.evidence_ids if e not in target)
    support = [e for e in dict.fromkeys(top.supporting_evidence) if e not in contradictions and e not in disputed]
    weighed = len(support) + len(contradictions)
    share = len(contradictions) / weighed if weighed else 0.0
    margin = top.confidence - hypotheses[1].confidence if len(hypotheses) > 1 else top.confidence

    reasons = []
    if top.confidence < cfg.inconclusive_threshold:
        reasons.append(f"top hypothesis confidence {top.confidence:.2f} is below {cfg.inconclusive_threshold:.2f}")
    if len(support) < cfg.min_supporting_evidence:
        reasons.append(f"{len(support)} verified, undisputed supporting evidence item(s); {cfg.min_supporting_evidence} required")
    if margin < cfg.min_confidence_margin:
        reasons.append(f"top two hypotheses are not separated (margin {margin:.2f} < {cfg.min_confidence_margin:.2f})")
    if share > cfg.max_contradiction_share:
        reasons.append(f"contradicting evidence is {share:.0%} of the weighed evidence (max {cfg.max_contradiction_share:.0%})")
    status = "inconclusive" if reasons else "conclusive"
    if not reasons:
        reasons.append(f"confidence {top.confidence:.2f}, margin {margin:.2f}, {len(support)} verified supporting and "
                       f"{len(contradictions)} contradicting evidence items ({share:.0%})")
    return ConclusionDecision(
        status=status,
        reasons=reasons,
        top_hypothesis=f"{top.service} / {top.category.value}",
        top_confidence=top.confidence,
        margin_over_runner_up=round(margin, 3),
        verified_support=support,
        contradicting_evidence=contradictions,
        contradiction_share=round(share, 3),
        blocking_objections=blocking,
        non_blocking_objections=non_blocking,
    )


_GAP_STOPWORDS = {
    "the", "and", "was", "were", "not", "for", "from", "that", "this", "with", "are", "but", "any", "all", "its",
    "has", "had", "have", "only", "could", "can", "into", "via", "than", "which", "what", "whether", "been",
    "no", "so", "is", "of", "to", "in", "on", "or", "a", "an", "be", "it", "as", "at", "by",
}


def _gap_tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+(?:[-_.][a-z0-9]+)*", text.lower()) if w not in _GAP_STOPWORDS and len(w) > 2}


def _similar(a: set[str], b: set[str]) -> bool:
    if not a or not b:
        return False
    inter = len(a & b)
    return inter / len(a | b) >= 0.5 or inter / min(len(a), len(b)) >= 0.75


def consolidate_gaps(tool_notes: list[str], agent_gaps: list[str], limit: int) -> tuple[list[str], int]:
    """Deduplicate data gaps and cap the list, summarising whatever is omitted.

    Tool failures observed by the executor come first (they are facts about the investigation). Agent-reported
    gaps are clustered by word overlap; clusters reported by several agents rank first. Anything beyond the
    limit is replaced by one line naming how many items were omitted and what they mostly concern.
    Returns (gaps to show, total number of raw gap entries).
    """
    total = len(tool_notes) + len(agent_gaps)
    tool = list(dict.fromkeys(tool_notes))
    clusters: list[dict] = []
    for i, gap in enumerate(agent_gaps):
        tokens = _gap_tokens(gap)
        for c in clusters:
            if _similar(tokens, c["tokens"]):
                c["count"] += 1
                c["tokens"] |= tokens
                break
        else:
            clusters.append({"text": gap.strip(), "tokens": set(tokens), "count": 1, "order": i})
    clusters.sort(key=lambda c: (-c["count"], c["order"]))

    room = max(0, limit - 1)  # keep one slot for the omission summary if needed
    if len(tool) + len(clusters) <= limit:
        shown_tool, shown, omitted = tool, clusters, []
    else:
        shown_tool = tool[:room]
        shown = clusters[: max(0, room - len(shown_tool))]
        omitted = clusters[len(shown):]
    lines = list(shown_tool) + [c["text"] + (f" (reported {c['count']}x)" if c["count"] > 1 else "") for c in shown]
    dropped_tool = len(tool) - len(shown_tool)
    if omitted or dropped_tool:
        words = Counter(w for c in omitted for w in c["tokens"]).most_common(6)
        about = ", ".join(w for w, _ in words) or "tool failures"
        n = sum(c["count"] for c in omitted) + dropped_tool
        lines.append(f"{n} further gap report(s) in {len(omitted) + dropped_tool} group(s) omitted here (mostly about: {about}); "
                     "the full list is in the run record.")
    return lines, total


def assemble_report(
    *,
    system: str,
    model: str,
    brief: IncidentBrief,
    hypotheses: list[Hypothesis],
    draft: ReportDraft,
    decision: ConclusionDecision,
    data_gaps: list[str],
    data_gaps_total: int,
    termination_reason: str,
) -> IncidentReport:
    facts = [f for f in draft.observed_facts if f.evidence_ids]
    unverified = [f"(unverified - no valid evidence cited) {f.statement}" for f in draft.observed_facts if not f.evidence_ids]
    return IncidentReport(
        incident_id=brief.id,
        system=system,
        model=model,
        status=decision.status,
        status_reason="; ".join(decision.reasons),
        decision=decision,
        confidence=hypotheses[0].confidence if hypotheses else 0.0,
        summary=draft.summary,
        root_cause=hypotheses[0] if decision.status == "conclusive" else None,
        ranked_hypotheses=hypotheses,
        observed_facts=facts,
        assumptions=draft.assumptions + unverified,
        inferred_conclusions=draft.inferred_conclusions,
        remediation=draft.remediation,
        open_questions=draft.open_questions,
        data_gaps=data_gaps,
        data_gaps_total=data_gaps_total,
        termination_reason=termination_reason,
    )


def fallback_draft(reason: str) -> ReportDraft:
    return ReportDraft(summary=f"Report generation failed ({reason}); see hypotheses, decision and data gaps.")
