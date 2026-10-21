"""Render an IncidentReport as Markdown."""

from __future__ import annotations

from .schemas import IncidentReport


def _ids(ids: list[str]) -> str:
    return f" `{', '.join(ids)}`" if ids else ""


def report_to_markdown(r: IncidentReport) -> str:
    out = [
        f"# Incident report {r.incident_id}",
        "",
        f"- **Status:** {r.status.upper()} ({r.status_reason})",
        f"- **System:** {r.system} · **Model:** {r.model} · **Stopped because:** {r.termination_reason}",
    ]
    if r.root_cause:
        h = r.root_cause
        out.append(f"- **Root cause:** `{h.service}` - {h.category.value} (confidence {h.confidence:.2f})")
    d = r.decision
    out += ["", "## Summary", r.summary, "", "## Conclusion decision"]
    out += [f"- {reason}" for reason in d.reasons]
    if d.top_hypothesis:
        share = f"{d.contradiction_share:.0%}" if d.contradiction_share is not None else "n/a"
        out.append(f"- Criteria: top `{d.top_hypothesis}` confidence {d.top_confidence:.2f}, margin {d.margin_over_runner_up:.2f}, "
                   f"{len(d.verified_support)} verified supporting / {len(d.contradicting_evidence)} contradicting items "
                   f"({share} contradicting); {len(d.blocking_objections)} evidence-backed material critic objection(s), "
                   f"{d.non_blocking_objections} non-blocking")
    out += [f"  - objection: {o}" for o in d.blocking_objections]
    out += ["", "## Ranked hypotheses"]
    if not r.ranked_hypotheses:
        out.append("_None produced._")
    for i, h in enumerate(r.ranked_hypotheses, 1):
        out += [
            f"{i}. **{h.service}** - {h.category.value} (confidence {h.confidence:.2f})",
            f"   - Mechanism: {h.mechanism}",
            f"   - Supporting evidence:{_ids(h.supporting_evidence) or ' none'}",
            f"   - Contradicting evidence:{_ids(h.contradicting_evidence) or ' none'}",
        ]
        if h.assumptions:
            out.append(f"   - Assumptions: {'; '.join(h.assumptions)}")
    sections = [
        ("Observed facts", [f"{f.statement}{_ids(f.evidence_ids)}" for f in r.observed_facts]),
        ("Assumptions", r.assumptions),
        ("Inferred conclusions", [f"{c.statement} (confidence {c.confidence:.2f}){_ids(c.evidence_ids)}" for c in r.inferred_conclusions]),
        ("Remediation", [f"**{m.priority}** - {m.action}" + (f" _({m.rationale})_" if m.rationale else "") for m in r.remediation]),
        ("Open questions", r.open_questions),
        (f"Data gaps and tool failures ({len(r.data_gaps)} shown, {r.data_gaps_total} reported)", r.data_gaps),
    ]
    for title, items in sections:
        out += ["", f"## {title}"] + ([f"- {i}" for i in items] if items else ["_None._"])
    return "\n".join(out) + "\n"
