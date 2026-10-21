"""A scripted, offline stand-in for the LLM.

`ScriptedLLM` routes each request by the `ROLE:` header that every agent puts at the top of its system
prompt, and calls a handler for that role. Handlers return either a final text reply or a list of tool
calls. The default handlers behave like a cooperative model: specialists query their tools, then cite
the ids they received; reasoning cites ids from the ledger; the critic follows a configurable script.
"""

from __future__ import annotations

import json
import re
import threading
from typing import Any, Callable

from incident_investigator.llm_client import LLMResponse, ToolCall, Usage

Handler = Callable[[list[dict[str, Any]], list[dict[str, Any]] | None], "str | list[tuple[str, dict]]"]

ID_PATTERN = re.compile(r"\b([LMCDHP]\d{2,4})\b")


def role_of(messages: list[dict[str, Any]]) -> str:
    first = messages[0]["content"]
    return first.split("\n", 1)[0].removeprefix("ROLE:").strip()


def tool_results(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [json.loads(m["content"]) for m in messages if m["role"] == "tool"]


def returned_ids(messages: list[dict[str, Any]]) -> list[str]:
    return [r["id"] for res in tool_results(messages) for r in res.get("records", [])]


def ledger_ids(messages: list[dict[str, Any]]) -> list[str]:
    """Ids listed in the EVIDENCE LEDGER section of the latest user prompt."""
    text = next(m["content"] for m in reversed(messages) if m["role"] == "user")
    section = text.split("EVIDENCE LEDGER", 1)[-1]
    return list(dict.fromkeys(re.findall(r"^\[([A-Z]\d+)\]", section, re.M)))


def affected_services(messages: list[dict[str, Any]]) -> list[str]:
    text = next(m["content"] for m in messages if m["role"] == "user")
    match = re.search(r"Alerting services: (.*)", text)
    return [s.strip() for s in match.group(1).split(",")] if match else ["api-gateway"]


class ScriptedLLM:
    model = "scripted-test-model"

    def __init__(self, handlers: dict[str, Handler] | None = None, usage: tuple[int, int] | None = (120, 40)):
        self.handlers = {**default_handlers(), **(handlers or {})}
        self.usage = usage
        self.calls: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def chat(self, messages, *, tools=None, tool_choice=None, max_tokens=None, response_schema=None) -> LLMResponse:
        role = role_of(messages)
        with self._lock:
            self.calls.append({"role": role, "tool_choice": tool_choice, "n_messages": len(messages),
                               "structured": response_schema is not None})
        out = self.handlers[role](messages, tools if tool_choice != "none" else None)
        usage = Usage(prompt_tokens=self.usage[0], completion_tokens=self.usage[1], cost_usd=0.0001) if self.usage else Usage()
        if isinstance(out, list):
            calls = [ToolCall(id=f"call_{len(self.calls)}_{i}", name=n, arguments=json.dumps(a)) for i, (n, a) in enumerate(out)]
            raw = [{"id": c.id, "type": "function", "function": {"name": c.name, "arguments": c.arguments}} for c in calls]
            return LLMResponse(content=None, tool_calls=calls, message={"role": "assistant", "content": None, "tool_calls": raw},
                               usage=usage, finish_reason="tool_calls", model=self.model)
        return LLMResponse(content=out, message={"role": "assistant", "content": out}, usage=usage,
                           finish_reason="stop", model=self.model)

    def count(self, role: str) -> int:
        return sum(c["role"] == role for c in self.calls)


def _findings(messages) -> str:
    ids = returned_ids(messages)
    return json.dumps({
        "summary": f"Queried {len(tool_results(messages))} tools.",
        "observations": [{"statement": "Errors increased after onset.", "evidence_ids": ids[:3] + ["L9999"]}],
        "interpretations": [{"statement": "Likely related to the alerting service.", "evidence_ids": ids[:1], "confidence": 0.6}],
        "data_gaps": [r["note"] for r in tool_results(messages) if r["status"] != "ok"],
    })


def specialist(tool_plan: Callable[[list[str]], list[tuple[str, dict]]]) -> Handler:
    def handler(messages, tools):
        if tools and not tool_results(messages):
            return tool_plan(affected_services(messages))
        return _findings(messages)
    return handler


def reasoning_handler(confidence: float = 0.8, service: str | None = None, category: str = "deployment_regression",
                      runner_up: float = 0.2) -> Handler:
    def handler(messages, tools):
        ids = ledger_ids(messages)
        svc = service or affected_services(messages)[-1]
        return json.dumps({
            "hypotheses": [
                {"id": "H1", "service": svc, "category": category, "mechanism": "Recent change broke requests.",
                 "supporting_evidence": ids[:3] + ["X123"], "contradicting_evidence": [], "assumptions": ["change is live"],
                 "confidence": confidence},
                {"id": "H2", "service": "payments-db", "category": "resource_exhaustion", "mechanism": "DB saturated.",
                 "supporting_evidence": ids[3:5], "contradicting_evidence": ids[:1], "confidence": runner_up},
            ],
            "reasoning": "Change precedes errors.",
        })
    return handler


def critic_script(verdicts: list[str], issues: Callable[[list[str]], list[dict]] | None = None) -> Handler:
    """Return the given verdicts in order (the last one repeats). 'investigate' requests one follow-up.
    `issues(ledger_ids)` overrides the objections raised (default: one minor missing-evidence note)."""
    state = {"i": 0}

    def handler(messages, tools):
        verdict = verdicts[min(state["i"], len(verdicts) - 1)]
        state["i"] += 1
        followups = [{"agent": "dependency", "objective": "Check change history for the top service.", "focus_services": ["checkout-service"]}] if verdict == "investigate" else []
        if issues is not None:
            raised = issues(ledger_ids(messages))
        elif verdict != "accept":
            raised = [{"hypothesis_id": "H1", "issue": "missing_evidence", "severity": "minor", "detail": "confirm the change"}]
        else:
            raised = []
        return json.dumps({"verdict": verdict, "summary": f"critic says {verdict}", "issues": raised, "followup_requests": followups})
    return handler


def orchestrator_handler(action: str = "continue") -> Handler:
    def handler(messages, tools):
        text = messages[-1]["content"] if messages[-1]["role"] == "user" else ""
        if "TASK: plan" in messages[1]["content"]:
            return json.dumps({
                "incident_understanding": "errors on alerting services",
                "tasks": [
                    {"key": "obs", "agent": "observability", "objective": "Characterise errors.", "focus_services": affected_services(messages)},
                    {"key": "dep", "agent": "dependency", "objective": "Find recent changes.", "focus_services": affected_services(messages)},
                ],
            })
        critique_requests = re.findall(r"- requested (\w+) task: (.*?) \(services", text)
        return json.dumps({
            "action": action,
            "rationale": "follow the critic",
            "new_tasks": [{"agent": a, "objective": o, "focus_services": ["checkout-service"]} for a, o in critique_requests],
        })
    return handler


def reporting_handler(conclusion: str = "conclusive") -> Handler:
    def handler(messages, tools):
        ids = ledger_ids(messages)
        return json.dumps({
            "conclusion": conclusion,
            "summary": "Summary of the incident.",
            "observed_facts": [{"statement": "Error rate rose.", "evidence_ids": ids[:2]},
                               {"statement": "Something without evidence.", "evidence_ids": ["NOPE1"]}],
            "assumptions": ["Telemetry clocks are synchronised."],
            "inferred_conclusions": [{"statement": "The change caused it.", "evidence_ids": ids[:1], "confidence": 0.7}],
            "remediation": [{"action": "Roll back the change.", "priority": "immediate"}],
            "open_questions": [],
        })
    return handler


def baseline_handler(confidence: float = 0.8) -> Handler:
    def handler(messages, tools):
        if tools and not tool_results(messages):
            svc = affected_services(messages)[-1]
            return [("get_change_history", {"service": svc}), ("query_logs", {"service": svc, "min_level": "ERROR"})]
        ids = returned_ids(messages)
        return json.dumps({
            "conclusion": "conclusive",
            "summary": "Baseline summary.",
            "hypotheses": [{"id": "H1", "service": affected_services(messages)[-1], "category": "deployment_regression",
                            "mechanism": "bad deploy", "supporting_evidence": ids[:3], "confidence": confidence}],
            "observed_facts": [{"statement": "Errors seen.", "evidence_ids": ids[:2]}],
            "remediation": [{"action": "Roll back.", "priority": "immediate"}],
        })
    return handler


def default_handlers() -> dict[str, Handler]:
    return {
        "orchestrator": orchestrator_handler("continue"),
        "observability": specialist(lambda svcs: [("query_logs", {"service": svcs[-1], "min_level": "ERROR"}),
                                                  ("query_metrics", {"service": svcs[-1], "metric": "error_rate"})]),
        "dependency": specialist(lambda svcs: [("get_change_history", {"service": svcs[-1]}),
                                               ("get_dependencies", {"service": svcs[-1]})]),
        "reasoning": reasoning_handler(),
        "critic": critic_script(["investigate", "accept"]),
        "reporting": reporting_handler(),
        "baseline": baseline_handler(),
    }
