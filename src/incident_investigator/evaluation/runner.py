"""Run both systems over the scenario set and write per-run records plus a summary."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

from ..config import Settings
from ..engine import MultiAgentInvestigator, RunResult
from ..llm_client import LLMClient
from ..render import report_to_markdown
from ..scenarios import load_scenario
from .baseline import SingleAgentBaseline
from .metrics import aggregate, grade, load_ground_truth

SYSTEMS: dict[str, Callable[[LLMClient, Settings], Any]] = {
    "multi_agent": MultiAgentInvestigator,
    "baseline": SingleAgentBaseline,
}


def run_one(system: str, scenario_id: str, client: LLMClient, settings: Settings) -> RunResult:
    scenario = load_scenario(scenario_id)
    investigator = SYSTEMS[system](client, settings)
    started = time.perf_counter()
    try:
        return investigator.investigate(scenario)
    except Exception as exc:  # recorded as a failed run, never silently dropped
        return RunResult(system=system, incident_id=scenario_id, report=None, usage={}, tool_stats={}, citations={},
                         latency_s=round(time.perf_counter() - started, 3), evidence_ids=[],
                         error=f"{type(exc).__name__}: {exc}")


def run_evaluation(
    *,
    systems: list[str],
    scenario_ids: list[str],
    repeats: int,
    client: LLMClient,
    settings: Settings,
    out_dir: Path,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for scenario_id in scenario_ids:
        truth = load_ground_truth(scenario_id)
        for system in systems:
            for rep in range(1, repeats + 1):
                result = run_one(system, scenario_id, client, settings)
                row = grade(result, truth) | {"repeat": rep}
                rows.append(row)
                stem = out_dir / "runs" / f"{scenario_id}_{system}_r{rep}"
                stem.parent.mkdir(parents=True, exist_ok=True)
                stem.with_suffix(".json").write_text(json.dumps(result.to_dict() | {"grade": row}, indent=2, default=str), encoding="utf-8")
                if result.report:
                    stem.with_suffix(".md").write_text(report_to_markdown(result.report), encoding="utf-8")
                log(f"{scenario_id} {system:<11} r{rep}: correct={row['correct']} status={row.get('status')} "
                    f"top={row.get('top_service')}/{row.get('top_category')} tools={row['tool_calls']} "
                    f"tokens={row['total_tokens']} {row['latency_s']:.1f}s" + (f" ERROR {row['error']}" if row['error'] else ""))
    summary = {
        "model": client.model,
        "settings": settings.investigation.model_dump(),
        "reasoning_effort": settings.llm.reasoning_effort,
        "scenarios": scenario_ids,
        "repeats": repeats,
        "systems": aggregate(rows),
    }
    (out_dir / "rows.json").write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    (out_dir / "summary.md").write_text(summary_markdown(summary, rows), encoding="utf-8")
    return summary


def _fmt(v: Any) -> str:
    if v is None:
        return "n/a"
    if isinstance(v, float):
        return f"{v:.3f}" if abs(v) < 10 else f"{v:,.0f}"
    return str(v)


METRIC_LABELS = [
    ("accuracy", "Diagnosis accuracy (all scenarios)"),
    ("accuracy_root_cause_cases", "Accuracy - scenarios with a determinable root cause"),
    ("accuracy_inconclusive_cases", "Accuracy - scenarios that should be inconclusive"),
    ("top1_lead_accuracy", "Top hypothesis correct (ignoring abstention)"),
    ("top3_recall", "Correct cause in top 3"),
    ("misled_rate", "Conclusive on a planted decoy"),
    ("false_inconclusive_rate", "Abstained when a cause was determinable"),
    ("citation_validity", "Citation validity (cited ids that exist)"),
    ("key_evidence_cited", "Key evidence cited in report"),
    ("key_evidence_retrieved", "Key evidence retrieved by tools"),
    ("mean_tool_calls", "Tool calls per run"),
    ("mean_failed_tool_calls", "Failed tool calls per run"),
    ("mean_llm_calls", "LLM calls per run"),
    ("mean_invalid_outputs", "Invalid agent outputs (repair attempts) per run"),
    ("mean_prompt_tokens", "Prompt tokens per run"),
    ("mean_completion_tokens", "Completion tokens per run"),
    ("mean_total_tokens", "Total tokens per run"),
    ("total_cost_usd", "Total cost (USD, provider-reported)"),
    ("mean_latency_s", "Mean latency (s)"),
    ("median_latency_s", "Median latency (s)"),
    ("errored_runs", "Errored runs"),
    ("runs_with_unreported_usage", "Runs with unreported usage"),
]


def summary_markdown(summary: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    systems = list(summary["systems"])
    lines = [
        f"# Evaluation summary - model `{summary['model']}`",
        "",
        f"Scenarios: {len(summary['scenarios'])} × repeats: {summary['repeats']}",
        "",
        "| Metric | " + " | ".join(systems) + " |",
        "|---|" + "---|" * len(systems),
    ]
    for key, label in METRIC_LABELS:
        lines.append(f"| {label} | " + " | ".join(_fmt(summary["systems"][s].get(key)) for s in systems) + " |")
    lines += ["", "## Per-scenario results", "", "| Scenario | System | Rep | Correct | Status | Top hypothesis | Tool calls | Tokens | Latency (s) |",
              "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        top = f"{r.get('top_service')} / {r.get('top_category')}" if r.get("top_service") else "-"
        lines.append(f"| {r['incident_id']} | {r['system']} | {r['repeat']} | {'yes' if r['correct'] else 'no'} | "
                     f"{r.get('status') or 'error'} | {top} | {r['tool_calls']} | {_fmt(r['total_tokens'])} | {r['latency_s']:.1f} |")
    return "\n".join(lines) + "\n"
