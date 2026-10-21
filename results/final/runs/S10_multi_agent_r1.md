# Incident report S10

- **Status:** INCONCLUSIVE (top hypothesis confidence 0.30 is below 0.50; contradicting evidence is 50% of the weighed evidence (max 35%))
- **System:** multi_agent · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** orchestrator_stopped

## Summary
Incident S10 was a single 5-minute api-gateway p99 latency spike (1633 ms at 20:00 UTC against a roughly 175-187 ms baseline) that auto-resolved by 20:05 with no customer reports. The system determination is INCONCLUSIVE because the top hypothesis (search-service dependency slowdown, confidence 0.30) is below the 0.50 threshold and contradicting evidence is 50% of weighed evidence against a 35% maximum. Gateway slow-upstream warnings name route /api/v1/search, but the route-to-service mapping is unconfirmed and search-service telemetry was entirely unavailable. No changes were recorded in the 60 minutes before 20:00 UTC, and request rate, error rate, CPU and memory stayed flat. The slow search warnings also occurred at 19:26 and 19:42 with flat p99, and the largest logged upstream time (1079 ms) is below the p99 value, so the logs do not account for the spike magnitude. The root cause therefore cannot be established from the available data.

## Conclusion decision
- top hypothesis confidence 0.30 is below 0.50
- contradicting evidence is 50% of the weighed evidence (max 35%)
- Criteria: top `search-service / dependency_failure` confidence 0.30, margin 0.10, 4 verified supporting / 4 contradicting items (50% contradicting); 1 evidence-backed material critic objection(s), 5 non-blocking
  - objection: ignored_contradiction: Identical slow-upstream warnings at 19:26 (1068ms) and 19:42 (885ms) occurred while p99 stayed near 180ms, and the largest logged upstream time (1079ms) is belo [L0083, L0126, M03, L0192]

## Ranked hypotheses
1. **search-service** - dependency_failure (confidence 0.30)
   - Mechanism: An intermittent slowdown on the /api/v1/search path, plausibly served by search-service, produces multi-second upstream responses that inflate gateway p99 for one 5-minute bucket at 20:00. Slow-upstream warnings recur at 19:26, 19:42, 19:59, 20:01 and 20:03, so the search path is a recurring tail source, but the logged maximum of 1079 ms is below the 1633 ms p99, so the logs do not fully account for the spike.
   - Supporting evidence: `L0083, L0126, L0178, L0185, L0192, M03, M05, M02`
   - Contradicting evidence: `L0083, L0126, M03`
   - Assumptions: The /api/v1/search route is served by search-service, inferred from D02 and the route name only; Logged slow warnings are representative of the tail; The p99 spike shares the same slow upstream calls as the warnings
2. **api-gateway** - other (confidence 0.20)
   - Mechanism: A transient gateway-side stall (GC pause, connection-pool contention or rate-limiter queuing) delays requests for one sample with no visible load or resource change in CPU, memory or request rate. The search warnings would then be non-causal side effects. Pool and limiter metrics were not retrievable, so this cannot be excluded.
   - Supporting evidence: `M01, M04, M05, M02`
   - Contradicting evidence: `L0185, L0192`
   - Assumptions: Sub-5-minute stalls are invisible at 5-minute sample resolution; Gateway-measured upstream durations do not rule out a local stall
3. **auth-service** - dependency_failure (confidence 0.08)
   - Mechanism: A brief auth-service slowdown would add latency to every gateway request on the synchronous path, lifting the median as well as the tail. No auth-service latency telemetry was retrieved, and the only slow warnings name the search route, so this is weakly supported.
   - Supporting evidence: `D03, H02`
   - Contradicting evidence: `L0185, L0192`
   - Assumptions: auth-service is on the request path for all routes; Shallow health checks would not reflect a transient slowdown

## Observed facts
- api-gateway latency_p99_ms was about 173-187 ms from 19:00 to 19:55 and 20:05 to 20:30, peaking at 1633.34 ms at 20:00 and returning to 177.45 ms at 20:05. `M03`
- api-gateway request_rate stayed between 407 and 435 req/s with no step change at 20:00, and error_rate stayed between 0.34% and 0.45% with no change around 20:00. `M05, M02`
- api-gateway cpu_pct (about 36.5-39.5%) and memory_pct (about 50.5-54.0%) showed no anomaly around 20:00. `M01, M04`
- Five WARN lines 'upstream response slow' name route /api/v1/search at 19:26:33 (1068 ms), 19:42:27 (885 ms), 19:59:08 (892 ms), 20:01:12 (1072 ms) and 20:03:10 (1079 ms). `L0083, L0126, L0178, L0185, L0192`
- Three rate-limiter 'near burst limit' WARN lines occurred at 19:01:25, 19:50:21 and 20:16:01, none within the latency spike bucket. `L0009, L0151, L0228`
- No ERROR-level log lines were returned for api-gateway in the window. `L0009, L0083, L0126, L0151, L0178, L0185, L0192, L0228`
- No changes (deploy, config, feature flag or infra) were recorded for any service from 18:00 to 20:30 UTC; the last api-gateway deploy was v7.4.2 on 2026-09-04. `C01`
- api-gateway health checks and those of its three direct upstreams (checkout-service, search-service, auth-service) returned healthy at 20:28 UTC, after the blip resolved. `H01, H02, H03, H14`
- api-gateway's direct synchronous HTTP dependencies are checkout-service, search-service and auth-service. `D01, D02, D03`
- latency_p50_ms and per-route latency series do not exist for api-gateway, so the p50 and route-concentration tests could not be completed. `M03`

## Assumptions
- Route /api/v1/search is served by search-service; this is inferred from the route name and the single gateway-to-search edge, not from route configuration.
- Logged slow-upstream WARN lines (threshold around 850 ms and above) are representative of the latency tail.
- The p99 spike shares the same slow upstream calls as the logged warnings.
- Sub-5-minute stalls would be invisible at the 5-minute metric sample resolution.
- Shallow /health checks at 20:28 UTC would not reflect a transient slowdown during 20:00-20:05.
- (unverified - no valid evidence cited) search-service telemetry was unavailable: metrics returned a retention-gap error and every log query timed out after 3 attempts.

## Inferred conclusions
- The leading candidate is an intermittent slowdown on the /api/v1/search path served by search-service, but this is not established as the cause. (confidence 0.30) `L0178, L0185, L0192, D02`
- A transient gateway-side stall (GC pause, connection-pool contention or rate-limiter queuing) remains a viable alternative that cannot be excluded, since no pool or limiter metrics were available and the spike is a single bucket with flat load. (confidence 0.20) `M01, M04, M05, M02`
- A recent deploy or config change is unlikely to be the trigger, since no change was recorded in the 60 minutes before 20:00 UTC. (confidence 0.60) `C01`
- Auth-service latency is a weak candidate, since it would affect all routes and no auth-service latency telemetry was retrieved. (confidence 0.08) `D03, H02`
- Load or resource exhaustion on the gateway is unlikely, since request rate, CPU, memory and error rate stayed flat. (confidence 0.55) `M05, M01, M04, M02`
- Passing health checks at 20:28 do not rule out a transient fault during 20:00-20:05, because they ran after recovery and are shallow. (confidence 0.60) `H01, H14`

## Remediation
- **immediate** - Pull search-service metrics and logs for 19:45-20:15 UTC (latency, errors, timeouts) once the retention gap or log backend timeout is resolved, or query an alternate metrics source. _(This is the single check most likely to confirm or rule out the leading hypothesis, and search-service telemetry is entirely missing.)_
- **immediate** - Confirm the api-gateway route configuration mapping /api/v1/search to its upstream, including timeout and retry settings. _(The route-to-service attribution is unverified and is the basis of the leading hypothesis.)_
- **immediate** - Continue monitoring api-gateway p99 and the /api/v1/search slow-upstream warnings; escalate if p99 spikes recur or customer impact appears. _(The event is self-resolved and low severity, so monitoring is a safe interim step while data is missing.)_
- **short_term** - Add gateway p50 and per-route or per-upstream duration p99 metrics, and connection-pool and rate-limiter metrics. _(These series are missing and are needed to test route concentration, tail-versus-median shift and gateway-side stalls.)_
- **short_term** - Add search-service latency and timeout telemetry with reliable retention, and make the log backend query path less prone to timeouts. _(Observability gaps prevented any conclusion about the dependency and would hamper future incidents.)_
- **long_term** - Add deep health checks or synthetic probes on the /api/v1/search path at a sub-minute interval. _(Shallow 5-minute-sampled checks cannot detect brief tail-latency events like this one.)_
- **long_term** - Set explicit timeouts and retry budgets for the /api/v1/search upstream if they are not already in place. _(Bounding upstream slow calls limits the impact of any future search-path slowdown on gateway p99.)_

## Open questions
- Which upstream service actually serves /api/v1/search, and what are its timeout and retry settings?
- Did search-service latency or timeouts spike between 19:58 and 20:05 UTC, and did they precede the gateway p99 spike?
- Was there a gateway-side stall (GC pause, connection-pool or rate-limiter queuing) at 20:00 UTC that the available metrics cannot show?
- Do the 19:26 and 19:42 slow search warnings represent a recurring pattern with no p99 impact, and what is their true frequency?
- Did p50 latency move with p99 at 20:00 UTC, indicating a broad versus tail-only slowdown?

## Data gaps and tool failures (10 shown, 41 reported)
- query_metrics(start=2026-09-10T19:45:00Z, end=2026-09-10T20:15:00Z, service=search-service) -> error: Error: metrics for search-service unavailable (retention gap)
- query_logs(start=2026-09-10T19:45:00Z, end=2026-09-10T20:15:00Z, service=search-service, min_level=WARN, limit=50) -> timeout: Timed out after 10000 ms: log backend query for search-service exceeded deadline (gave up after 3 attempts)
- query_logs(start=2026-09-10T19:58:00Z, end=2026-09-10T20:05:00Z, service=search-service, min_level=WARN, limit=20) -> timeout: Timed out after 10000 ms: log backend query for search-service exceeded deadline (gave up after 3 attempts)
- query_metrics(start=2026-09-10T19:50:00Z, end=2026-09-10T20:10:00Z, service=search-service) -> error: Error: metrics for search-service unavailable (retention gap)
- query_logs(start=2026-09-10T19:50:00Z, end=2026-09-10T19:58:00Z, service=search-service, min_level=WARN, limit=20) -> timeout: Timed out after 10000 ms: log backend query for search-service exceeded deadline (gave up after 3 attempts)
- query_logs(start=2026-09-10T19:58:00Z, end=2026-09-10T20:02:00Z, service=search-service, min_level=WARN, limit=20) -> timeout: Timed out after 10000 ms: log backend query for search-service exceeded deadline (gave up after 3 attempts)
- query_logs(start=2026-09-10T20:02:00Z, end=2026-09-10T20:10:00Z, service=search-service, min_level=WARN, limit=20) -> timeout: Timed out after 10000 ms: log backend query for search-service exceeded deadline (gave up after 3 attempts)
- query_metrics(start=2026-09-10T19:58:00Z, end=2026-09-10T20:02:00Z, service=search-service, metric=latency_p99_ms) -> error: Error: metrics for search-service unavailable (retention gap)
- query_logs(start=2026-09-10T19:58:00Z, end=2026-09-10T20:02:00Z, service=search-service, min_level=ERROR, limit=10) -> timeout: Timed out after 10000 ms: log backend query for search-service exceeded deadline (gave up after 3 attempts)
- 32 further gap report(s) in 29 group(s) omitted here (mostly about: search-service, api-gateway, returned, latency, utc, logs); the full list is in the run record.
