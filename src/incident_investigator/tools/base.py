"""Tool framework: typed inputs, a uniform result envelope, bounded retries and fault injection.

Tools are deterministic functions over scenario data. `ToolExecutor` is the only way agents reach
them: it validates arguments, enforces the shared tool-call budget, injects configured faults
(timeouts, errors, partial results), retries recoverable failures, and registers every returned
record in the evidence ledger.
"""

from __future__ import annotations

import itertools
import json
import threading
from datetime import datetime, timezone
from enum import Enum
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

from ..state import Evidence, EvidenceLedger

SIMULATED_TIMEOUT_MS = 10_000


def parse_ts(value: str) -> datetime:
    dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class TimeWindow(BaseModel):
    start: str | None = Field(None, description="ISO-8601 UTC start time, e.g. 2026-09-01T13:30:00Z (inclusive)")
    end: str | None = Field(None, description="ISO-8601 UTC end time (inclusive)")

    @field_validator("start", "end")
    @classmethod
    def _valid_ts(cls, v: str | None) -> str | None:
        if v is not None:
            parse_ts(v)  # raises ValueError with a readable message
        return v

    def in_window(self, ts: str) -> bool:
        t = parse_ts(ts)
        return (self.start is None or t >= parse_ts(self.start)) and (self.end is None or t <= parse_ts(self.end))


class ToolStatus(str, Enum):
    OK = "ok"
    PARTIAL = "partial"
    TIMEOUT = "timeout"
    ERROR = "error"


class ToolOutput(BaseModel):
    records: list[dict[str, Any]] = Field(default_factory=list)
    note: str = ""


class ToolResult(BaseModel):
    call_id: str
    tool: str
    agent: str
    args: dict[str, Any]
    status: ToolStatus
    records: list[dict[str, Any]] = Field(default_factory=list)
    note: str = ""
    attempts: int = 1
    recoverable: bool = True
    simulated_latency_ms: int = 0

    def to_llm(self) -> str:
        return json.dumps(
            {"status": self.status.value, "note": self.note, "attempts": self.attempts, "records": self.records},
            default=str,
            separators=(",", ":"),
        )


class FaultSpec(BaseModel):
    """A deterministic failure injected into a tool. `fail_attempts=None` means every attempt fails."""

    tool: str
    mode: Literal["timeout", "error", "partial"]
    when: dict[str, str] = Field(default_factory=dict, description="Only applies when these arguments match")
    fail_attempts: int | None = None
    recoverable: bool = True
    message: str = ""


class Tool:
    name: ClassVar[str]
    description: ClassVar[str]
    Input: ClassVar[type[BaseModel]]

    def run(self, data: dict[str, Any], args: Any) -> ToolOutput:
        raise NotImplementedError

    def summarize(self, record: dict[str, Any]) -> str:
        raise NotImplementedError

    def spec(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {"name": self.name, "description": self.description, "parameters": self.Input.model_json_schema()},
        }


class ToolExecutor:
    def __init__(
        self,
        tools: dict[str, Tool],
        data: dict[str, Any],
        ledger: EvidenceLedger,
        *,
        faults: list[FaultSpec] | tuple[FaultSpec, ...] = (),
        max_retries: int = 2,
        max_calls: int = 30,
    ):
        self.tools = tools
        self.data = data
        self.ledger = ledger
        self.faults = list(faults)
        self.max_retries = max_retries
        self.max_calls = max_calls
        self._fault_hits = [0] * len(self.faults)
        self._ids = itertools.count(1)
        self._lock = threading.Lock()
        self.calls = 0
        self.rejected = 0
        self.history: list[ToolResult] = []

    def remaining(self) -> int:
        return max(0, self.max_calls - self.calls)

    def execute(self, name: str, raw_args: str | dict[str, Any], agent: str, allowed: set[str] | None = None) -> ToolResult:
        with self._lock:
            call_id = f"tc{next(self._ids)}"
            if self.calls >= self.max_calls:
                self.rejected += 1
                return ToolResult(call_id=call_id, tool=name, agent=agent, args={}, status=ToolStatus.ERROR,
                                  recoverable=False, note="Rejected: the investigation's tool-call budget is exhausted.")
            self.calls += 1
        result = self._execute(call_id, name, raw_args, agent, allowed)
        with self._lock:
            self.history.append(result)
        return result

    def _execute(self, call_id, name, raw_args, agent, allowed) -> ToolResult:
        def fail(note: str, args: dict | None = None) -> ToolResult:
            return ToolResult(call_id=call_id, tool=name, agent=agent, args=args or {}, status=ToolStatus.ERROR,
                              recoverable=False, note=note)

        tool = self.tools.get(name)
        if tool is None or (allowed is not None and name not in allowed):
            return fail(f"Unknown or unavailable tool '{name}'. Available: {', '.join(sorted(allowed or self.tools))}")
        try:
            args_dict = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
            args = tool.Input.model_validate(args_dict)
        except (json.JSONDecodeError, ValidationError, TypeError) as exc:
            return fail(f"Invalid arguments: {exc}".replace("\n", " ")[:600])
        args_dict = args.model_dump(exclude_none=True)

        latency = 0
        for attempt in range(1, self.max_retries + 2):
            fault = self._active_fault(name, args_dict)
            if fault is None or fault.mode == "partial":
                output = tool.run(self.data, args)
                status, note = ToolStatus.OK, output.note
                records = output.records
                if fault is not None:
                    keep = max(1, len(records) // 2) if records else 0
                    status = ToolStatus.PARTIAL
                    note = (f"PARTIAL RESULT: {fault.message or 'backend returned incomplete data'}; "
                            f"{keep} of {len(records)} records returned. {note}").strip()
                    records = records[:keep]
                self._register(records, tool, agent, call_id)
                return ToolResult(call_id=call_id, tool=name, agent=agent, args=args_dict, status=status, records=records,
                                  note=note, attempts=attempt, simulated_latency_ms=latency + 120)
            if fault.mode == "timeout":
                latency += SIMULATED_TIMEOUT_MS
                status, recoverable = ToolStatus.TIMEOUT, True
                note = f"Timed out after {SIMULATED_TIMEOUT_MS} ms: {fault.message or 'backend did not respond'}"
            else:
                latency += 200
                status, recoverable = ToolStatus.ERROR, fault.recoverable
                note = f"Error: {fault.message or 'backend error'}"
            if not recoverable or attempt > self.max_retries:
                if recoverable:
                    note += f" (gave up after {attempt} attempts)"
                return ToolResult(call_id=call_id, tool=name, agent=agent, args=args_dict, status=status, note=note,
                                  attempts=attempt, recoverable=recoverable, simulated_latency_ms=latency)
        raise AssertionError("unreachable")

    def _active_fault(self, name: str, args: dict[str, Any]) -> FaultSpec | None:
        with self._lock:
            for i, f in enumerate(self.faults):
                if f.tool != name:
                    continue
                if any(str(args.get(k, "")).lower() != str(v).lower() for k, v in f.when.items()):
                    continue
                if f.fail_attempts is not None and self._fault_hits[i] >= f.fail_attempts:
                    continue
                self._fault_hits[i] += 1
                return f
        return None

    def _register(self, records: list[dict[str, Any]], tool: Tool, agent: str, call_id: str) -> None:
        for rec in records:
            self.ledger.add(Evidence(id=rec["id"], tool=tool.name, summary=tool.summarize(rec), record=rec,
                                     retrieved_by=agent, call_id=call_id))

    def failure_notes(self) -> list[str]:
        """One line per distinct failing query (tool, arguments, status), with a repeat count."""
        groups: dict[str, int] = {}
        for r in self.history:
            if r.status in (ToolStatus.TIMEOUT, ToolStatus.ERROR, ToolStatus.PARTIAL) and r.args:
                args = ", ".join(f"{k}={v}" for k, v in r.args.items())
                note = f"{r.tool}({args}) -> {r.status.value}: {r.note[:160]}"
                groups[note] = groups.get(note, 0) + 1
        return [note + (f" [{n} calls]" if n > 1 else "") for note, n in groups.items()]

    def stats(self) -> dict[str, Any]:
        by_status: dict[str, int] = {}
        by_tool: dict[str, int] = {}
        by_agent: dict[str, int] = {}
        for r in self.history:
            by_status[r.status.value] = by_status.get(r.status.value, 0) + 1
            by_tool[r.tool] = by_tool.get(r.tool, 0) + 1
            by_agent[r.agent] = by_agent.get(r.agent, 0) + 1
        return {
            "tool_calls": self.calls,
            "rejected_calls": self.rejected,
            "attempts": sum(r.attempts for r in self.history),
            "failed_calls": by_status.get("timeout", 0) + by_status.get("error", 0),
            "partial_calls": by_status.get("partial", 0),
            "simulated_tool_latency_ms": sum(r.simulated_latency_ms for r in self.history),
            "by_status": by_status,
            "by_tool": by_tool,
            "by_agent": by_agent,
        }
