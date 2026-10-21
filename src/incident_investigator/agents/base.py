"""Common agent machinery: structured output with bounded repair, the tool-use loop, citation checks.

An agent is a role prompt, an output schema and (for specialists) a tool subset. The LLM decides
what to query and how to interpret it; Python validates every output against its schema, executes
tools through the `ToolExecutor`, and strips evidence ids that are not in the ledger.
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, ClassVar

from pydantic import BaseModel, ValidationError

from ..config import InvestigationSettings
from ..llm_client import LLMClient, LLMResponse, ToolCall
from ..schemas import AgentFindings
from ..state import EvidenceLedger, InvestigationState, Task
from ..tools import ToolExecutor

CITATION_FIELDS = {"evidence_ids", "supporting_evidence", "contradicting_evidence"}
REJECTED_CALL = json.dumps({"status": "error", "note": "Rejected: tool-call budget for this task is exhausted."})


class AgentOutputError(RuntimeError):
    """The model did not produce schema-valid output within the repair budget."""


def extract_json(text: str) -> Any:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("no JSON object found in the reply") from None
        return json.loads(text[start : end + 1])


def describe_error(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        parts = [f"{'.'.join(str(p) for p in e['loc']) or '<root>'}: {e['msg']}" for e in exc.errors()[:8]]
        return "schema validation failed - " + "; ".join(parts)
    return str(exc)[:400]


def validation_report(schema: type[BaseModel], attempt: int, resp: LLMResponse, error: Exception) -> dict[str, Any]:
    """Structured, secret-free description of an unusable reply: where it failed, not what it contained."""
    if isinstance(error, ValidationError):
        kind = "schema_validation"
        errors = [{"loc": ".".join(str(p) for p in e["loc"]) or "<root>", "type": e["type"], "msg": e["msg"]} for e in error.errors()[:8]]
    else:
        kind = "tool_call_instead_of_answer" if resp.tool_calls else "json_parse"
        errors = [{"msg": str(error)[:200]}]
    return {
        "schema": schema.__name__,
        "attempt": attempt,
        "kind": kind,
        "finish_reason": resp.finish_reason,
        "reply_chars": len(resp.content or ""),
        "completion_tokens": resp.usage.completion_tokens,
        "errors": errors,
    }


def output_instructions(schema: type[BaseModel]) -> str:
    return (
        "OUTPUT FORMAT: when you give your final answer, reply with ONLY one JSON object (no prose, no markdown "
        "fences) that validates against this JSON Schema:\n"
        + json.dumps(schema.model_json_schema(), separators=(",", ":"))
    )


def sanitize_citations(model: BaseModel, ledger: EvidenceLedger) -> tuple[int, int]:
    """Remove evidence ids that are not in the ledger (in place). Returns (valid, invalid) counts."""
    valid = invalid = 0

    def walk(obj: Any) -> None:
        nonlocal valid, invalid
        if isinstance(obj, BaseModel):
            for name in type(obj).model_fields:
                value = getattr(obj, name)
                if name in CITATION_FIELDS and isinstance(value, list):
                    kept: list[str] = []
                    for raw in value:
                        eid = str(raw).strip().strip("[]")
                        if eid in ledger:
                            if eid not in kept:
                                kept.append(eid)
                                valid += 1
                        else:
                            invalid += 1
                    setattr(obj, name, kept)
                else:
                    walk(value)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(model)
    return valid, invalid


class Agent:
    role: ClassVar[str]
    instructions: ClassVar[str]
    output_schema: ClassVar[type[BaseModel]]

    def __init__(self, llm: LLMClient, settings: InvestigationSettings, log: Callable[..., None] | None = None):
        self.llm = llm
        self.settings = settings
        self._log = log or (lambda actor, event, **detail: None)

    def system_prompt(self, schema: type[BaseModel]) -> str:
        return f"ROLE: {self.role}\n\n{self.instructions.strip()}\n\n{output_instructions(schema)}"

    def complete(self, user: str, schema: type[BaseModel] | None = None) -> Any:
        """A single structured reply with no tools. The schema is also sent for provider-side constrained
        decoding where supported; the reply is validated against the Pydantic model either way."""
        schema = schema or self.output_schema
        messages = [{"role": "system", "content": self.system_prompt(schema)}, {"role": "user", "content": user}]
        resp = self.llm.chat(messages, response_schema=schema.model_json_schema())
        return self._parse_or_repair(messages, resp, schema, tools=None)

    def investigate(self, user: str, tool_names: tuple[str, ...], executor: ToolExecutor, max_calls: int) -> tuple[Any, int]:
        """Tool-use loop: the model chooses tools and arguments until it answers or the budget runs out."""
        schema = self.output_schema
        allowed = set(tool_names)
        tools = [executor.tools[n].spec() for n in tool_names]
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt(schema)},
            {"role": "user", "content": user},
        ]
        used = 0
        while True:
            resp = self.llm.chat(messages, tools=tools, tool_choice="auto")
            if not resp.tool_calls:
                return self._parse_or_repair(messages, resp, schema, tools), used
            messages.append(resp.message)
            granted = resp.tool_calls[: max(0, max_calls - used)]
            results = self._run_calls(granted, executor, allowed)
            used += len(granted)
            for call in resp.tool_calls:
                messages.append({"role": "tool", "tool_call_id": call.id, "content": results.get(call.id, REJECTED_CALL)})
            if used >= max_calls or executor.remaining() <= 0:
                messages.append({
                    "role": "user",
                    "content": "Tool-call budget exhausted. Do not call tools again. Give your final JSON answer now, "
                               "based only on the evidence gathered, and list what you could not check in data_gaps.",
                })
                resp = self.llm.chat(messages, tools=tools, tool_choice="none")
                return self._parse_or_repair(messages, resp, schema, tools), used

    def _run_calls(self, calls: list[ToolCall], executor: ToolExecutor, allowed: set[str]) -> dict[str, str]:
        def run(call: ToolCall) -> tuple[str, str]:
            return call.id, executor.execute(call.name, call.arguments, self.role, allowed).to_llm()

        if len(calls) <= 1:
            return dict(run(c) for c in calls)
        with ThreadPoolExecutor(max_workers=min(4, len(calls))) as pool:
            return dict(pool.map(run, calls))

    def _parse_or_repair(self, messages: list[dict[str, Any]], resp: LLMResponse, schema: type[BaseModel], tools) -> Any:
        for attempt in range(self.settings.max_repair_attempts + 1):
            messages.append(resp.message)
            if resp.tool_calls:
                # Tools are switched off at this stage; answer any stray calls so the transcript stays valid.
                messages += [{"role": "tool", "tool_call_id": c.id, "content": REJECTED_CALL} for c in resp.tool_calls]
                error: Exception = ValueError("tool calls are not allowed now; a final JSON answer is required")
            else:
                try:
                    result = schema.model_validate(extract_json(resp.content or ""))
                except (ValueError, ValidationError) as exc:
                    error = exc
                else:
                    if attempt:
                        self._log(self.role, "output_repaired", schema=schema.__name__, attempts=attempt + 1)
                    return result
            self._log(self.role, "output_invalid", **validation_report(schema, attempt + 1, resp, error))
            if attempt == self.settings.max_repair_attempts:
                raise AgentOutputError(f"{self.role}: no valid {schema.__name__} after {attempt + 1} attempts ({describe_error(error)})")
            hint = (" Your reply was cut off by the output length limit: be more concise (fewer, shorter items)."
                    if resp.finish_reason == "length" else "")
            messages.append({
                "role": "user",
                "content": f"Your previous reply could not be used: {describe_error(error)}.{hint}\n"
                           "Reply with ONLY the corrected JSON object.",
            })
            if tools:
                resp = self.llm.chat(messages, tools=tools, tool_choice="none")
            else:
                resp = self.llm.chat(messages, response_schema=schema.model_json_schema())
        raise AssertionError("unreachable")


class SpecialistAgent(Agent):
    """Base for the evidence-gathering agents. Each owns a subset of the tools."""

    output_schema = AgentFindings
    tool_names: ClassVar[tuple[str, ...]]

    def run_task(self, task: Task, state: InvestigationState, executor: ToolExecutor) -> AgentFindings:
        budget = min(self.settings.max_tool_calls_per_task, executor.remaining())
        context = state.dependency_context(task)
        user = (
            f"TASK {task.id}: {task.objective}\n"
            f"Focus services: {', '.join(task.focus_services) or 'use your judgement'}\n\n"
            f"INCIDENT\n{state.brief.render()}\n\n"
            + (f"FINDINGS FROM TASKS THIS ONE DEPENDS ON\n{context}\n\n" if context else "")
            + f"You may make at most {budget} tool calls. Independent queries can be issued together in one turn."
        )
        findings, used = self.investigate(user, self.tool_names, executor, budget)
        task.tool_calls = used
        return findings


EVIDENCE_RULES = """
Rules:
- Observations state only what returned data literally shows; every observation cites the `id` of the records
  that show it. Interpretations are your inferences, with a confidence between 0 and 1.
- Cite only ids that tools actually returned. Never invent ids.
- Report evidence that argues AGAINST an obvious explanation as carefully as evidence for it.
- A failed, timed-out or partial tool result is a data gap, not evidence that nothing is wrong. Record it in
  data_gaps; retry with a narrower query only if that is likely to help.
- Use exact timestamps when you describe timing; note which signal changed first.
"""
SPECIALIST_RULES = EVIDENCE_RULES + "- Do not decide the final root cause; the reasoning agent compares hypotheses across all findings.\n"
