"""Read-only analysis of a finished evaluation: outcome breakdown, failed decision criteria, per-scenario table.

    python scripts/analyze_results.py results/final

Reads runs/*.json and rows.json; writes analysis.json and analysis.md next to them. Never modifies run records.
"""

from __future__ import annotations

import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

CRITERIA = {
    "confidence": r"confidence .* below",
    "verified_support": r"verified, undisputed supporting",
    "margin": r"not separated",
    "contradiction_share": r"contradicting evidence is",
    "no_hypothesis": r"no root-cause hypothesis",
}


def outcome(row: dict) -> str:
    if row["error"]:
        return "error"
    if row["expected_inconclusive"]:
        return "correct_abstention" if row["status"] == "inconclusive" else "unwarranted_conclusion"
    if row["status"] == "conclusive":
        return "correct_diagnosis" if row["top1_lead"] else "wrong_diagnosis"
    return "abstained_correct_lead" if row["top1_lead"] else "abstained_wrong_lead"


def mean(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.fmean(xs), 4) if xs else None


def main(out_dir: Path) -> None:
    rows = json.loads((out_dir / "rows.json").read_text(encoding="utf-8"))
    runs = {}
    for f in sorted((out_dir / "runs").glob("*.json")):
        runs[f.stem] = json.loads(f.read_text(encoding="utf-8"))

    analysis: dict = {"systems": {}, "per_scenario": defaultdict(dict), "inconclusive_runs": []}
    for system in sorted({r["system"] for r in rows}):
        rs = [r for r in rows if r["system"] == system]
        outcomes = Counter(outcome(r) for r in rs)
        failed = Counter()
        for r in rs:
            run = runs[f"{r['incident_id']}_{system}_r{r['repeat']}"]
            report = run.get("report")
            if not report or report["status"] != "inconclusive":
                continue
            reasons = report["decision"]["reasons"]
            hits = [name for name, pat in CRITERIA.items() if any(re.search(pat, x) for x in reasons)]
            failed.update(hits)
            analysis["inconclusive_runs"].append({
                "run": f"{r['incident_id']}_{system}_r{r['repeat']}",
                "expected_inconclusive": r["expected_inconclusive"],
                "top": f"{r['top_service']}/{r['top_category']}",
                "top_correct": r["top1_lead"],
                "failed_criteria": hits,
                "reasons": reasons,
                "blocking_objections": [o[:240] for o in report["decision"]["blocking_objections"]],
            })
        determinable = [r for r in rs if not r["expected_inconclusive"]]
        analysis["systems"][system] = {
            "runs": len(rs),
            "outcomes": dict(outcomes),
            "accuracy": mean([float(r["correct"]) for r in rs]),
            "top_hypothesis_correct_determinable": mean([float(r["top1_lead"]) for r in determinable]),
            "conclusive_rate": mean([float(r["status"] == "conclusive") for r in rs if not r["error"]]),
            "precision_when_conclusive": mean([float(r["top1_lead"]) for r in determinable if r["status"] == "conclusive"]),
            "failed_criteria_in_inconclusive_runs": dict(failed),
            "mean_rounds": mean([r.get("rounds") for r in rs]),
            "runs_hitting_tool_budget": sum(r["tool_calls"] >= 30 for r in rs),
        }
        for sid in sorted({r["incident_id"] for r in rs}):
            srs = [r for r in rs if r["incident_id"] == sid]
            analysis["per_scenario"][sid][system] = {
                "correct": sum(r["correct"] for r in srs),
                "top_correct": sum(bool(r["top1_lead"]) for r in srs),
                "conclusive": sum(r["status"] == "conclusive" for r in srs),
                "runs": len(srs),
                "outcomes": dict(Counter(outcome(r) for r in srs)),
            }
    (out_dir / "analysis.json").write_text(json.dumps(analysis, indent=2), encoding="utf-8")
    (out_dir / "analysis.md").write_text(render(analysis), encoding="utf-8")
    print(render(analysis))


def render(a: dict) -> str:
    systems = list(a["systems"])
    lines = ["# Outcome analysis", "", "| | " + " | ".join(systems) + " |", "|---|" + "---|" * len(systems)]
    keys = ["accuracy", "top_hypothesis_correct_determinable", "conclusive_rate", "precision_when_conclusive", "mean_rounds", "runs_hitting_tool_budget"]
    for k in keys:
        lines.append(f"| {k} | " + " | ".join(str(a["systems"][s][k]) for s in systems) + " |")
    lines += ["", "## Outcome categories (runs)", "", "| Outcome | " + " | ".join(systems) + " |", "|---|" + "---|" * len(systems)]
    cats = ["correct_diagnosis", "abstained_correct_lead", "abstained_wrong_lead", "wrong_diagnosis", "correct_abstention", "unwarranted_conclusion", "error"]
    for c in cats:
        lines.append(f"| {c} | " + " | ".join(str(a["systems"][s]["outcomes"].get(c, 0)) for s in systems) + " |")
    lines += ["", "## Failed criteria in inconclusive runs", ""]
    for s in systems:
        lines.append(f"- {s}: {a['systems'][s]['failed_criteria_in_inconclusive_runs']}")
    lines += ["", "## Per scenario (correct / top-correct / conclusive, out of runs)", "", "| Scenario | " + " | ".join(systems) + " |", "|---|" + "---|" * len(systems)]
    for sid, by in sorted(a["per_scenario"].items()):
        lines.append(f"| {sid} | " + " | ".join(
            f"{by[s]['correct']}/{by[s]['top_correct']}/{by[s]['conclusive']} of {by[s]['runs']}" if s in by else "-" for s in systems) + " |")
    lines += ["", "## Inconclusive runs", ""]
    for r in a["inconclusive_runs"]:
        lines.append(f"- **{r['run']}** (expected inconclusive: {r['expected_inconclusive']}, top {r['top']}, top correct: {r['top_correct']}): "
                     f"failed {r['failed_criteria']}")
        for o in r["blocking_objections"]:
            lines.append(f"  - objection: {o}")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("results/final"))
