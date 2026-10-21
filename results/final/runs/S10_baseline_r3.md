# Incident report S10

- **Status:** INCONCLUSIVE (top hypothesis confidence 0.30 is below 0.50)
- **System:** baseline · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** agent_finished

## Summary
The api-gateway p99 spike (1633 ms at 20:00:00Z, back to about 178 ms by 20:05:00Z) coincides with slow responses on the gateway's /api/v1/search route (885 to 1079 ms WARNs from 19:42 to 20:03). Gateway CPU, memory, error rate and request rate stayed flat, and no changes were recorded in the 19:00-20:30 window. The likely origin is the search path (search-service or its search-index dependency), but search-service metrics and logs were unavailable and search-index is unmonitored, so the root cause is not established. The only recent change to search-service is v5.3.1 deployed 2026-09-08, about 47 hours earlier, which does not match the onset. Confidence is low and the incident is not conclusive.

## Conclusion decision
- top hypothesis confidence 0.30 is below 0.50
- Criteria: top `search-index / dependency_failure` confidence 0.30, margin 0.10, 6 verified supporting / 1 contradicting items (14% contradicting); 0 evidence-backed material critic objection(s), 0 non-blocking

## Ranked hypotheses
1. **search-index** - dependency_failure (confidence 0.30)
   - Mechanism: A transient slowdown in the search index (e.g. a maintenance or rebuild job) raised search-service response times, so gateway calls to /api/v1/search exceeded 0.9 to 1.1 s and pushed the gateway's p99 to 1.6 s for one interval before recovering.
   - Supporting evidence: `L0126, L0178, L0185, L0192, M03, P02`
   - Contradicting evidence: `C04`
   - Assumptions: search-index causes the slowdown, since search-index has no telemetry.; The gateway's p99 spike is caused by the search route alone.
2. **search-service** - deployment_regression (confidence 0.20)
   - Mechanism: The v5.3.1 query parser change from 2026-09-08 added latency to some search queries, which surfaced as slow upstream calls on /api/v1/search during this window.
   - Supporting evidence: `C04, L0126, L0185`
   - Contradicting evidence: `M03`
   - Assumptions: The regression is load- or input-dependent and only appeared at 19:40 to 20:05.; The deploy was not already visible in the 47 hours before the incident.
3. **api-gateway** - other (confidence 0.10)
   - Mechanism: A transient gateway-side issue (e.g. connection pool or retry behaviour on the search route) produced the slow-upstream warnings and p99 spike without a backend fault.
   - Supporting evidence: `M03, L0151, L0228`
   - Contradicting evidence: `M01, M04, M05, M02`
   - Assumptions: The gateway's own resource metrics are too coarse to show a short pool exhaustion.

## Observed facts
- api-gateway latency_p99_ms jumped to 1633.34 ms at 2026-09-10T20:00:00Z; all other 5-minute points from 19:00 to 20:30 are between 173 and 187 ms. `M03`
- Gateway logs show WARN 'upstream response slow' on route /api/v1/search at 19:42:27 (885 ms), 19:59:08 (892 ms), 20:01:12 (1072 ms) and 20:03:10 (1079 ms). `L0126, L0178, L0185, L0192`
- Gateway error_rate (0.34 to 0.45%), request_rate (407 to 435 req/s), cpu_pct (36.5 to 39.5%) and memory_pct (50.5 to 54.0%) show no step change during 19:00 to 20:30. `M01, M02, M04, M05`
- Two WARN 'rate limiter: client near burst limit' messages appeared at 19:50:21 and 20:16:01, outside the spike window except as background. `L0151, L0228`
- The only search-service change in the last 7 days is deploy v5.3.1 ('query parser fixes') completed at 2026-09-08T20:30:00Z. `C04`
- Health checks for api-gateway, search-service, search-index, auth-service and checkout-service were all HTTP 200 at 20:28:00Z, after the spike ended. `H01, H14, H13, H02, H03`
- Past incident P02 (2026-02-27) had the same symptoms: search p99 high and gateway 'slow upstream' warnings, caused by an index rebuild during peak traffic. `P02`

## Assumptions
- Health checks are shallow and do not exercise search queries, so healthy checks do not rule out a search-path slowdown.
- The /api/v1/search route's slowness is caused by search-service or search-index rather than by the gateway itself.
- The 5-minute metric resolution may hide the exact duration of the spike.
- The 'retention gap' on search-service metrics is a telemetry gap, not evidence of no problem.
- (unverified - no valid evidence cited) No change events were recorded for api-gateway, search-service or the wider system between 19:00 and 20:30 on 2026-09-10.
- (unverified - no valid evidence cited) search-service metrics query returned 'retention gap' and its log queries timed out after 3 attempts, so search-service telemetry for the incident window is unavailable.
- (unverified - no valid evidence cited) search-index has no metrics or logs in the telemetry store.

## Inferred conclusions
- The incident is a transient latency spike on the search path, most likely originating in search-service or search-index, not in the gateway's own resources. (confidence 0.50) `M03, L0185, M01, M04`
- A search-index maintenance job, such as an index rebuild as in P02, is a plausible cause, but there is no change record or telemetry to confirm it. (confidence 0.30) `P02, L0185`
- The search-service v5.3.1 deploy is unlikely to be the trigger, because it happened about 47 hours before onset and no change occurred in the window. (confidence 0.25) `C04`
- Root cause is unresolved: the search-service and search-index telemetry needed to confirm the mechanism is missing. (confidence 0.80)

## Remediation
- **immediate** - No customer-facing action is needed now; the spike self-resolved. Keep the P3 alert open for monitoring. _(The gateway p99 recovered by 20:05:00Z and health checks are green.)_
- **immediate** - Restore search-service metrics and logs and check for a search-index job (rebuild, compaction, backup) running around 19:40 to 20:05 UTC. _(The data gap prevents confirming the origin of the slow responses.)_
- **short_term** - If the spike recurs, check the search-index scheduler and move heavy maintenance off peak, as in P02. _(P02 showed the same symptom signature from an index rebuild at peak.)_
- **short_term** - Add search-index metrics and logs, and a deep health check that runs a representative search query. _(Current health checks are shallow and search-index is not observable.)_
- **long_term** - Add a per-route latency alert on /api/v1/search at the gateway, with a threshold below the global p99. _(The route-level WARNs appeared about 18 minutes before the global p99 breach.)_

## Open questions
- What did search-service and search-index do between 19:40 and 20:05 UTC? Those logs and metrics timed out or are missing.
- Is the 'retention gap' on search-service metrics caused by the same backend problem as the log timeouts?
- Did a scheduled index job or a traffic change on the search path run in this window? No change record shows one.
- Did the v5.3.1 deploy from 2026-09-08 change search latency at all, which would show as a slow build-up rather than a step?
- Why did the global p99 spike to 1.6 s for one 5-minute point when the route WARNs show 0.9 to 1.1 s?

## Data gaps and tool failures (3 shown, 3 reported)
- query_metrics(start=2026-09-10T19:30:00Z, end=2026-09-10T20:30:00Z, service=search-service) -> error: Error: metrics for search-service unavailable (retention gap)
- query_logs(start=2026-09-10T19:30:00Z, end=2026-09-10T20:30:00Z, service=search-service, min_level=WARN, limit=20) -> timeout: Timed out after 10000 ms: log backend query for search-service exceeded deadline (gave up after 3 attempts)
- query_logs(start=2026-09-10T19:55:00Z, end=2026-09-10T20:06:00Z, service=search-service, min_level=INFO, limit=20) -> timeout: Timed out after 10000 ms: log backend query for search-service exceeded deadline (gave up after 3 attempts)
