import json

from incident_investigator.tools import FaultSpec, ToolStatus


def test_query_logs_filters_and_registers_evidence(executor_for):
    ex = executor_for("S01")
    r = ex.execute("query_logs", {"service": "checkout-service", "min_level": "ERROR", "limit": 5}, "t")
    assert r.status is ToolStatus.OK
    assert 0 < len(r.records) <= 5
    assert all(rec["level"] == "ERROR" for rec in r.records)
    assert "matching lines" in r.note
    assert all(rec["id"] in ex.ledger for rec in r.records)


def test_query_logs_unknown_service_lists_alternatives(executor_for):
    r = executor_for("S01").execute("query_logs", {"service": "nope"}, "t")
    assert r.records == [] and "Services with logs" in r.note


def test_metrics_stats_and_window(executor_for, s01):
    ex = executor_for("S01")
    r = ex.execute("query_metrics", {"service": "checkout-service", "metric": "error_rate",
                                     "start": s01.brief.window_start, "end": s01.brief.window_end}, "t")
    rec = r.records[0]
    assert rec["stats"]["max"] > 10 > rec["stats"]["first"]  # injected step from ~0.3% to ~18.5%


def test_change_history_and_dependencies(executor_for):
    ex = executor_for("S01")
    changes = ex.execute("get_change_history", {"service": "checkout-service", "change_type": "deploy"}, "t").records
    assert any("v2.14.0" in c.get("version", "") for c in changes)
    deps = ex.execute("get_dependencies", {"service": "payment-service", "direction": "dependencies"}, "t").records
    callees = {d["callee"] for d in deps if d["record_type"] == "edge"}
    assert callees == {"payments-db", "payment-provider"}


def test_past_incident_search_ranks_by_overlap(executor_for):
    r = executor_for("S01").execute("search_past_incidents", {"query": "NullPointerException pricing checkout"}, "t")
    assert r.records and "pricing" in r.records[0]["title"].lower()


def test_invalid_arguments_are_reported_not_raised(executor_for):
    ex = executor_for("S01")
    r = ex.execute("query_logs", '{"service": "checkout-service", "start": "yesterday"}', "t")
    assert r.status is ToolStatus.ERROR and "Invalid arguments" in r.note and not r.recoverable
    r = ex.execute("query_logs", "not json", "t")
    assert r.status is ToolStatus.ERROR


def test_unavailable_tool_is_rejected(executor_for):
    r = executor_for("S01").execute("get_change_history", {}, "observability", allowed={"query_logs"})
    assert r.status is ToolStatus.ERROR and "unavailable" in r.note


def test_persistent_timeout_retries_then_gives_up(executor_for):
    ex = executor_for("S08", max_retries=2)  # S08: query_logs times out for payment-service
    r = ex.execute("query_logs", {"service": "payment-service"}, "t")
    assert r.status is ToolStatus.TIMEOUT and r.attempts == 3 and r.records == []
    assert "gave up after 3 attempts" in r.note
    # other services are unaffected
    assert ex.execute("query_logs", {"service": "checkout-service"}, "t").status is ToolStatus.OK
    assert ex.failure_notes() and "timeout" in ex.failure_notes()[0]


def test_transient_error_recovers_on_retry(executor_for):
    ex = executor_for("S09")  # change history fails once (recoverable)
    r = ex.execute("get_change_history", {}, "t")
    assert r.status is ToolStatus.OK and r.attempts == 2


def test_partial_result_then_full(executor_for):
    ex = executor_for("S09")  # first metrics call for inventory-service is partial
    first = ex.execute("query_metrics", {"service": "inventory-service"}, "t")
    second = ex.execute("query_metrics", {"service": "inventory-service"}, "t")
    assert first.status is ToolStatus.PARTIAL and "PARTIAL RESULT" in first.note
    assert second.status is ToolStatus.OK and len(second.records) > len(first.records)


def test_non_recoverable_error_is_not_retried(executor_for):
    ex = executor_for("S12")
    r = ex.execute("query_logs", {"service": "api-gateway"}, "t")
    assert r.status is ToolStatus.ERROR and r.attempts == 1 and not r.recoverable


def test_budget_is_enforced(executor_for):
    ex = executor_for("S01", max_calls=2)
    for _ in range(2):
        ex.execute("get_change_history", {}, "t")
    r = ex.execute("get_change_history", {}, "t")
    assert r.status is ToolStatus.ERROR and "budget" in r.note
    assert ex.stats()["tool_calls"] == 2 and ex.stats()["rejected_calls"] == 1


def test_fault_matching_is_argument_specific(executor_for):
    ex = executor_for("S01", faults=[FaultSpec(tool="query_metrics", mode="error", when={"service": "auth-service"}, recoverable=False)])
    assert ex.execute("query_metrics", {"service": "auth-service"}, "t").status is ToolStatus.ERROR
    assert ex.execute("query_metrics", {"service": "api-gateway"}, "t").status is ToolStatus.OK


def test_result_serialises_for_llm(executor_for):
    payload = json.loads(executor_for("S01").execute("get_change_history", {}, "t").to_llm())
    assert payload["status"] == "ok" and payload["records"][0]["id"].startswith("C")


def test_ground_truth_is_not_reachable_through_tools(s01):
    # The answer lives in data/ground_truth/, never in the data the tools serve.
    blob = json.dumps(s01.model_dump())
    assert "root_cause_services" not in blob and "expected_inconclusive" not in blob
