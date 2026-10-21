# Incident report S10

- **Status:** INCONCLUSIVE (top hypothesis confidence 0.40 is below 0.50)
- **System:** baseline · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** agent_finished

## Summary
The api-gateway p99 latency spike is a single 5-minute bucket at 20:00Z (1633 ms vs a ~180 ms baseline) that auto-resolved by 20:05Z. The only slow upstream warnings are on the /api/v1/search route, which points at search-service, but its metrics are unavailable (retention gap) and its logs time out, so the origin cannot be confirmed. Gateway CPU, memory, request rate and error rate stayed flat, and no changes were recorded in the window. Customer impact appears negligible (error rate 0.34–0.45% throughout). Confidence is low and the incident is best treated as a transient, unexplained search-path slowdown pending search-service data.

## Conclusion decision
- top hypothesis confidence 0.40 is below 0.50
- Criteria: top `search-service / dependency_failure` confidence 0.40, margin 0.25, 5 verified supporting / 2 contradicting items (29% contradicting); 0 evidence-backed material critic objection(s), 0 non-blocking

## Ranked hypotheses
1. **search-service** - dependency_failure (confidence 0.40)
   - Mechanism: A transient slowdown in search-service (possibly its index or backend) increased response times on /api/v1/search, pushing gateway p99 above threshold for about 5 minutes until it recovered.
   - Supporting evidence: `M03, L0126, L0178, L0185, L0192`
   - Contradicting evidence: `H01, H14`
   - Assumptions: Gateway p99 on the search route reflects search-service latency.; The health checks are shallow and do not exercise search queries.
2. **search-service** - deployment_regression (confidence 0.15)
   - Mechanism: The v5.3.1 query parser change introduced slow queries for some inputs, with the slow path triggered intermittently.
   - Supporting evidence: `C04, L0126`
   - Contradicting evidence: `M03, C04`
   - Assumptions: The deploy did not show slowdown until 19:42Z, two days after release, which requires a trigger such as a specific query pattern.
3. **api-gateway** - traffic_surge (confidence 0.08)
   - Mechanism: A burst from one or a few clients pushed the gateway into rate limiting and queueing, raising p99 for a few minutes.
   - Supporting evidence: `L0151, L0228`
   - Contradicting evidence: `M05, M01, M04`
   - Assumptions: Rate-limiter warnings reflect real bursts rather than normal limiter behaviour.

## Observed facts
- api-gateway p99 latency was 1633.34 ms at 2026-09-10T20:00:00Z, against 173–187 ms in all other 5-minute buckets from 19:00 to 20:30Z. `M03`
- api-gateway error_rate stayed between 0.34% and 0.45% over 19:00–20:30Z, with no visible change at 20:00Z. `M02`
- api-gateway cpu_pct (36.5–39.5%), memory_pct (50.5–54.0%) and request_rate (407–435 req/s) show no spike around 20:00Z. `M01, M04, M05`
- Gateway logs show 'upstream response slow' warnings on route /api/v1/search at 19:42:27 (885 ms), 19:59:08 (892 ms), 20:01:12 (1072 ms) and 20:03:10 (1079 ms). `L0126, L0178, L0185, L0192`
- Two rate-limiter 'client near burst limit' warnings occurred, at 19:50:21 and 20:16:01, both outside the 20:00–20:05 window. `L0151, L0228`
- Health checks at 20:28Z report api-gateway, auth-service, checkout-service and search-service as healthy (HTTP /health 200); these checks are shallow. `H01, H02, H03, H14`
- The only recorded change to search-service in the 7-day window is deploy v5.3.1 at 2026-09-08T20:30:00Z; no changes to api-gateway or its other dependencies in 18:00–20:30Z. `C04`

## Assumptions
- The /health endpoints do not exercise the search query path, so 'healthy' does not rule out search-service slowness.
- The gateway's p99 for the search route is dominated by the search-service response time, since the slow warnings are on that route.
- The retention gap and log timeouts are data-availability issues, not signals that search-service is down.
- The gateway's rate-limiter warnings are unrelated to the 20:00Z latency spike.
- (unverified - no valid evidence cited) search-service metrics query returned an error: metrics unavailable due to a retention gap.
- (unverified - no valid evidence cited) search-service log queries timed out three times, including a narrow 19:55–20:06Z window.

## Inferred conclusions
- The most likely origin is a transient slowdown in search-service (or its index/backend) that lasted about 5 minutes and recovered without intervention. (confidence 0.40) `M03, L0178, L0185, L0192`
- A gateway-side resource problem is unlikely, because CPU, memory and request rate were flat during the spike. (confidence 0.75) `M01, M04, M05`
- The v5.3.1 search-service deploy two days earlier is an unlikely trigger, since slow warnings began only in the 20:00 window and not at deploy time, but this is not ruled out without search-service data. (confidence 0.20) `C04, L0126`
- Customer impact is likely negligible given the flat error rate and the self-resolved, single-bucket nature of the spike. (confidence 0.60) `M02, M03`

## Remediation
- **immediate** - No immediate mitigation needed; monitor api-gateway p99 on /api/v1/search for recurrence over the next hour. _(The spike self-resolved and no customer impact is reported.)_
- **immediate** - Restore search-service metrics and log access (retention gap and log backend timeouts) and re-query 19:50–20:10Z. _(Needed to confirm or reject search-service as the origin.)_
- **short_term** - Check search-service index or background jobs (e.g. index rebuild, compaction) running around 20:00Z, as in past incident P02. _(A past search latency spike was caused by a rebuild during peak traffic.)_
- **long_term** - Add a deep health check on search-service that exercises a real query, and per-route latency panels at the gateway. _(Current /health checks are shallow and do not show the slow route.)_
- **long_term** - Fix the telemetry retention gap for search-service metrics and the log backend timeouts. _(Current gaps prevented root-cause analysis of this incident.)_

## Open questions
- What did search-service latency, CPU and dependency calls look like between 19:50 and 20:10Z? Metrics are unavailable and logs time out.
- Was there a scheduled job, index rebuild or traffic burst on the search backend at 20:00Z?
- Does the 20:00Z spike appear on the search route only, or on other gateway routes too? Per-route data was not available.
- Is the v5.3.1 deploy (2026-09-08) linked to the slow-search warnings that started at 19:42Z?

## Data gaps and tool failures (3 shown, 3 reported)
- query_metrics(start=2026-09-10T19:30:00Z, end=2026-09-10T20:30:00Z, service=search-service) -> error: Error: metrics for search-service unavailable (retention gap)
- query_logs(start=2026-09-10T19:30:00Z, end=2026-09-10T20:30:00Z, service=search-service, min_level=WARN, limit=20) -> timeout: Timed out after 10000 ms: log backend query for search-service exceeded deadline (gave up after 3 attempts)
- query_logs(start=2026-09-10T19:55:00Z, end=2026-09-10T20:06:00Z, service=search-service, min_level=INFO, limit=10) -> timeout: Timed out after 10000 ms: log backend query for search-service exceeded deadline (gave up after 3 attempts)
