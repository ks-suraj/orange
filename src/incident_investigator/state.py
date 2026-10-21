"""Shared investigation state: task graph, evidence ledger, analyses and an event trace.

The state is owned by the orchestration engine. Agents read rendered views of it; only Python
code mutates it, under a lock where specialists run in parallel.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .schemas import (
    AgentFindings,
    Critique,
    HypothesisAnalysis,
    IncidentBrief,
    InvestigationPlan,
    OrchestratorDecision,
    TaskRequest,
)

TOOL_ORDER = ["get_change_history", "get_dependencies", "query_metrics", "query_logs", "search_past_incidents"]


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass
class Task:
    id: str
    agent: str
    objective: str
    focus_services: list[str]
    depends_on: list[str]
    requested_by: str
    round: int
    status: TaskStatus = TaskStatus.PENDING
    attempts: int = 0
    tool_calls: int = 0
    findings: AgentFindings | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "agent": self.agent,
            "objective": self.objective,
            "focus_services": self.focus_services,
            "depends_on": self.depends_on,
            "requested_by": self.requested_by,
            "round": self.round,
            "status": self.status.value,
            "attempts": self.attempts,
            "tool_calls": self.tool_calls,
            "findings": self.findings.model_dump() if self.findings else None,
            "error": self.error,
        }


@dataclass(frozen=True)
class Evidence:
    id: str
    tool: str
    summary: str
    record: dict[str, Any]
    retrieved_by: str
    call_id: str


class EvidenceLedger:
    """Every record any tool has returned during the investigation, keyed by its id."""

    def __init__(self) -> None:
        self._items: dict[str, Evidence] = {}
        self._lock = threading.Lock()

    def add(self, evidence: Evidence) -> bool:
        with self._lock:
            if evidence.id in self._items:
                return False
            self._items[evidence.id] = evidence
            return True

    def __contains__(self, evidence_id: object) -> bool:
        return evidence_id in self._items

    def __len__(self) -> int:
        return len(self._items)

    def ids(self) -> list[str]:
        with self._lock:
            return list(self._items)

    def items(self) -> list[Evidence]:
        with self._lock:
            return list(self._items.values())

    def digest(self, limit: int = 300) -> str:
        """One line per evidence item, grouped by tool. Low-severity logs are dropped first if over limit."""
        items = self.items()
        if not items:
            return "(no evidence retrieved yet)"
        omitted = 0
        if len(items) > limit:
            keep = sorted(items, key=lambda e: e.record.get("level") in ("INFO", "DEBUG"))[:limit]
            keep_ids = {e.id for e in keep}
            omitted = len(items) - len(keep)
            items = [e for e in items if e.id in keep_ids]
        rank = {name: i for i, name in enumerate(TOOL_ORDER)}
        items.sort(key=lambda e: (rank.get(e.tool, len(rank)), e.id))
        lines = [f"[{e.id}] {e.summary}" for e in items]
        if omitted:
            lines.append(f"... {omitted} INFO-level log lines omitted for brevity")
        return "\n".join(lines)


@dataclass
class RoundRecord:
    number: int
    task_ids: list[str]
    new_evidence: int = 0
    analysis: HypothesisAnalysis | None = None
    critique: Critique | None = None
    decision: OrchestratorDecision | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "number": self.number,
            "task_ids": self.task_ids,
            "new_evidence": self.new_evidence,
            "analysis": self.analysis.model_dump(mode="json") if self.analysis else None,
            "critique": self.critique.model_dump(mode="json") if self.critique else None,
            "decision": self.decision.model_dump(mode="json") if self.decision else None,
        }


def _ids(ids: list[str]) -> str:
    return f"[{', '.join(ids)}]" if ids else "[no evidence cited]"


@dataclass
class InvestigationState:
    brief: IncidentBrief
    ledger: EvidenceLedger = field(default_factory=EvidenceLedger)
    tasks: dict[str, Task] = field(default_factory=dict)
    rounds: list[RoundRecord] = field(default_factory=list)
    plan: InvestigationPlan | None = None
    analysis: HypothesisAnalysis | None = None
    critique: Critique | None = None
    termination_reason: str | None = None
    citations: dict[str, int] = field(default_factory=lambda: {"valid": 0, "invalid": 0})
    trace: list[dict[str, Any]] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _started: float = field(default_factory=time.perf_counter, repr=False)

    def log(self, actor: str, event: str, **detail: Any) -> None:
        with self._lock:
            self.trace.append({"t": round(time.perf_counter() - self._started, 3), "actor": actor, "event": event, **detail})

    def record_citations(self, valid: int, invalid: int) -> None:
        with self._lock:
            self.citations["valid"] += valid
            self.citations["invalid"] += invalid

    def add_tasks(self, requests: list[TaskRequest], requested_by: str, round_no: int, limit: int) -> list[Task]:
        """Create tasks from agent requests. Dependencies may only point at tasks that already exist,
        so the task graph can never contain a cycle."""
        created: list[Task] = []
        local: dict[str, str] = {}
        for req in requests[:limit]:
            task_id = f"T{len(self.tasks) + 1}"
            deps = [local.get(d, d) for d in req.depends_on]
            task = Task(
                id=task_id,
                agent=req.agent,
                objective=req.objective,
                focus_services=req.focus_services,
                depends_on=[d for d in deps if d in self.tasks],
                requested_by=requested_by,
                round=round_no,
            )
            self.tasks[task_id] = task
            if req.key:
                local[req.key] = task_id
            created.append(task)
        if len(requests) > limit:
            self.log("engine", "tasks_dropped", reason="max_tasks_per_round", dropped=len(requests) - limit)
        return created

    def ready_tasks(self) -> list[Task]:
        finished = {TaskStatus.DONE, TaskStatus.FAILED}
        return [
            t
            for t in self.tasks.values()
            if t.status is TaskStatus.PENDING and all(self.tasks[d].status in finished for d in t.depends_on)
        ]

    def findings_digest(self) -> str:
        parts = []
        for t in self.tasks.values():
            header = f"## {t.id} [{t.agent}] {t.objective}"
            if t.status is TaskStatus.DONE and t.findings:
                f = t.findings
                lines = [header, f"Summary: {f.summary}"]
                lines += [f"- OBSERVED: {o.statement} {_ids(o.evidence_ids)}" for o in f.observations]
                lines += [f"- INFERRED (confidence {i.confidence:.2f}): {i.statement} {_ids(i.evidence_ids)}" for i in f.interpretations]
                lines += [f"- DATA GAP: {g}" for g in f.data_gaps]
                parts.append("\n".join(lines))
            elif t.status is TaskStatus.FAILED:
                parts.append(f"{header}\n- TASK FAILED: {t.error}")
        return "\n\n".join(parts) or "(no findings yet)"

    def dependency_context(self, task: Task) -> str:
        parts = []
        for dep_id in task.depends_on:
            dep = self.tasks[dep_id]
            if dep.findings:
                obs = "; ".join(f"{o.statement} {_ids(o.evidence_ids)}" for o in dep.findings.observations[:8])
                parts.append(f"- {dep.id} [{dep.agent}] {dep.findings.summary} Observations: {obs}")
            else:
                parts.append(f"- {dep.id} [{dep.agent}] failed: {dep.error}")
        return "\n".join(parts)

    def data_gaps(self) -> list[str]:
        gaps: list[str] = []
        for t in self.tasks.values():
            if t.findings:
                gaps += t.findings.data_gaps
            if t.status is TaskStatus.FAILED:
                gaps.append(f"Task {t.id} ({t.agent}) failed: {t.error}")
        return list(dict.fromkeys(gaps))

    def to_dict(self) -> dict[str, Any]:
        return {
            "brief": self.brief.model_dump(),
            "plan": self.plan.model_dump(mode="json") if self.plan else None,
            "tasks": [t.to_dict() for t in self.tasks.values()],
            "rounds": [r.to_dict() for r in self.rounds],
            "termination_reason": self.termination_reason,
            "citations": self.citations,
            "evidence_ids": self.ledger.ids(),
            "trace": self.trace,
        }


def render_analysis(analysis: HypothesisAnalysis | None) -> str:
    if analysis is None or not analysis.hypotheses:
        return "(no hypotheses yet)"
    lines = []
    for rank, h in enumerate(analysis.hypotheses, 1):
        lines.append(
            f"{rank}. {h.id} service={h.service} category={h.category.value} confidence={h.confidence:.2f}\n"
            f"   mechanism: {h.mechanism}\n"
            f"   supporting: {_ids(h.supporting_evidence)} contradicting: {_ids(h.contradicting_evidence)}\n"
            f"   assumptions: {'; '.join(h.assumptions) or 'none stated'}"
        )
    lines.append(f"Reasoning: {analysis.reasoning}")
    if analysis.evidence_needed:
        lines.append("Evidence still needed: " + "; ".join(analysis.evidence_needed))
    return "\n".join(lines)


def render_critique(critique: Critique | None) -> str:
    if critique is None:
        return "(no critique yet)"
    lines = [f"Verdict: {critique.verdict}. {critique.summary}"]
    lines += [f"- [{i.issue}, {i.severity}] {i.hypothesis_id or 'general'}: {i.detail} {_ids(i.evidence_ids)}" for i in critique.issues]
    lines += [f"- requested {r.agent} task: {r.objective} (services: {', '.join(r.focus_services) or 'any'})" for r in critique.followup_requests]
    return "\n".join(lines)
