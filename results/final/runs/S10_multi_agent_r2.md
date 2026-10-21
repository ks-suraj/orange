# Incident report S10

- **Status:** INCONCLUSIVE (top hypothesis confidence 0.35 is below 0.50; 0 verified, undisputed supporting evidence item(s); 2 required; contradicting evidence is 100% of the weighed evidence (max 35%))
- **System:** multi_agent · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** max_rounds_reached

## Summary
The api-gateway p99 latency rose to 1633 ms in the 20:00 UTC bucket and returned to about 177 ms by 20:05 UTC, with no customer reports. The system determination is INCONCLUSIVE because the leading hypothesis confidence (0.35) is below 0.50, no verified undisputed supporting evidence meets the required two items, and contradicting evidence dominates. The leading lead is slow upstream calls on /api/v1/search, but the route-to-service mapping rests on one graph edge and search-service metrics were unavailable. Gateway-internal causes (GC or pool stall) remain open because the relevant 20:00 data was not retrieved. No root cause is asserted.

## Conclusion decision
- top hypothesis confidence 0.35 is below 0.50
- 0 verified, undisputed supporting evidence item(s); 2 required
- contradicting evidence is 100% of the weighed evidence (max 35%)
- Criteria: top `search-service / dependency_failure` confidence 0.35, margin 0.20, 0 verified supporting / 8 contradicting items (100% contradicting); 2 evidence-backed material critic objection(s), 5 non-blocking
  - objection: alternative_not_ruled_out: The 1633 ms p99 exceeds every logged upstream time (max 1079 ms), and the only fast search request in the window (169 ms at 20:03:40) sits between slow ones. Th [M03, L0178, L0185, L0192, L0193]
  - objection: unsupported_claim: The claim that /api/v1/search is served by search-service rests on a single sync_http edge (D02). No routing configuration, upstream host field, or trace confir [D02, L0178, L0185, L0192]

## Ranked hypotheses
1. **search-service** - dependency_failure (confidence 0.35)
   - Mechanism: A transient slowdown in the service serving /api/v1/search made gateway upstream calls slow between 19:59 and 20:03, producing the 20:00 p99 sample before recovery by 20:05. The slow-upstream WARNs (892 to 1079 ms) bracket the spike and gateway CPU, memory, traffic and error rate stayed flat, so the origin plausibly lies downstream on that route. Peak warning time (1079 ms) is below the 1633 ms p99, so the warnings do not fully account for the tail.
   - Supporting evidence: `L0178, L0185, L0192, M03, D02`
   - Contradicting evidence: `L0193, M01, M04, M05`
   - Assumptions: /api/v1/search is served by search-service, inferred from edge D02 alone without routing config; The slow-upstream WARN lines reflect the same tail that produced the p99 sample; search-service was healthy at 20:28 after recovery, which says little about 20:00
2. **api-gateway** - other (confidence 0.15)
   - Mechanism: A brief gateway-internal stall such as a GC pause or connection-pool contention inflated measured latency in the 20:00 bucket without a visible CPU or traffic change. The search WARNs would then reflect gateway-side handling rather than the upstream origin.
   - Supporting evidence: `M03, M04, L0151`
   - Contradicting evidence: `L0178, L0185, L0192, M01`
   - Assumptions: GC and connection-pool metrics for 20:00, which were not retrieved, would show a short pause; The 19:50 rate-limiter warning is unrelated to the 20:00 peak
3. **auth-service** - dependency_failure (confidence 0.08)
   - Mechanism: A transient slowdown in auth-service on the request path added latency to a subset of calls and surfaced in the 20:00 p99 sample. No auth-attributed warnings were logged, but that absence depends on an unverified logging assumption.
   - Supporting evidence: `D03, M03`
   - Contradicting evidence: `L0178, L0185, L0192`
   - Assumptions: Auth latency would be logged under the triggering route, which is not established; Auth-service metrics for the window have not been checked

## Observed facts
- api-gateway latency_p99_ms was about 181 ms at 19:45, 185 ms at 19:50, 182 ms at 19:55, 1633.34 ms at 20:00, 177 ms at 20:05, 175 ms at 20:10 and 179 ms at 20:15. `M03`
- api-gateway error_rate stayed between 0.37% and 0.44% across 19:45-20:15 with no step change at 20:00. `M02`
- api-gateway request_rate ranged from 413 to 435 req/s with no surge at 20:00; cpu_pct stayed between 36.6% and 39.1% and memory_pct between 50.5% and 53.8%. `M01, M04, M05`
- Three WARN lines report 'upstream response slow' on route /api/v1/search: 892 ms at 19:59:08Z, 1072 ms at 20:01:12Z and 1079 ms at 20:03:10Z. None names an upstream host or service. `L0178, L0185, L0192`
- A fast INFO request GET /api/v1/search returned 200 in 169 ms at 20:03:40Z, between the slow warnings. `L0193`
- A single WARN 'rate limiter: client a5617224 near burst limit' was logged at 19:50:21Z; no ERROR lines or timeout lines were returned for api-gateway in the window. `L0151`
- api-gateway has sync_http edges to checkout-service, search-service and auth-service, and search-service has a sync_http edge to search-index. `D01, D02, D03, D14`
- Health checks for api-gateway and its direct dependencies returned healthy at 20:28 UTC, after the latency episode and outside the requested window. `H01, H02, H03, H13, H14`

## Assumptions
- /api/v1/search is served by search-service; this is inferred from edge D02 alone, with no routing configuration or upstream host field confirming it.
- The slow-upstream WARN lines reflect the same slow tail that produced the 1633 ms p99 sample; the logged maximum of 1079 ms does not reach that value.
- Gateway GC pauses and connection-pool waits at 20:00 would be visible in the data if they had occurred; GC and pool metrics were not retrieved.
- Health checks at 20:28 UTC, being shallow HTTP /health probes taken after recovery, say nothing about downstream state during 20:00-20:05.
- Search-service latency during the window would appear in the metrics that were unavailable; its state at 20:00 is unknown.
- (unverified - no valid evidence cited) No changes were recorded for api-gateway or any service between 19:30 and 20:10 UTC.
- (unverified - no valid evidence cited) search-service metrics query returned 'unavailable (retention gap)' and search-service log queries timed out after 3 attempts.

## Inferred conclusions
- The leading lead is a slow upstream on the /api/v1/search route, probably search-service, but this is unconfirmed and does not meet the conclusive threshold. (confidence 0.35) `L0178, L0185, L0192, D02, M03`
- A gateway-internal stall such as a GC pause or connection-pool contention remains a live alternative, because the 20:00 GC and pool data was never obtained and the fast 169 ms search request sits among the slow ones. (confidence 0.15) `L0193, M01, M04`
- A change-driven cause is unlikely, since no deployments, config changes or infra events were recorded in the window. (confidence 0.50)
- An auth-service slowdown is a weakly supported alternative, since no auth-attributed warnings were logged and auth metrics were never queried. (confidence 0.08) `D03, M03`
- The gateway's own CPU, memory, traffic and error rate do not explain the spike, which argues against gateway saturation or a traffic surge. (confidence 0.60) `M01, M02, M04, M05`

## Remediation
- **immediate** - Keep the P3 alert open for review and take no configuration changes based on this incident; no customer impact was recorded. _(The cause is undetermined and the impact was a single 5-minute bucket with auto-resolution.)_
- **immediate** - Confirm the routing configuration for /api/v1/search to establish which service serves it. _(The whole leading hypothesis depends on the route-to-service mapping, which currently rests on one graph edge.)_
- **short_term** - Restore search-service metrics and logs for 19:45-20:15 UTC and examine latency, GC and connection-pool behaviour. _(These are the data needed to test the leading lead, and they are currently unavailable.)_
- **short_term** - Pull gateway GC pause, connection-pool wait and INFO-level request timing for 20:00 UTC. _(These would test the gateway-internal alternative, which the data does not yet rule out.)_
- **short_term** - Capture per-call upstream traces or host fields for /api/v1/search to confirm the serving service and whether the tail matches the p99 sample. _(Traces would resolve both the mapping and the gap between the 1079 ms maximum and the 1633 ms p99.)_
- **long_term** - Add sub-minute p50 and p99 telemetry and per-route latency for api-gateway. _(Five-minute resolution cannot pin the onset or show which route drives the tail.)_
- **long_term** - Ensure search-service telemetry retention and log availability cover incident windows. _(The retention gap and log timeouts prevented the downstream check that the investigation needed.)_

## Open questions
- Which service actually serves /api/v1/search, and what does the routing configuration show?
- What were search-service latency, error rate, CPU, GC and connection-pool values between 19:55 and 20:05 UTC?
- Did api-gateway GC pauses or connection-pool waits occur at 20:00 UTC?
- Does the 1633 ms p99 sample correspond to an unlogged upstream tail, or to a gateway-side stall?
- Did the 20:03:40 fast search request and the slow warnings come from the same upstream instance or host?

## Data gaps and tool failures (10 shown, 37 reported)
- query_metrics(start=2026-09-10T19:45:00Z, end=2026-09-10T20:15:00Z, service=search-service) -> error: Error: metrics for search-service unavailable (retention gap)
- query_metrics(start=2026-09-10T19:55:00Z, end=2026-09-10T20:05:00Z, service=search-service) -> error: Error: metrics for search-service unavailable (retention gap)
- query_logs(start=2026-09-10T19:55:00Z, end=2026-09-10T20:05:00Z, service=search-service, min_level=WARN, limit=50) -> timeout: Timed out after 10000 ms: log backend query for search-service exceeded deadline (gave up after 3 attempts)
- query_logs(start=2026-09-10T19:59:00Z, end=2026-09-10T20:02:00Z, service=search-service, min_level=INFO, limit=20) -> timeout: Timed out after 10000 ms: log backend query for search-service exceeded deadline (gave up after 3 attempts)
- search-service metrics query returned 'unavailable (retention gap)'. The search dependency's latency, error rate, CPU, memory, GC, connection pool and restarts are unknown for 19:45-20:15. (reported 2x)
- Traces and gateway upstream timing beyond the three WARN lines were not retrieved. (reported 2x)
- Health-check results for the requested 19:45-20:15 UTC window were not returned; only a single 20:28 UTC sample per service is available, so downstream health during the latency episode is unknown.
- Downstream latency or error metrics for checkout-service, search-service and auth-service during 20:00-20:05 were not queried and are not in this output.
- Past incidents were not searched; no historical comparison was made.
- 26 further gap report(s) in 26 group(s) omitted here (mostly about: lines, search, window, returned, query, metrics); the full list is in the run record.
