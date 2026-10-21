"""Deterministic grading against ground truth, and aggregation across runs.

No LLM judge is used. A diagnosis is correct when the report is conclusive and its top hypothesis
names an accepted root-cause component and category; for scenarios whose ground truth is
"inconclusive", it is correct only when the report is inconclusive.
"""

from __future__ import annotations

import json
import re
import statistics
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ..config import DATA_DIR
from ..engine import RunResult
from ..schemas import Hypothesis, IncidentReport, RootCauseCategory


class GroundTruth(BaseModel):
    incident_id: str
    expected_inconclusive: bool = False
    root_cause_services: list[str] = Field(default_factory=list)
    root_cause_categories: list[RootCauseCategory] = Field(default_factory=list)
    summary: str = ""
    key_evidence: list[list[str]] = Field(default_factory=list, description="Groups of ids; citing any id in a group covers it")
    misleading_evidence: list[list[str]] = Field(default_factory=list)
    decoy_hypotheses: list[dict[str, str]] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


def load_ground_truth(incident_id: str, data_dir: Path = DATA_DIR) -> GroundTruth:
    return GroundTruth(**json.loads((data_dir / "ground_truth" / f"{incident_id}.json").read_text(encoding="utf-8")))


def _service_matches(named: str, accepted: list[str]) -> bool:
    """Exact name, or the hypothesis text mentions exactly one accepted component as a whole word."""
    named = named.strip().lower()
    accepted = [a.lower() for a in accepted]
    if named in accepted:
        return True
    mentioned = {a for a in accepted if re.search(rf"(?<![\w-]){re.escape(a)}(?![\w-])", named)}
    return len(mentioned) == 1


def hypothesis_matches(h: Hypothesis, services: list[str], categories: list[RootCauseCategory]) -> bool:
    return _service_matches(h.service, services) and h.category in categories


def cited_ids(report: IncidentReport) -> set[str]:
    ids: set[str] = set()
    for h in report.ranked_hypotheses:
        ids |= set(h.supporting_evidence) | set(h.contradicting_evidence)
    for f in report.observed_facts:
        ids |= set(f.evidence_ids)
    for c in report.inferred_conclusions:
        ids |= set(c.evidence_ids)
    return ids


def _group_coverage(groups: list[list[str]], ids: set[str]) -> float | None:
    if not groups:
        return None
    return sum(any(i in ids for i in g) for g in groups) / len(groups)


def grade(result: RunResult, truth: GroundTruth) -> dict[str, Any]:
    row: dict[str, Any] = {
        "system": result.system,
        "incident_id": result.incident_id,
        "expected_inconclusive": truth.expected_inconclusive,
        "error": result.error,
        "latency_s": result.latency_s,
        "tool_calls": result.tool_stats.get("tool_calls", 0),
        "failed_tool_calls": result.tool_stats.get("failed_calls", 0),
        "llm_calls": result.usage.get("llm_calls", 0),
        "prompt_tokens": result.usage.get("prompt_tokens"),
        "completion_tokens": result.usage.get("completion_tokens"),
        "total_tokens": result.usage.get("total_tokens"),
        "cost_usd": result.usage.get("cost_usd"),
        "calls_without_usage": result.usage.get("calls_without_usage", 0),
        "invalid_outputs": sum(e.get("event") == "output_invalid" for e in result.state.get("trace", [])),
    }
    report = result.report
    if report is None:
        row.update(correct=False, status=None, top_service=None, top_category=None, top1_lead=False, top3=False,
                   misled=False, citation_validity=None, key_evidence_cited=None, key_evidence_retrieved=None,
                   unsupported_hypotheses=None, rounds=None)
        return row
    hyps = report.ranked_hypotheses
    top = hyps[0] if hyps else None
    match = lambda h: hypothesis_matches(h, truth.root_cause_services, truth.root_cause_categories)  # noqa: E731
    lead = bool(top and not truth.expected_inconclusive and match(top))
    if truth.expected_inconclusive:
        correct = report.status == "inconclusive"
    else:
        correct = report.status == "conclusive" and lead
    misled = bool(
        top and report.status == "conclusive" and any(
            _service_matches(top.service, [d["service"]]) and top.category.value == d["category"] for d in truth.decoy_hypotheses
        )
    )
    valid, invalid = result.citations.get("valid", 0), result.citations.get("invalid", 0)
    cited = cited_ids(report)
    row.update(
        correct=correct,
        status=report.status,
        confidence=report.confidence,
        top_service=top.service if top else None,
        top_category=top.category.value if top else None,
        top1_lead=lead,
        top3=None if truth.expected_inconclusive else any(match(h) for h in hyps[:3]),
        misled=misled,
        citation_validity=valid / (valid + invalid) if valid + invalid else None,
        key_evidence_cited=_group_coverage(truth.key_evidence, cited),
        key_evidence_retrieved=_group_coverage(truth.key_evidence, set(result.evidence_ids)),
        unsupported_hypotheses=sum(not h.supporting_evidence for h in hyps),
        rounds=len(result.state.get("rounds", [])) or None,
        termination_reason=report.termination_reason,
    )
    return row


def _mean(values: list[float | int | None]) -> float | None:
    present = [v for v in values if v is not None]
    return round(statistics.fmean(present), 4) if present else None


def aggregate(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for system in sorted({r["system"] for r in rows}):
        rs = [r for r in rows if r["system"] == system]
        conclusive_cases = [r for r in rs if not r["expected_inconclusive"]]
        inconclusive_cases = [r for r in rs if r["expected_inconclusive"]]
        latencies = [r["latency_s"] for r in rs if r["error"] is None]
        costs = [r["cost_usd"] for r in rs if r["cost_usd"] is not None]
        out[system] = {
            "runs": len(rs),
            "errored_runs": sum(r["error"] is not None for r in rs),
            "accuracy": _mean([float(r["correct"]) for r in rs]),
            "accuracy_root_cause_cases": _mean([float(r["correct"]) for r in conclusive_cases]),
            "accuracy_inconclusive_cases": _mean([float(r["correct"]) for r in inconclusive_cases]),
            "top1_lead_accuracy": _mean([float(r["top1_lead"]) for r in conclusive_cases]),
            "top3_recall": _mean([None if r["top3"] is None else float(r["top3"]) for r in conclusive_cases]),
            "misled_rate": _mean([float(r["misled"]) for r in rs]),
            "false_inconclusive_rate": _mean([float(r["status"] == "inconclusive") for r in conclusive_cases]),
            "citation_validity": _mean([r["citation_validity"] for r in rs]),
            "key_evidence_cited": _mean([r["key_evidence_cited"] for r in rs]),
            "key_evidence_retrieved": _mean([r["key_evidence_retrieved"] for r in rs]),
            "mean_tool_calls": _mean([r["tool_calls"] for r in rs]),
            "mean_failed_tool_calls": _mean([r["failed_tool_calls"] for r in rs]),
            "mean_llm_calls": _mean([r["llm_calls"] for r in rs]),
            "mean_invalid_outputs": _mean([r["invalid_outputs"] for r in rs]),
            "mean_prompt_tokens": _mean([r["prompt_tokens"] for r in rs]),
            "mean_completion_tokens": _mean([r["completion_tokens"] for r in rs]),
            "mean_total_tokens": _mean([r["total_tokens"] for r in rs]),
            "runs_with_unreported_usage": sum(bool(r["calls_without_usage"]) for r in rs),
            "total_cost_usd": round(sum(costs), 6) if costs else None,
            "mean_latency_s": _mean(latencies),
            "median_latency_s": round(statistics.median(latencies), 3) if latencies else None,
        }
    return out
