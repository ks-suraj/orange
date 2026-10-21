import json

import httpx
import pytest

from fakes import ScriptedLLM
from incident_investigator.agents import AgentOutputError, ObservabilityAgent, ReasoningAgent, consolidate_gaps
from incident_investigator.config import LLMSettings
from incident_investigator.llm_client import LLMError, MeteredLLM, OpenRouterClient, UsageMeter, strict_json_schema
from incident_investigator.state import InvestigationState, Task


def _events(state, name):
    return [e for e in state.trace if e["event"] == name]


def test_repair_loop_recovers_from_invalid_output(settings, s01):
    replies = iter(["not json at all", '{"hypotheses": [], "reasoning": "ok"}'])
    llm = ScriptedLLM({"reasoning": lambda m, t: next(replies)})
    state = InvestigationState(brief=s01.brief)
    analysis = ReasoningAgent(llm, settings.investigation, state.log).analyze(state)
    assert analysis.reasoning == "ok"
    assert llm.count("reasoning") == 2
    [invalid] = _events(state, "output_invalid")
    assert invalid["kind"] == "json_parse" and invalid["schema"] == "HypothesisAnalysis" and invalid["attempt"] == 1
    assert _events(state, "output_repaired")[0]["attempts"] == 2


def test_schema_violation_is_logged_with_field_locations(settings, s01):
    bad = json.dumps({"hypotheses": [{"id": "H1", "service": "x", "category": "gremlins", "mechanism": "m", "confidence": 250}],
                      "reasoning": "r"})
    replies = iter([bad, '{"hypotheses": [], "reasoning": "fixed"}'])
    llm = ScriptedLLM({"reasoning": lambda m, t: next(replies)})
    state = InvestigationState(brief=s01.brief)
    ReasoningAgent(llm, settings.investigation, state.log).analyze(state)
    [invalid] = _events(state, "output_invalid")
    locs = {e["loc"] for e in invalid["errors"]}
    assert invalid["kind"] == "schema_validation"
    assert {"hypotheses.0.category", "hypotheses.0.confidence"} <= locs
    assert "gremlins" not in json.dumps(invalid)  # the log records where it failed, not the model's content


def test_repair_budget_is_bounded(settings, s01):
    llm = ScriptedLLM({"reasoning": lambda m, t: '{"hypotheses": "wrong type"}'})
    state = InvestigationState(brief=s01.brief)
    with pytest.raises(AgentOutputError):
        ReasoningAgent(llm, settings.investigation, state.log).analyze(state)
    attempts = settings.investigation.max_repair_attempts + 1
    assert llm.count("reasoning") == attempts
    assert len(_events(state, "output_invalid")) == attempts and not _events(state, "output_repaired")


def test_truncated_reply_gets_a_conciseness_hint(settings, s01):
    seen = []

    def handler(messages, tools):
        seen.append(messages[-1]["content"])
        return '{"hypotheses": [], "reasoning": "ok"}' if len(seen) > 1 else '{"hypotheses": [{"id": "H1", "serv'
    llm = ScriptedLLM({"reasoning": handler})
    original = llm.chat

    def chat(messages, **kw):
        resp = original(messages, **kw)
        if len(seen) == 1:
            resp.finish_reason = "length"
        return resp
    llm.chat = chat
    ReasoningAgent(llm, settings.investigation).analyze(InvestigationState(brief=s01.brief))
    assert "cut off by the output length limit" in seen[1]


def test_toolless_agents_request_structured_output(settings, s01):
    llm = ScriptedLLM({"reasoning": lambda m, t: '{"hypotheses": [], "reasoning": "ok"}'})
    ReasoningAgent(llm, settings.investigation).analyze(InvestigationState(brief=s01.brief))
    assert llm.calls[0]["structured"] is True


def test_consolidate_gaps_deduplicates_and_caps():
    tool = ["query_logs(service=a) -> timeout: deadline [3 calls]"]
    agent = [
        "Tool-call budget was exhausted before the certificate lookup could be made.",
        "The tool-call budget was exhausted before certificate lookups.",
        "Health checks are shallow (HTTP /health only) and do not exercise TLS.",
        "Health checks are shallow HTTP /health only and do not exercise TLS on 8443.",
        "No metrics for session-store were returned.",
        "The v2.15.1 commit diff was not retrieved.",
        "Per-instance status was not retrieved.",
    ]
    shown, total = consolidate_gaps(tool, agent, limit=10)
    assert total == 8
    assert shown[0] == tool[0]  # executor-observed failures first
    assert len(shown) == 6      # 7 agent gaps -> 5 clusters
    assert any("(reported 2x)" in s for s in shown)

    capped, _ = consolidate_gaps(tool, agent, limit=4)
    assert len(capped) == 4 and capped[0] == tool[0]
    # 1 tool failure + 2 top clusters (the two duplicated ones) shown; the 3 single gaps are summarised
    assert any("(reported 2x)" in s for s in capped[1:3])
    assert capped[-1].startswith("3 further gap report(s) in 3 group(s) omitted") and "session-store" in capped[-1]


def test_consolidate_gaps_without_overflow_has_no_summary_line():
    shown, total = consolidate_gaps([], ["one gap about logs", "another about metrics"], limit=10)
    assert total == 2 and len(shown) == 2 and not any("omitted" in s for s in shown)


def test_strict_schema_keeps_field_names_and_drops_unsupported_keywords():
    from incident_investigator.schemas import Hypothesis, IncidentBrief
    s = strict_json_schema(Hypothesis.model_json_schema())
    assert s["additionalProperties"] is False and set(s["required"]) == set(s["properties"])
    assert "minimum" not in json.dumps(s) and "default" not in json.dumps(s)
    brief = strict_json_schema(IncidentBrief.model_json_schema())
    assert "title" in brief["properties"]  # a field named like a schema keyword survives


def test_specialist_tool_loop_executes_tools_and_cites(settings, s01, executor_for):
    llm = ScriptedLLM()
    state = InvestigationState(brief=s01.brief)
    ex = executor_for("S01")
    ex.ledger = state.ledger
    task = Task(id="T1", agent="observability", objective="o", focus_services=["checkout-service"], depends_on=[],
                requested_by="test", round=1)
    findings = ObservabilityAgent(llm, settings.investigation).run_task(task, state, ex)
    assert task.tool_calls == 2 and ex.stats()["by_agent"] == {"observability": 2}
    assert findings.observations[0].evidence_ids  # cited ids returned by tools (plus a fake one, stripped later)


def test_specialist_respects_per_task_budget(settings, s01, executor_for):
    settings.investigation.max_tool_calls_per_task = 1
    llm = ScriptedLLM()
    state = InvestigationState(brief=s01.brief)
    ex = executor_for("S01")
    task = Task(id="T1", agent="observability", objective="o", focus_services=[], depends_on=[], requested_by="t", round=1)
    ObservabilityAgent(llm, settings.investigation).run_task(task, state, ex)
    assert task.tool_calls == 1 and ex.stats()["tool_calls"] == 1
    assert llm.calls[-1]["tool_choice"] == "none"  # forced to answer once the budget ran out


def test_metered_llm_attributes_usage_by_role():
    meter = UsageMeter()
    llm = ScriptedLLM({"x": lambda m, t: "hi"})
    MeteredLLM(llm, meter, "critic").chat([{"role": "system", "content": "ROLE: x"}])
    MeteredLLM(llm, meter, "critic").chat([{"role": "system", "content": "ROLE: x"}])
    s = meter.summary()
    assert s["llm_calls"] == 2 and s["prompt_tokens"] == 240 and s["by_role"]["critic"]["calls"] == 2


def test_missing_usage_stays_unknown_not_zero():
    meter = UsageMeter()
    MeteredLLM(ScriptedLLM({"x": lambda m, t: "hi"}, usage=None), meter, "r").chat([{"role": "system", "content": "ROLE: x"}])
    s = meter.summary()
    assert s["prompt_tokens"] is None and s["calls_without_usage"] == 1


def _client(handler) -> OpenRouterClient:
    return OpenRouterClient(LLMSettings(api_key="k", max_retries=2), transport=httpx.MockTransport(handler), sleep=lambda s: None)


def test_openrouter_parses_tool_calls_and_usage():
    def handler(request):
        body = json.loads(request.content)
        assert body["model"] == "anthropic/claude-haiku-5.5" and body["tools"]
        return httpx.Response(200, json={
            "model": "anthropic/claude-haiku-5.5",
            "choices": [{"finish_reason": "tool_calls", "message": {
                "role": "assistant", "content": None, "reasoning_details": [{"type": "reasoning.encrypted", "data": "x"}],
                "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "query_logs", "arguments": "{\"service\":\"a\"}"}}]}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20, "cost": 0.00002,
                      "completion_tokens_details": {"reasoning_tokens": 5}},
        })
    resp = _client(handler).chat([{"role": "user", "content": "hi"}], tools=[{"type": "function", "function": {"name": "query_logs"}}])
    assert resp.tool_calls[0].name == "query_logs"
    assert resp.usage.prompt_tokens == 100 and resp.usage.reasoning_tokens == 5 and resp.usage.cost_usd == 0.00002
    assert resp.message["reasoning_details"]  # preserved for the next turn


def test_openrouter_retries_transient_errors():
    attempts = {"n": 0}

    def handler(request):
        attempts["n"] += 1
        if attempts["n"] < 3:
            return httpx.Response(429, json={"error": {"code": 429, "message": "rate limited"}})
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})
    resp = _client(handler).chat([{"role": "user", "content": "hi"}])
    assert resp.content == "ok" and attempts["n"] == 3 and resp.usage.prompt_tokens is None


def test_openrouter_auth_error_is_fatal_and_not_retried():
    attempts = {"n": 0}

    def handler(request):
        attempts["n"] += 1
        return httpx.Response(401, json={"error": {"code": 401, "message": "User not found."}})
    with pytest.raises(LLMError) as err:
        _client(handler).chat([{"role": "user", "content": "hi"}])
    assert err.value.fatal and attempts["n"] == 1


def test_openrouter_sends_structured_output_and_falls_back_on_schema_rejection():
    seen = []

    def handler(request):
        body = json.loads(request.content)
        seen.append("response_format" in body)
        if "response_format" in body:
            assert body["response_format"]["json_schema"]["strict"] is True
            return httpx.Response(400, json={"error": {"code": 400, "message": "response_format json_schema not supported"}})
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})
    client = _client(handler)
    schema = {"title": "X", "type": "object", "properties": {"a": {"type": "integer", "minimum": 0}}}
    assert client.chat([{"role": "user", "content": "hi"}], response_schema=schema).content == "{}"
    client.chat([{"role": "user", "content": "hi"}], response_schema=schema)
    assert seen == [True, False, False]  # rejected once, then prompt-only JSON for the rest of the run


def test_openrouter_other_400s_are_not_masked_by_the_fallback():
    def handler(request):
        return httpx.Response(400, json={"error": {"code": 400, "message": "context length exceeded"}})
    with pytest.raises(LLMError):
        _client(handler).chat([{"role": "user", "content": "hi"}], response_schema={"title": "X", "type": "object"})
