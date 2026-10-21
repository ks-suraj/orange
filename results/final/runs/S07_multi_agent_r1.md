# Incident report S07

- **Status:** INCONCLUSIVE (contradicting evidence is 38% of the weighed evidence (max 35%))
- **System:** multi_agent · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** max_rounds_reached

## Summary
Checkout-service p99 latency rose from about 320ms to about 2.9-3.0s and its error rate from about 0.3% to about 5.6% in the 18:00 UTC bucket, with checkout CPU pinned at 94-100% and request rate up about 4x. The 503s are worker-pool saturation rejections (queue 500/500) in checkout-service, and HPA was capped at maxReplicas 20 while it wanted 34. The system determination is INCONCLUSIVE: the traffic surge is the best-supported explanation (confidence 0.50), but the source of the surge, whether retries or campaign traffic, and the inventory contribution to checkout latency remain unresolved. The api-gateway alert appears to be a propagation effect, since gateway p99 and error rate stayed flat. Two changes preceded onset (inventory-service v4.2.0 client library deploy at 17:25Z and the api-gateway fall-sale flag at 17:55Z), but neither is confirmed as a cause.

## Conclusion decision
- contradicting evidence is 38% of the weighed evidence (max 35%)
- Criteria: top `checkout-service / traffic_surge` confidence 0.50, margin 0.35, 8 verified supporting / 5 contradicting items (38% contradicting); 1 evidence-backed material critic objection(s), 5 non-blocking
  - objection: alternative_not_ruled_out: Inventory-service latency rose from about 90ms to about 142-145ms (about 1.6x) at 18:00 and checkout logs show sparse slow inventory reservation warnings (679-1 [M23, L0241, L0302, L0318]

## Ranked hypotheses
1. **checkout-service** - traffic_surge (confidence 0.50)
   - Mechanism: Request volume into checkout rose about 4x at 18:00 (about 85 to 330-353 req/s), with CPU pinned at 94-100% and the worker queue hitting its 500 cap, so requests were rejected with 503s and admitted requests queued to about 2.9-3.0s p99. HPA wanted 34 replicas but was capped at maxReplicas 20, so capacity could not catch up.
   - Supporting evidence: `M15, M11, M13, M12, L0199, L0193, M05, C10`
   - Contradicting evidence: `M14`
   - Assumptions: The 4x increase is real campaign demand rather than client or retry amplification; Capacity at maxReplicas 20 is insufficient for about 340 req/s; Inventory latency rise (about 1.6x) is secondary rather than the origin
2. **api-gateway** - traffic_surge (confidence 0.15)
   - Mechanism: A burst of campaign or bot clients, with rate-limiter warnings from 17:57, pushed gateway traffic about 4x and forwarded it to checkout. This is the same surge as H-A located at the entry point, but gateway p99 and error rate stayed flat, so the gateway itself is not saturated.
   - Supporting evidence: `C10, M05, L0176, L0211, L0238, L0243`
   - Contradicting evidence: `M03, M02`
   - Assumptions: Gateway traffic is the origin rather than checkout capacity limits; Rate-limiter warnings reflect campaign clients
3. **inventory-service** - deployment_regression (confidence 0.12)
   - Mechanism: The v4.2.0 HTTP client library change could alter timeouts or pooling on the synchronous path from checkout, slowing reservations and holding checkout workers until the queue saturated. Sparse slow-reservation warnings appear on the checkout-to-inventory path.
   - Supporting evidence: `C09, D05, L0241, L0302, L0318`
   - Contradicting evidence: `M23, M25, M22`
   - Assumptions: The client library change affects checkout-to-inventory calls; Inventory p99 step at 18:00 is a consequence of the traffic surge rather than the cause; The v4.2.0 diff is unknown and could be benign

## Observed facts
- Checkout-service p99 latency was 308-332ms from 17:00 to 17:55, then 2931ms at 18:00 and 2788-3005ms through 18:30. `M13`
- Checkout-service error rate was 0.25-0.35% through 17:55, then 5.65% at 18:00 and 5.15-5.83% through 18:30. `M12`
- Checkout-service request rate was 82-87 req/s through 17:55 and 352.97 req/s at 18:00, staying at 328-345 req/s afterwards. `M15`
- Checkout-service CPU rose from about 40% to 93.7% at 18:00 and was 94-100% through 18:30; memory stayed at 56-60%. `M11, M14`
- Api-gateway request rate rose from about 417-435 to about 1625-1696 req/s at 18:00, while api-gateway p99 (173-184ms) and error rate (0.33-0.47%) stayed flat. `M05, M03, M02`
- The dominant checkout ERROR signature is 'rejecting request: worker pool saturated (queue 500/500) -> 503', first logged at 18:03:25Z and recurring through 18:30. `L0199, L0205, L0391`
- Checkout logs show 'HPA desired replicas 34 exceeds maxReplicas 20' repeatedly from 18:02:34 to 18:30:00. `L0193, L0390`
- Inventory-service p99 stepped from about 90ms to 136-145ms at 18:00, and its request rate rose from about 136 to 507-541 req/s; its error rate and CPU stayed flat. `M23, M25, M22, M21`
- Only 3 'slow inventory reservation' warnings (679ms, 1236ms, 1086ms) appear in checkout logs; retry lines are rare (2 in the window). `L0241, L0302, L0318, L0192, L0307`
- Api-gateway rate-limiter 'near burst limit' warnings begin at 17:57:26Z, before the 18:00 step; the api-gateway 503 search returned no records. `L0176, L0211, L0238, L0243`
- Change history in the 17:00-18:30 window shows only inventory-service deploy v4.2.0 (HTTP client library bump) at 17:25:00Z and api-gateway feature flag 'fall-sale' enabled at 17:55:00Z; no checkout-service change was recorded. `C09, C10`
- Health checks at 18:28Z returned healthy (HTTP /health 200) for all checked services; these are single shallow snapshots. `H01, H03, H07, H11`

## Assumptions
- The roughly 4x request-rate increase is real demand rather than client or retry amplification; no source breakdown was obtained.
- Checkout capacity at maxReplicas 20 is insufficient for about 340 req/s.
- Inventory latency rise (about 1.6x) is secondary to the checkout queueing rather than its origin.
- The inventory-service v4.2.0 client library change affects checkout-to-inventory calls, and its diff is unknown and could be benign.
- Shallow /health checks do not exercise the timeout, pooling or inventory call paths under load.
- Metrics at 5-minute resolution place onset in the 18:00 bucket; the exact second is unknown.

## Inferred conclusions
- A traffic surge at 18:00 saturated checkout's worker pool and CPU, with HPA capped at maxReplicas 20, producing the 503s and latency; this is the best-supported explanation but is not confirmed as the root cause. (confidence 0.50) `M15, M11, M13, L0199, L0193`
- The surge's source (campaign demand, bot or rate-limited clients, or retry amplification) is unidentified; timing alone cannot separate the 17:55 banner flag from the 18:00 email blast. (confidence 0.40) `L0176, C10, M05`
- Inventory-service latency is unlikely to be the sole cause, since its 1.6x rise and flat error rate do not fully account for the 2.9s checkout p99, but its contribution to queueing is unmeasured. (confidence 0.35) `M23, M13, L0241`
- The inventory-service v4.2.0 client library change remains a possible contributor through checkout's client timeouts or pooling, which inventory-side metrics cannot show; it is weakened but not ruled out. (confidence 0.15) `C09, M23, M22`
- The api-gateway alert is a propagation effect of checkout's 503s rather than an independent gateway fault. (confidence 0.45) `M03, M02, M01, M04`

## Remediation
- **immediate** - Raise checkout-service maxReplicas above 20 (target about 34 or more) and verify replicas scale, to relieve worker-pool saturation. _(HPA logs show desired replicas of 34 were capped at 20 throughout the incident while CPU stayed at 94-100%.)_
- **immediate** - Apply rate limiting or load shedding at api-gateway for the burst clients identified by rate-limiter warnings, and confirm whether traffic is campaign demand or retries. _(Reduces load on checkout while the trigger is unresolved; the rate-limiter bursts start at 17:57.)_
- **short_term** - Pull checkout request volume by client source, user agent, retry header and endpoint for 17:50-18:30, and checkout latency and worker-pool metrics per downstream call and instance. _(These are needed to settle whether the trigger is organic or retry-driven and whether inventory calls contribute to queueing.)_
- **short_term** - Obtain the inventory-service v4.2.0 client library diff (timeouts, pool sizes, retry policy) and test checkout-to-inventory call timeouts under load. _(The deploy at 17:25Z precedes onset and its effect on checkout's client path has not been measured.)_
- **long_term** - Review the campaign launch process so that traffic-generating marketing actions are coordinated with capacity planning and checkout autoscaling limits. _(The fall-sale flag and email blast coincided with the surge, indicating a missing capacity check.)_
- **long_term** - Make health checks exercise checkout write paths and the inventory call, not only HTTP /health. _(Current shallow checks reported healthy during a period of severe checkout latency and 503s.)_
- **long_term** - Add per-downstream latency and worker-pool utilisation and queue-depth metrics at sub-5-minute resolution for checkout-service. _(The current 5-minute, aggregate-only metrics cannot separate local queueing from slow downstream calls.)_

## Open questions
- Is the 4x request increase organic campaign demand, bot or client traffic, or retry amplification? The client-source breakdown was not obtained.
- How much of checkout's 2.9s p99 is inventory reservation latency versus local worker-pool queueing? No per-downstream or worker-pool series was retrieved.
- What did the inventory-service v4.2.0 client library change alter (timeouts, pool sizes, retry policy), and does it affect checkout's calls?
- Do api-gateway 503 records exist outside the 17:50-18:30 window, or is the absence of gateway 503 logs real?
- Do payment-service and auth-service latency and errors rise during 18:00-18:30? These were not queried.

## Data gaps and tool failures (10 shown, 33 reported)
- Tool budget exhausted after 6 calls, so no further queries were possible.
- No api-gateway 503 log lines were found (contains '503' at ERROR level returned 0). Gateway 503 signature and volume are therefore unverified. Gateway 503 rate is unknown.
- Downstream service metrics for inventory, payment and the worker pool were not queried. Downstream latency attribution is unverified.
- Per-endpoint and per-instance breakdowns for checkout latency were not retrieved, so it is unknown whether latency is concentrated in a subset of instances or endpoints.
- Log results were truncated: 30 of 46 checkout WARN/ERROR lines were returned, and the HPA warnings have no record IDs in the returned sample.
- Metrics are 5-minute resolution, so the onset is only known to the 18:00 bucket, not to the second.
- The 17:50-18:30 window for api-gateway 503s was narrow. A search over the full window may find gateway 503 lines outside it.
- Change history returned only changes in the 6h window; no visibility into what the v4.2.0 client library change actually modified (timeouts, pool sizes) or the volume of traffic after the email blast.
- Health checks are shallow (HTTP /health only) and do not exercise checkout write paths or inventory calls; they cannot confirm or exclude latency issues.
- 24 further gap report(s) in 24 group(s) omitted here (mostly about: metrics, returned, latency, queried, search, 503); the full list is in the run record.
