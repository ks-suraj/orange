"""LLM access: a provider-neutral interface, an OpenRouter implementation, and usage metering.

Agents talk to `LLMClient.chat()` using OpenAI-style chat messages and function tools. Token
usage and cost are recorded exactly as the provider reports them; when a provider omits usage
the values stay `None` (never estimated).
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Protocol

import httpx
from pydantic import BaseModel, Field

from .config import LLMSettings

RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504, 529}
FATAL_STATUS = {401, 402, 403}


class LLMError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = False, status: int | None = None):
        super().__init__(message)
        self.retryable = retryable
        self.status = status

    @property
    def fatal(self) -> bool:
        """Authentication, permission or billing failures: no later call can succeed."""
        return self.status in FATAL_STATUS


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: str = "{}"


class Usage(BaseModel):
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    reasoning_tokens: int | None = None
    cached_tokens: int | None = None
    cost_usd: float | None = None


class LLMResponse(BaseModel):
    content: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    message: dict[str, Any]  # assistant message to append to the conversation unchanged
    finish_reason: str | None = None
    usage: Usage = Field(default_factory=Usage)
    latency_s: float = 0.0
    model: str | None = None


class LLMClient(Protocol):
    model: str

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
        max_tokens: int | None = None,
        response_schema: dict[str, Any] | None = None,
    ) -> LLMResponse: ...


# JSON-Schema keywords that provider-side constrained decoding does not accept. They are still enforced,
# because every reply is validated against the full Pydantic model afterwards.
_UNSUPPORTED_SCHEMA_KEYS = {"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "minLength", "maxLength",
                            "minItems", "maxItems", "default", "title", "pattern"}


def strict_json_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Adapt a Pydantic JSON schema for strict structured outputs: closed objects, all properties required
    (optional ones are already nullable), unsupported constraint keywords removed."""
    def walk(node: Any, is_properties: bool = False) -> Any:
        if isinstance(node, dict):
            if is_properties:  # keys here are field names, not schema keywords
                return {k: walk(v) for k, v in node.items()}
            out = {k: walk(v, k == "properties") for k, v in node.items() if k not in _UNSUPPORTED_SCHEMA_KEYS}
            if out.get("type") == "object" and "properties" in out:
                out["additionalProperties"] = False
                out["required"] = list(out["properties"])
            return out
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node
    return walk(schema)


class OpenRouterClient:
    """OpenRouter chat-completions client with bounded retries on transient failures."""

    def __init__(
        self,
        settings: LLMSettings,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        if not settings.api_key:
            raise LLMError("OPENROUTER_API_KEY is not set", status=401)
        self.settings = settings
        self.model = settings.model
        self._sleep = sleep
        self.structured_outputs = settings.structured_outputs
        self._http = httpx.Client(
            base_url=settings.base_url,
            timeout=settings.timeout_s,
            transport=transport,
            headers={
                "Authorization": f"Bearer {settings.api_key}",
                "Content-Type": "application/json",
                "X-Title": "incident-investigator-v2",
            },
        )

    def chat(self, messages, *, tools=None, tool_choice=None, max_tokens=None, response_schema=None) -> LLMResponse:
        if response_schema and self.structured_outputs:
            try:
                return self._chat(messages, tools, tool_choice, max_tokens, response_schema)
            except LLMError as exc:
                if exc.status != 400 or not re.search(r"schema|response_format|structured", str(exc), re.I):
                    raise
                # The provider/model rejected the schema: use prompt-only JSON (still validated) from now on.
                self.structured_outputs = False
        return self._chat(messages, tools, tool_choice, max_tokens, None)

    def _chat(self, messages, tools, tool_choice, max_tokens, response_schema) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens or self.settings.max_tokens,
            "usage": {"include": True},
        }
        if self.settings.reasoning_effort:
            payload["reasoning"] = {"effort": self.settings.reasoning_effort}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice or "auto"
        if response_schema:
            name = re.sub(r"[^A-Za-z0-9_-]", "_", response_schema.get("title", "response"))[:64]
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": name, "strict": True, "schema": strict_json_schema(response_schema)},
            }

        error = LLMError("no request attempted")
        for attempt in range(self.settings.max_retries + 1):
            if attempt:
                self._sleep(min(2 ** (attempt - 1), 8))
            started = time.perf_counter()
            try:
                resp = self._http.post("/chat/completions", json=payload)
            except httpx.TimeoutException as exc:
                error = LLMError(f"request timed out: {exc}", retryable=True)
                continue
            except httpx.TransportError as exc:
                error = LLMError(f"transport error: {exc}", retryable=True)
                continue
            latency = time.perf_counter() - started
            try:
                body = resp.json()
            except ValueError:
                body = {}
            choices = body.get("choices") or []
            if resp.status_code != 200 or not choices:
                err = body.get("error") or {}
                status = err.get("code") if isinstance(err.get("code"), int) else resp.status_code
                if resp.status_code == 200 and not err:
                    error = LLMError("response contained no choices", retryable=True)
                else:
                    message = err.get("message") or resp.text[:300]
                    error = LLMError(f"HTTP {status}: {message}", retryable=status in RETRYABLE_STATUS, status=status)
                if error.retryable:
                    continue
                raise error
            if choices[0].get("finish_reason") == "error":
                error = LLMError(f"provider error: {choices[0].get('error')}", retryable=True)
                continue
            return parse_chat_response(body, latency)
        raise error


def parse_chat_response(body: dict[str, Any], latency_s: float) -> LLMResponse:
    choice = body["choices"][0]
    msg = choice.get("message") or {}
    raw_calls = msg.get("tool_calls") or []
    tool_calls = [
        ToolCall(
            id=tc.get("id") or f"call_{i}",
            name=(tc.get("function") or {}).get("name", ""),
            arguments=(tc.get("function") or {}).get("arguments") or "{}",
        )
        for i, tc in enumerate(raw_calls)
    ]
    content = msg.get("content")
    message: dict[str, Any] = {"role": "assistant", "content": content if raw_calls else (content or "(empty)")}
    if raw_calls:
        message["tool_calls"] = raw_calls
    if msg.get("reasoning_details"):
        # Passed back unmodified so the provider can continue the model's reasoning across turns.
        message["reasoning_details"] = msg["reasoning_details"]
    usage = body.get("usage") or {}
    return LLMResponse(
        content=content,
        tool_calls=tool_calls,
        message=message,
        finish_reason=choice.get("finish_reason"),
        usage=Usage(
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            reasoning_tokens=(usage.get("completion_tokens_details") or {}).get("reasoning_tokens"),
            cached_tokens=(usage.get("prompt_tokens_details") or {}).get("cached_tokens"),
            cost_usd=usage.get("cost"),
        ),
        latency_s=latency_s,
        model=body.get("model"),
    )


def build_client(settings: LLMSettings) -> LLMClient:
    if settings.provider == "openrouter":
        return OpenRouterClient(settings)
    raise LLMError(f"unsupported LLM_PROVIDER {settings.provider!r}")


@dataclass
class LLMCallRecord:
    role: str
    latency_s: float
    ok: bool
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    reasoning_tokens: int | None = None
    cost_usd: float | None = None
    error: str | None = None


def _sum(values: list[float | int | None]) -> float | int | None:
    present = [v for v in values if v is not None]
    return sum(present) if present else None


class UsageMeter:
    """Thread-safe record of every LLM call made during one investigation."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.records: list[LLMCallRecord] = []

    def record(self, rec: LLMCallRecord) -> None:
        with self._lock:
            self.records.append(rec)

    def summary(self) -> dict[str, Any]:
        with self._lock:
            recs = list(self.records)
        by_role: dict[str, dict[str, Any]] = {}
        for r in recs:
            d = by_role.setdefault(r.role, {"calls": 0, "prompt_tokens": None, "completion_tokens": None, "cost_usd": None})
            d["calls"] += 1
            for key in ("prompt_tokens", "completion_tokens", "cost_usd"):
                d[key] = _sum([d[key], getattr(r, key)])
        prompt = _sum([r.prompt_tokens for r in recs])
        completion = _sum([r.completion_tokens for r in recs])
        return {
            "llm_calls": len(recs),
            "failed_llm_calls": sum(not r.ok for r in recs),
            "calls_without_usage": sum(r.ok and r.prompt_tokens is None for r in recs),
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "reasoning_tokens": _sum([r.reasoning_tokens for r in recs]),
            "total_tokens": None if prompt is None and completion is None else (prompt or 0) + (completion or 0),
            "cost_usd": _sum([r.cost_usd for r in recs]),
            "llm_time_s": round(sum(r.latency_s for r in recs), 3),
            "by_role": by_role,
        }


class MeteredLLM:
    """Wraps a client so every call is attributed to an agent role in a UsageMeter."""

    def __init__(self, client: LLMClient, meter: UsageMeter, role: str):
        self.client = client
        self.meter = meter
        self.role = role
        self.model = client.model

    def chat(self, messages, **kwargs) -> LLMResponse:
        started = time.perf_counter()
        try:
            resp = self.client.chat(messages, **kwargs)
        except LLMError as exc:
            self.meter.record(LLMCallRecord(self.role, time.perf_counter() - started, ok=False, error=str(exc)))
            raise
        u = resp.usage
        self.meter.record(
            LLMCallRecord(
                self.role,
                time.perf_counter() - started,
                ok=True,
                prompt_tokens=u.prompt_tokens,
                completion_tokens=u.completion_tokens,
                reasoning_tokens=u.reasoning_tokens,
                cost_usd=u.cost_usd,
            )
        )
        return resp
