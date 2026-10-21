# Incident report S10

- **Status:** INCONCLUSIVE (top hypothesis confidence 0.30 is below 0.50; 1 verified, undisputed supporting evidence item(s); 2 required; contradicting evidence is 88% of the weighed evidence (max 35%))
- **System:** multi_agent · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** max_rounds_reached

## Summary
Incident S10 was a brief api-gateway p99 latency excursion (about 1633 ms at the 20:00 UTC sample against a roughly 180 ms baseline) that cleared by 20:05 UTC with no customer reports. The system determination is INCONCLUSIVE: the top hypothesis (search-service backend slowdown) has confidence 0.30, below the 0.50 threshold, and only one verified supporting item was available against two required. Contradicting evidence makes up 88% of the weighed evidence, above the 35% limit. Gateway error rate, CPU, memory and request rate stayed flat at 5-minute resolution, and three WARN 'upstream response slow' lines on /api/v1/search fall inside the spike window. The route-to-search-service mapping is unconfirmed, no route configuration or search-service telemetry was obtained, and no root cause can be asserted.

## Conclusion decision
- top hypothesis confidence 0.30 is below 0.50
- 1 verified, undisputed supporting evidence item(s); 2 required
- contradicting evidence is 88% of the weighed evidence (max 35%)
- Criteria: top `search-service / dependency_failure` confidence 0.30, margin 0.15, 1 verified supporting / 7 contradicting items (88% contradicting); 2 evidence-backed material critic objection(s), 5 non-blocking
  - objection: unsupported_claim: The claim that search-service serves /api/v1/search rests only on the existence of one dependency edge D02; no route configuration was obtained and the T6 resul [D02]
  - objection: alternative_not_ruled_out: The slow-upstream WARN lines are emitted by the gateway after it waits on upstream calls, so they cannot distinguish a slow upstream from gateway-side queuing o [L0151, L0178, L0185, L0192, M01, M05]

## Ranked hypotheses
1. **search-service** - dependency_failure (confidence 0.30)
   - Mechanism: A transient slowdown in the search-service backend serving /api/v1/search made upstream calls from api-gateway slow for about 5 minutes, lifting the aggregate gateway p99 to 1.6s. The three upstream-slow WARN lines on that route fall within the spike window and are the only slowness signal in the gateway logs.
   - Supporting evidence: `L0178, L0185, L0192, M03, D02`
   - Contradicting evidence: `M02, M05`
   - Assumptions: The /api/v1/search route is served by search-service, inferred from route name and single sync_http edge D02, not confirmed by route config.; The slow upstream responses cause the p99 spike rather than being a symptom of gateway-side queuing.
2. **api-gateway** - other (confidence 0.15)
   - Mechanism: A brief gateway-internal contention or near-limit client burst increased tail latency on a subset of requests, which 5-minute averages of CPU, memory and request rate would not reveal. The upstream-slow WARN lines could then be a downstream effect of gateway-side queuing.
   - Supporting evidence: `L0151, M01, M04, M05`
   - Contradicting evidence: `L0178, L0185, L0192`
   - Assumptions: A burst shorter than the 5-minute metric resolution occurred.; The rate-limiter WARN at 19:50:21 relates to the 20:00 spike, which is not established.
3. **search-service** - infrastructure_failure (confidence 0.10)
   - Mechanism: A transient infrastructure or retention-related fault in the search backend produced the slow responses, following the same path as H1 with an unverifiable cause.
   - Supporting evidence: `L0178, L0185, L0192`
   - Contradicting evidence: none
   - Assumptions: The search backend's metrics retention gap and log timeout coincide with the latency event.; No change explains the fault, based on a change feed that returned zero records and was not cross-checked.

## Observed facts
- api-gateway latency_p99_ms was about 181-185 ms from 19:45 to 19:55, reached 1633.34 ms at 20:00:00, and was 177.45 ms at 20:05 and 174.72 ms at 20:10. `M03`
- Three WARN lines read 'upstream response slow' on route /api/v1/search: 892 ms at 19:59:08, 1072 ms at 20:01:12 and 1079 ms at 20:03:10. `L0178, L0185, L0192`
- The slow-upstream WARN lines carry no upstream host or service name. `L0178, L0185, L0192`
- api-gateway error_rate stayed between 0.37% and 0.44% with no step change at 20:00. `M02`
- api-gateway cpu_pct (36.5-39.1%), memory_pct (50.5-53.8%) and request_rate (413-435 req/s) stayed in narrow ranges with no sustained change at 20:00. `M01, M04, M05`
- A rate-limiter WARN for client a5617224 near burst limit occurred at 19:50:21, about 10 minutes before the spike. `L0151`
- No ERROR-level api-gateway lines appeared in the 19:45-20:10 window. `L0151, L0178, L0185, L0192`
- The dependency graph lists api-gateway to search-service as a sync_http edge; no route configuration was returned, so the /api/v1/search mapping is not confirmed. `D02`
- Health checks at 20:28 UTC returned HTTP 200 for api-gateway, auth-service, checkout-service, search-service and search-index; these are shallow /health probes taken after the event. `H01, H02, H03, H13, H14`

## Assumptions
- The /api/v1/search route is served by search-service, inferred from the route name and the single dependency edge D02 rather than route configuration.
- The slow upstream responses caused the p99 spike rather than being a symptom of gateway-side queuing or thread contention.
- The 5-minute metric resolution is adequate to characterise the event, though sub-5-minute bursts cannot be excluded.
- The change feed returning zero records is complete; it was not cross-checked and excludes changes before 18:00 UTC.
- Shallow /health checks at 20:28 UTC do not reflect search-path behaviour during 20:00-20:05 UTC.
- (unverified - no valid evidence cited) No deployments, config changes, feature-flag changes, rollbacks or infra events were recorded for 18:00-20:30 UTC across all services; the change feed was not cross-checked from a second source.
- (unverified - no valid evidence cited) search-service metrics query failed with a retention-gap error, persisting on retry; its WARN-level log query timed out on 3 attempts; search-index has no telemetry.

## Inferred conclusions
- The leading candidate is a transient slowdown in the search backend serving /api/v1/search, but this is not established; confidence is 0.30, below the 0.50 threshold, and the attribution to search-service is unverified. (confidence 0.30) `L0178, L0185, L0192, M03, D02`
- A brief gateway-internal contention or near-limit client burst (sub-5-minute) is a competing candidate, since the slow-upstream WARN lines cannot distinguish a slow upstream from gateway-side queuing. (confidence 0.15) `L0151, M01, M04, M05, L0178`
- A sustained gateway-wide resource fault is unlikely given flat 5-minute CPU, memory, request rate and error rate. (confidence 0.60) `M01, M02, M04, M05`
- A change-induced cause is unlikely for this window based on the zero-record change feed, though this is not cross-checked. (confidence 0.40)

## Remediation
- **immediate** - Keep the incident at P3 and monitor api-gateway p99 and per-route latency for recurrence; no customer-facing mitigation is indicated since the spike self-resolved. _(The event auto-resolved at 20:05 UTC with no customer reports, and the data does not establish a cause that would justify intervention.)_
- **immediate** - Retrieve search-service latency, error, CPU and connection-pool metrics for 19:45-20:10 UTC, and retry its WARN logs, once the retention gap and log timeout are resolved. _(These are the data needed to test the leading hypothesis, and their absence prevents confirming or excluding it.)_
- **short_term** - Confirm from api-gateway route configuration which upstream serves /api/v1/search and whether any other route maps to search-service. _(The search-service attribution rests on a single dependency edge and is currently unverified.)_
- **short_term** - Add upstream host or service name and upstream duration fields to the gateway 'upstream response slow' log line. _(The current WARN lines cannot distinguish a slow upstream from gateway-side queuing or identify the upstream.)_
- **short_term** - Add per-route p99 and p50 latency metrics at finer than 5-minute resolution for api-gateway. _(Current aggregate 5-minute p99 cannot localise the excursion or test sub-5-minute bursts.)_
- **long_term** - Fix search-service metrics retention and log query reliability, and add telemetry for search-index. _(Telemetry gaps blocked testing of the downstream hypothesis and would hinder future investigations.)_
- **long_term** - Deepen health checks beyond shallow /health probes to exercise real request paths for gateway dependencies. _(Shallow checks taken after the event could not show degradation during the window.)_
- **long_term** - Cross-check the change feed against a second source and extend history beyond 18:00 UTC. _(The zero-change result has not been validated and earlier changes remain unexamined.)_

## Open questions
- Which upstream service actually serves /api/v1/search, and does any other gateway route map to search-service?
- Did search-service or search-index experience latency or errors between 19:55 and 20:05 UTC? Its telemetry was unavailable.
- Was the 20:00 spike confined to /api/v1/search, and did p50 move?
- Did a sub-5-minute burst or gateway-side queuing occur, and is the 19:50:21 rate-limiter WARN related to the spike?
- Are the zero change-feed results complete, and were there changes before 18:00 UTC?

## Data gaps and tool failures (10 shown, 32 reported)
- query_metrics(start=2026-09-10T19:45:00Z, end=2026-09-10T20:10:00Z, service=search-service) -> error: Error: metrics for search-service unavailable (retention gap) [2 calls]
- query_logs(start=2026-09-10T19:45:00Z, end=2026-09-10T20:10:00Z, service=search-service, min_level=WARN, limit=50) -> timeout: Timed out after 10000 ms: log backend query for search-service exceeded deadline (gave up after 3 attempts)
- query_logs(start=2026-09-10T19:45:00Z, end=2026-09-10T20:10:00Z, service=search-service, min_level=WARN, limit=20) -> timeout: Timed out after 10000 ms: log backend query for search-service exceeded deadline (gave up after 3 attempts)
- query_metrics(start=2026-09-10T19:45:00Z, end=2026-09-10T20:10:00Z, service=search-service, metric=latency_p99_ms) -> error: Error: metrics for search-service unavailable (retention gap)
- The downstream dependency for /api/v1/search is inferred, not confirmed. (reported 2x)
- p50 latency was not queried, so it is unknown whether median latency moved.
- No per-instance, per-route or per-region breakdown was available; whether the spike was concentrated on specific instances, routes or regions is unknown.
- Metrics are at 5-minute resolution, so exact onset and recovery are bounded to the 19:55–20:00 and 20:00–20:05 samples; the logs suggest the slow responses began before 19:59:08.
- Upstream services (the source of the slow search responses) were not queried, so the origin of the slow responses is not confirmed.
- 22 further gap report(s) in 22 group(s) omitted here (mostly about: latency, api-gateway, metrics, search-service, search, utc); the full list is in the run record.
