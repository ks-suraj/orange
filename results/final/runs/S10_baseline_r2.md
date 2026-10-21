# Incident report S10

- **Status:** INCONCLUSIVE (top hypothesis confidence 0.35 is below 0.50)
- **System:** baseline · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** agent_finished

## Summary
api-gateway p99 latency jumped to 1633 ms in the 20:00 UTC sample and returned to about 177 ms by 20:05, matching the P3 alert. The gateway's own CPU, memory, request rate and error rate stayed flat. Its WARN logs point at slow calls to /api/v1/search, and no changes were recorded in the window. search-service and search-index telemetry could not be retrieved (metrics retention gap, log queries timed out), so the upstream cause is unconfirmed. The incident is self-resolved with no customer impact, and the evidence is not conclusive.

## Conclusion decision
- top hypothesis confidence 0.35 is below 0.50
- Criteria: top `search-index / resource_exhaustion` confidence 0.35, margin 0.10, 5 verified supporting / 2 contradicting items (29% contradicting); 0 evidence-backed material critic objection(s), 0 non-blocking

## Ranked hypotheses
1. **search-index** - resource_exhaustion (confidence 0.35)
   - Mechanism: A transient load or maintenance event on the search index (for example a rebuild or compaction) slowed /api/v1/search responses for about 5 minutes. The gateway's sync calls then exceeded latency targets, which raised p99 and produced the slow-upstream WARNs until the event ended.
   - Supporting evidence: `L0178, L0185, L0192, M03, P02`
   - Contradicting evidence: `M02, H13`
   - Assumptions: The search-service calls search-index synchronously, as the dependency graph states.; The slow calls were on the search path, not elsewhere in search-service.
2. **search-service** - other (confidence 0.25)
   - Mechanism: A transient fault inside search-service, such as a GC pause, a slow dependency or a noisy query, slowed search responses for about 5 minutes. The gateway's sync calls then timed out slowly, which raised p99.
   - Supporting evidence: `L0178, L0185, L0192, M03`
   - Contradicting evidence: `M02, H14`
   - Assumptions: search-service is the only service in the search path that the slow WARNs describe.
3. **api-gateway** - traffic_surge (confidence 0.10)
   - Mechanism: A burst from client a5617224 near its rate limit added load on the search route. This pushed gateway queueing and search latency up briefly.
   - Supporting evidence: `L0151`
   - Contradicting evidence: `M05, M01, M04`
   - Assumptions: The client's burst reached the search route at about 20:00 UTC, which the data does not show.

## Observed facts
- api-gateway p99 latency was about 175–187 ms for every 5-minute point from 19:00 to 19:55 UTC, then 1633.34 ms at 20:00 UTC and 177.45 ms at 20:05 UTC. `M03`
- api-gateway error_rate stayed between 0.34% and 0.45% across 19:00–20:30 UTC, with no visible change at 20:00. `M02`
- api-gateway cpu_pct (36.5–39.5%), memory_pct (50.5–54.0%) and request_rate (407–435 req/s) show no visible change around 20:00 UTC. `M01, M04, M05`
- api-gateway logged 'upstream response slow' WARNs for route /api/v1/search at 19:59:08 (892 ms), 20:01:12 (1072 ms) and 20:03:10 (1079 ms). `L0178, L0185, L0192`
- api-gateway logged one rate-limiter WARN for client a5617224 near burst limit at 19:50:21 UTC. `L0151`
- At 20:28 UTC, health checks for api-gateway, search-service, search-index, auth-service and checkout-service all returned HTTP 200. `H01, H02, H03, H14, H13`

## Assumptions
- The /health checks are shallow and do not exercise the search query path or database writes.
- The search-service latency is the cause of the gateway's slow-upstream warnings, since the gateway's dependencies are search-service, checkout-service and auth-service.
- The 'no changes' result is complete for the change-history source.
- The one-sample 20:00 spike reflects a real transient event and is not a metrics artifact.
- (unverified - no valid evidence cited) No deployments, config changes, feature flags, rollbacks or infra events are recorded for api-gateway or search-service from 2026-09-09 through 20:30 UTC on 2026-09-10.
- (unverified - no valid evidence cited) search-service metrics query returned 'unavailable (retention gap)' for 19:30–20:30 UTC.
- (unverified - no valid evidence cited) search-service log queries timed out after 3 attempts for 19:50–20:10 and 19:58–20:04 UTC.

## Inferred conclusions
- The most likely origin is a transient slowdown in the search path (search-service or search-index), since all the slow-upstream WARNs are on /api/v1/search and the gateway's own resources were flat. This is not confirmed because search-service telemetry and logs are unavailable. (confidence 0.40) `M03, L0178, L0185, L0192`
- A transient burst from a single client (a5617224) is a weaker candidate: the rate-limiter WARN came 10 minutes before the spike, and rate limiting would not by itself produce slow upstream responses. (confidence 0.12) `L0151`
- Because no change was recorded, the incident looks like a transient, self-recovering event with no lasting fault. The health checks being green at 20:28 supports recovery but would not detect a search-query-level problem. (confidence 0.50) `H01, H14, H13`

## Remediation
- **immediate** - Restore search-service metrics and log retention so the 19:55–20:05 UTC window can be examined. _(The telemetry gap is the main blocker to confirming the upstream origin.)_
- **immediate** - Check search-index for a rebuild, compaction or other maintenance job around 19:58–20:03 UTC. _(Past incident P02 had a latency spike caused by an index rebuild during peak traffic.)_
- **short_term** - Set an alert on search-service latency with a deep health check that runs a real search query. _(Current health checks are green and do not reflect the search path.)_
- **short_term** - Review the rate-limit policy for client a5617224 and whether its traffic is legitimate. _(The client came near its burst limit shortly before the spike.)_
- **long_term** - Schedule index maintenance off-peak and enforce that scheduling. _(Follows the prevention step from P02.)_

## Open questions
- What did search-service and search-index do between 19:55 and 20:05 UTC? Their telemetry is missing.
- Why did the log backend time out for search-service, and is that related to the incident?
- Was there a scheduled job on search-index or a traffic spike from client a5617224 at 20:00 UTC?
- Do the 20:00 gateway latency samples show a real user-facing impact beyond the single 5-minute point?

## Data gaps and tool failures (3 shown, 3 reported)
- query_metrics(start=2026-09-10T19:30:00Z, end=2026-09-10T20:30:00Z, service=search-service) -> error: Error: metrics for search-service unavailable (retention gap)
- query_logs(start=2026-09-10T19:50:00Z, end=2026-09-10T20:10:00Z, service=search-service, min_level=WARN, limit=20) -> timeout: Timed out after 10000 ms: log backend query for search-service exceeded deadline (gave up after 3 attempts)
- query_logs(start=2026-09-10T19:58:00Z, end=2026-09-10T20:04:00Z, service=search-service, min_level=INFO, limit=10) -> timeout: Timed out after 10000 ms: log backend query for search-service exceeded deadline (gave up after 3 attempts)
