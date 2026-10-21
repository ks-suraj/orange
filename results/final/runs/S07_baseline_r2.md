# Incident report S07

- **Status:** CONCLUSIVE (confidence 0.80, margin 0.40, 8 verified supporting and 2 contradicting evidence items (20%))
- **System:** baseline · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** agent_finished
- **Root cause:** `checkout-service` - traffic_surge (confidence 0.80)

## Summary
Checkout-service p99 latency rose from about 320 ms to about 2.9 s and 503s began at 18:00:00Z, when request volume into api-gateway quadrupled (about 420 to about 1,650 req/s). The surge coincides with the 'fall-sale' homepage banner flag and a 2.1M-customer email blast, both launched by marketing-ops at 17:55–18:00. Checkout's worker pool saturated at 500/500 and the HPA wanted 34 replicas against a max of 20, so the capacity ceiling is the immediate bottleneck. Inventory-service also slowed in the same minute on a 4x request jump, with cache-miss storms, which adds to checkout's per-request time. The inventory v4.2.0 deploy at 17:25 shows no matching symptom change and is a weak lead. Health checks are green, but they are shallow and do not reflect saturation.

## Conclusion decision
- confidence 0.80, margin 0.40, 8 verified supporting and 2 contradicting evidence items (20%)
- Criteria: top `checkout-service / traffic_surge` confidence 0.80, margin 0.40, 8 verified supporting / 2 contradicting items (20% contradicting); 0 evidence-backed material critic objection(s), 0 non-blocking

## Ranked hypotheses
1. **checkout-service** - traffic_surge (confidence 0.80)
   - Mechanism: The marketing-driven traffic step (fall-sale flag plus email blast) at 18:00 quadrupled checkout load. The worker pool hit 500/500 and rejected requests with 503s, and the HPA could not scale past maxReplicas 20 when it wanted 34, so latency rose to about 2.9 s.
   - Supporting evidence: `M05, M15, M13, M12, L0199, L0193, C10, M11`
   - Contradicting evidence: `H03, M01`
   - Assumptions: The traffic came from the campaign, which is not directly tagged in the data.; maxReplicas 20 is the effective limit.
2. **inventory-service** - resource_exhaustion (confidence 0.40)
   - Mechanism: Inventory cache misses and reservation handling slowed under the surge. Checkout's synchronous reservation calls then held workers longer, which contributed to pool saturation.
   - Supporting evidence: `M25, M23, L0147, L0210, L0079`
   - Contradicting evidence: `M22, M24, M21`
   - Assumptions: Inventory latency is a cause, not only a symptom, of the surge.; Checkout's latency is mostly from the inventory call.
3. **inventory-service** - deployment_regression (confidence 0.15)
   - Mechanism: The v4.2.0 HTTP client library bump at 17:25 introduced latency or cache-miss behaviour in inventory, which slowed checkout.
   - Supporting evidence: `C09, L0079`
   - Contradicting evidence: `M23, L0011, M22, M21`
   - Assumptions: The deploy changed the client behaviour, which is not confirmed by the data.

## Observed facts
- api-gateway request_rate rose from about 417 req/s (17:55) to 1625 req/s at 18:00:00Z and stayed at about 1600–1700 req/s through 18:30. `M05`
- checkout-service request_rate rose from 85 req/s to 353 req/s at 18:00:00Z, and checkout p99 latency rose from 321 ms to 2931 ms in the same 5-minute bucket. `M15, M13`
- checkout-service error_rate went from about 0.3% to 5.65% at 18:00:00Z and was 5.83% at 18:30. `M12`
- checkout-service cpu_pct went from about 40% to 93.7% at 18:00 and reached 99.77% at 18:30; memory stayed about 56–60%. `M11, M14`
- Checkout logs show 30 rejections 'worker pool saturated (queue 500/500) -> 503' between 18:03:25 and 18:19:09. `L0199, L0205, L0314`
- HPA warned 'desired replicas 34 exceeds maxReplicas 20' eight times from 18:02:34 to 18:30:00. `L0193, L0390`
- inventory-service request_rate rose from about 136 to about 508 req/s at 18:00, and its p99 latency rose from about 91 ms to 142 ms; its health check stayed green. `M25, M23, H07`
- Inventory logs show cache miss storms (21–83 misses/s per sku prefix) from 17:03 onward, with reservation expiries at 17:25:49 and 18:04:45. `L0011, L0147, L0079, L0210`
- Change history shows inventory-service deploy v4.2.0 at 17:25 ('bump HTTP client library'), and the api-gateway 'fall-sale' feature flag at 17:55. `C09, C10`
- The last checkout-service deploy (v2.13.4) was 2026-09-06T22:00Z, about 20 hours before onset; api-gateway error_rate and latency stayed flat through the incident. `C07, M02, M03`
- Health checks for api-gateway, checkout-service, payment-service, inventory-service, auth-service and notification-queue all returned HTTP 200 at 18:28. `H01, H03, H11, H07, H02, H08`

## Assumptions
- The 'fall-sale' flag and email blast are the cause of the 18:00 traffic step; the data does not link traffic sources directly.
- The health checks are shallow HTTP /health probes that do not exercise saturation, reservation writes or TLS.
- The 500-slot worker queue and the maxReplicas of 20 are the configured limits; no other config changed in the window.
- payment-service is not the bottleneck, since its health is green and its logs show only a few retries.

## Inferred conclusions
- Primary cause: a marketing-driven traffic surge (fall-sale flag plus email blast) pushed about 4x load into checkout, which exhausted its worker pool and its HPA ceiling (34 desired vs 20 max), producing 503s and latency. (confidence 0.80) `M05, M15, L0199, L0193, C10`
- Secondary contributor: inventory-service slowed under the same surge (cache miss storms, reservation expiries), which lengthens checkout's synchronous calls and holds workers longer. (confidence 0.50) `M25, M23, L0147, L0210`
- The inventory v4.2.0 deploy at 17:25 is unlikely to be the root cause: its latency and error rate were flat until the 18:00 traffic step, and the cache misses began before the deploy. (confidence 0.30) `C09, L0011, M23`

## Remediation
- **immediate** - Raise checkout-service maxReplicas above 34 (or temporarily lift the cap) and confirm the new pods are scheduled and ready. _(The HPA wants 34 replicas but is capped at 20, and the worker pool is saturated.)_
- **immediate** - Consider throttling or pausing the fall-sale banner flag and the email blast, or enabling request shedding at api-gateway for checkout, to bring load back toward the normal ~420 req/s. _(The traffic step is the trigger; reducing it relieves all downstream services.)_
- **short_term** - Check inventory-service capacity and warm the SKU cache for the campaign's hot SKUs, and watch reservation expiry rates. _(Inventory latency rose with the surge and its cache misses are driving slow reservations.)_
- **short_term** - Review the checkout worker pool size and the 500-slot queue, and the behaviour of 503s when saturated. _(The queue limit is what turns the overload into 503s.)_
- **long_term** - Require load-test and capacity sign-off for marketing launches, and add a campaign-aware pre-scale of checkout and inventory. _(The campaign was launched without a capacity plan, so the surge was not anticipated.)_
- **long_term** - Deepen health checks so they exercise saturation and dependency calls, not just HTTP 200 on /health. _(All health checks showed green during a P2 outage.)_

## Open questions
- What is the actual split of the 4x traffic between the banner flag and the email blast, and can it be confirmed from gateway logs?
- Why does the HPA's max of 20 sit below the 34 desired replicas, and was that cap set deliberately?
- Did the card-declined rejections (L0027, L0195) rise with the surge, and are they related?
- Did the inventory cache miss storms start at 17:03, before the v4.2.0 deploy, and what caused them?

## Data gaps and tool failures (0 shown, 0 reported)
_None._
