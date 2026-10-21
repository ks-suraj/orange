# Incident report S07

- **Status:** CONCLUSIVE (confidence 0.75, margin 0.60, 8 verified supporting and 2 contradicting evidence items (20%))
- **System:** baseline · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** agent_finished
- **Root cause:** `checkout-service` - traffic_surge (confidence 0.75)

## Summary
Checkout-service went from about 85 to 350 req/s at 18:00:00Z, coinciding with the api-gateway 'fall-sale' banner flag and the marketing email blast. Its HPA wanted 34 replicas but was capped at maxReplicas 20, so the worker pool (queue 500/500) saturated and checkout began returning 503s, with p99 rising from about 320ms to about 2.9s. Downstream services (payment, inventory) show only modest changes and report healthy, so the primary bottleneck is checkout's capacity under a traffic surge. The inventory v4.2.0 deploy at 17:25 is a weaker, secondary contributor at most. Data covers only 17:00–18:30 and I did not check checkout's replica or deployment configuration directly.

## Conclusion decision
- confidence 0.75, margin 0.60, 8 verified supporting and 2 contradicting evidence items (20%)
- Criteria: top `checkout-service / traffic_surge` confidence 0.75, margin 0.60, 8 verified supporting / 2 contradicting items (20% contradicting); 0 evidence-backed material critic objection(s), 0 non-blocking

## Ranked hypotheses
1. **checkout-service** - traffic_surge (confidence 0.75)
   - Mechanism: A marketing campaign at 18:00 raised api-gateway traffic about 4x, pushing checkout to about 350 req/s. HPA wanted 34 replicas but was capped at 20, so the worker pool hit its 500-request queue limit, requests were rejected with 503, and latency grew because of queuing.
   - Supporting evidence: `M15, M05, C10, L0193, L0199, M13, M12, M11`
   - Contradicting evidence: `H03, M14`
   - Assumptions: The traffic step came from the marketing campaign.; maxReplicas 20 is the binding limit.
2. **inventory-service** - deployment_regression (confidence 0.15)
   - Mechanism: The v4.2.0 HTTP client library bump slowed inventory reservations, so checkout requests held worker threads longer and filled the pool.
   - Supporting evidence: `C09, M23, L0079, L0210`
   - Contradicting evidence: `L0011, M23, M25`
   - Assumptions: The client library change has a latency effect that only shows under load.
3. **inventory-service** - resource_exhaustion (confidence 0.10)
   - Mechanism: Cache-miss storms in inventory raised its latency under the 4x load, adding to checkout's time per request and worker-pool occupancy.
   - Supporting evidence: `L0147, L0242, M23, M25`
   - Contradicting evidence: `M21, M24`
   - Assumptions: Cache misses are load-dependent.

## Observed facts
- checkout-service request_rate rose from about 85 req/s (17:55:00Z 85.48) to 352.97 req/s at 18:00:00Z, and stayed at 328–345 req/s through 18:30:00Z. `M15`
- api-gateway request_rate rose from 417.09 req/s at 17:55:00Z to 1625.13 req/s at 18:00:00Z, while api-gateway cpu stayed around 37–39%. `M05, M01`
- A feature_flag change enabling the 'fall-sale' homepage banner on api-gateway was completed at 17:55:00Z, with an email blast to 2.1M customers scheduled at 18:00. `C10`
- checkout-service p99 latency went from about 321ms (17:55:00Z) to 2931ms at 18:00:00Z, and stayed between 2788 and 3005ms through 18:30:00Z. `M13`
- checkout-service error_rate rose from 0.32% (17:55:00Z) to 5.65% at 18:00:00Z, and was 5.83% at 18:30:00Z. `M12`
- checkout-service logs show 30 'rejecting request: worker pool saturated (queue 500/500) -> 503' errors, first at 18:03:25Z and continuing to 18:19:09Z. `L0199, L0314`
- checkout-service logs 8 HPA warnings 'desired replicas 34 exceeds maxReplicas 20' from 18:02:34Z to 18:30:00Z. `L0193, L0390`
- checkout-service cpu_pct rose from about 40% to 93.7% at 18:00:00Z and reached 99.77% at 18:30:00Z. `M11`
- checkout-service memory_pct stayed between 56% and 60%. `M14`
- inventory-service request_rate rose from about 135 req/s to about 507 req/s at 18:00:00Z, and its p99 latency rose from about 91ms to 142ms at the same time. `M25, M23`
- inventory-service deploy v4.2.0 (HTTP client library bump) was completed at 17:25:00Z; inventory cache-miss-storm warnings were already present at 17:03:19Z, before the deploy. `C09, L0011`
- payment-service latency_p99 stayed around 437–466ms, error_rate stayed around 0.2%, and request_rate was about 60 req/s throughout 17:50–18:30. `M34, M33, M36`
- Health checks for checkout-service, api-gateway, payment-service, inventory-service, auth-service and notification-queue all returned healthy (HTTP /health 200) at 18:28:00Z. `H03, H01, H11, H07, H02, H08`

## Assumptions
- Health checks are shallow and do not reflect saturation of the checkout worker pool or the 503 path.
- The api-gateway flag change and the email blast are the cause of the 18:00 traffic step; no direct link has been confirmed in the telemetry.
- maxReplicas 20 is an intentional or stale HPA cap that prevented scale-out to the desired 34 replicas.
- The 'card declined by issuer' errors are a normal background rate and not part of the incident.

## Inferred conclusions
- The primary cause is a marketing-driven traffic surge (~4x at api-gateway, ~4x at checkout) that exceeded checkout's capacity, because HPA was capped at maxReplicas 20 while desired was 34, which exhausted the worker pool and produced the 503s and latency spike. (confidence 0.75) `M15, M05, L0193, L0199, M13, M12`
- The inventory-service v4.2.0 deploy is a weak secondary candidate: its latency rise coincides with the 18:00 traffic step rather than the 17:25 deploy, and its cache-miss storms predate the deploy, so it is unlikely to be the main cause. (confidence 0.15) `C09, L0011, M23, M25`
- Inventory latency increase probably contributes to checkout's slow requests under load, but it does not explain the saturation on its own. (confidence 0.30) `M23, L0011`

## Remediation
- **immediate** - Raise checkout-service HPA maxReplicas above 34 (or temporarily set replicas manually) so the desired count can be met. _(HPA desired 34 is being capped at 20, which is the direct bottleneck.)_
- **immediate** - Ask marketing-ops to throttle or pause the 'fall-sale' banner and the email blast, or enable rate limiting at api-gateway for the checkout route. _(Reduces the incoming 4x load while capacity is restored.)_
- **immediate** - Increase checkout worker pool/queue capacity or add load shedding with a clear 503/Retry-After response, and watch checkout cpu (about 100%). _(Stops queue saturation from cascading into latency for all requests.)_
- **short_term** - Verify checkout's resource requests and node capacity so the scale-out to 34 replicas can actually schedule. _(Scaling to the desired count may fail on capacity limits that are not visible in the data.)_
- **short_term** - Investigate the inventory cache-miss storms and the v4.2.0 HTTP client change; roll back if correlated with latency. _(Inventory latency rose about 50ms and contributes to slow checkout calls.)_
- **long_term** - Make health checks exercise the checkout request path and worker-pool saturation so they stop reporting healthy during 503s. _(Health checks were green during a full outage of checkout requests.)_
- **long_term** - Require capacity review and load-test sign-off for marketing launches that email large customer lists, and align HPA maxReplicas with that load. _(The campaign launch was not coordinated with capacity planning.)_

## Open questions
- What is the checkout-service maxReplicas configuration history, and was the value 20 changed recently? The change history only covered deploys and flags within this window.
- Did the email blast at 18:00 directly cause the api-gateway traffic step, and was the flag rollout a factor?
- Are the checkout 503s all from worker pool saturation, or is there also a timeout on inventory calls?
- What caused the inventory cache-miss storms before the 17:25 deploy?
- Did the 'card declined' errors change in volume after 18:00?

## Data gaps and tool failures (0 shown, 0 reported)
_None._
