# Incident report S07

- **Status:** CONCLUSIVE (confidence 0.80, margin 0.55, 7 verified supporting and 1 contradicting evidence items (12%))
- **System:** baseline · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** agent_finished
- **Root cause:** `checkout-service` - traffic_surge (confidence 0.80)

## Summary
Checkout-service latency and 503s began at 18:00:00Z, when api-gateway request rate jumped from about 420 to about 1,650 req/s at the same moment the marketing 'fall-sale' banner flag was enabled ahead of a 2.1M-recipient email blast. Checkout's worker pool saturated at 500/500 and it rejected requests with 503, while its HPA wanted 34 replicas but was capped at maxReplicas 20. The traffic surge exceeded checkout's provisioned capacity, which is the most likely origin. Inventory-service latency rose and shows cache-miss storms, but it looks like a downstream consequence of the same surge rather than an independent fault. Health checks report healthy throughout, so they do not reflect the saturation.

## Conclusion decision
- confidence 0.80, margin 0.55, 7 verified supporting and 1 contradicting evidence items (12%)
- Criteria: top `checkout-service / traffic_surge` confidence 0.80, margin 0.55, 7 verified supporting / 1 contradicting items (12% contradicting); 0 evidence-backed material critic objection(s), 0 non-blocking

## Ranked hypotheses
1. **checkout-service** - traffic_surge (confidence 0.80)
   - Mechanism: The fall-sale campaign raised api-gateway traffic about 4x at 18:00. Checkout's CPU and worker pool saturated, and the HPA was capped at 20 replicas while it wanted 34, so the queue filled and requests were rejected with 503, with latency rising to about 2.9 s.
   - Supporting evidence: `M05, M15, M11, M13, L0199, L0193, C10`
   - Contradicting evidence: `L0011`
   - Assumptions: The campaign traffic is the cause of the 18:00 step, not a coincident event.
2. **inventory-service** - resource_exhaustion (confidence 0.25)
   - Mechanism: Inventory's cache-miss storms and higher latency slow reservation calls, holding checkout workers longer and filling the pool. Inventory's CPU and error rate stayed flat, so this is weaker.
   - Supporting evidence: `M23, L0011, L0079, L0210`
   - Contradicting evidence: `M22, M21, M25`
   - Assumptions: Slow inventory calls hold checkout worker threads for longer.
3. **inventory-service** - deployment_regression (confidence 0.10)
   - Mechanism: The v4.2.0 HTTP client library bump might have added latency to inventory, which then slowed checkout. The deploy preceded onset by 35 minutes, but no inventory change appeared at 17:25.
   - Supporting evidence: `C09`
   - Contradicting evidence: `M23, M22`
   - Assumptions: Latency from the library change is delayed rather than immediate.

## Observed facts
- api-gateway request_rate rose from about 417 req/s (17:55) to 1,625 req/s at 18:00:00 and stayed about 1,600-1,700 req/s through 18:30. `M05`
- checkout-service request_rate rose from 85 req/s (17:55) to 353 req/s at 18:00:00 and stayed 328-345 req/s. `M15`
- checkout-service cpu_pct jumped from about 40% to 93.7% at 18:00 and reached 99.77% at 18:30. `M11`
- checkout-service p99 latency went from about 320 ms to 2,931 ms at 18:00 and was 2,788 ms at 18:30; error_rate rose from about 0.3% to 5.65%. `M13, M12`
- checkout-service logged 30 'worker pool saturated (queue 500/500) -> 503' rejections, the first at 18:03:25. `L0199, L0205, L0213`
- checkout-service logged 8 HPA warnings 'desired replicas 34 exceeds maxReplicas 20', the first at 18:02:34. `L0193, L0309`
- The 18:00 api-gateway feature flag change enabled the 'fall-sale' homepage banner for a marketing email blast to 2.1M customers at 18:00. `C10`
- inventory-service request_rate rose from about 136 to about 508-540 req/s at 18:00; its p99 latency rose from about 90 ms to about 140 ms; its error rate stayed 0.15-0.26%. `M25, M23, M22`
- inventory-service logged 10 'cache miss storm' warnings, the first at 17:03:19, and 2 'reservation expired before confirmation' errors. `L0011, L0079, L0210`
- Health checks for checkout-service, api-gateway, payment-service, inventory-service, auth-service and notification-queue all returned HTTP 200 at 18:28. `H01, H02, H03, H07, H08, H11`
- A deploy of inventory-service v4.2.0 (HTTP client library bump) completed at 17:25, 35 minutes before the 18:00 onset; inventory latency and error rate did not change at 17:25. `C09, M23, M22`
- checkout-service logged 'card declined by issuer' errors at 17:08 and 18:02, before and at onset, and 3 retries to payment-service. `L0027, L0195`
- checkout-service memory_pct stayed between 56% and 60% throughout the window. `M14`

## Assumptions
- The HPA max of 20 is a configured ceiling that was not raised for the campaign; the change history shows no HPA or config change for checkout.
- The worker pool size per pod is fixed, so the 500-slot queue caps throughput regardless of CPU.
- Health checks are shallow and do not exercise checkout's worker pool or the saturated request path.
- The 17:55 flag change and the 18:00 email blast are the same campaign; the email timing is taken from the flag description, not from separate traffic logs.

## Inferred conclusions
- The primary cause is a traffic surge of about 4x from the 'fall-sale' campaign launch, which saturated checkout-service's worker pool and CPU while the HPA was capped at 20 replicas. (confidence 0.80) `M05, M15, M11, L0199, L0193, C10`
- Inventory-service latency and cache-miss storms are a secondary effect of the surge (inventory request rate also 4x), not an independent origin, since its CPU and error rate stayed flat. (confidence 0.60) `M25, M23, L0011`
- The inventory v4.2.0 deploy at 17:25 is unlikely to be the cause, because inventory's latency and errors did not move at 17:25 and its onset tracks the 18:00 traffic step. (confidence 0.70) `C09, M23, M22`
- The card-declined errors and the expired-TLS pattern from a past incident are not supported as causes here: the declines predate the surge at the baseline rate, and no TLS errors appear in the telemetry reviewed. (confidence 0.50) `L0027, L0195, P05`

## Remediation
- **immediate** - Raise checkout-service maxReplicas above 20 (the HPA wants 34) and confirm the node pool can schedule the extra pods. _(The HPA is already requesting 34 replicas and is blocked by the ceiling.)_
- **immediate** - Reduce or throttle the fall-sale banner / campaign traffic to checkout (for example, roll back flag C10 or shift the email blast to a gradual send) until capacity is restored. _(The surge is the trigger and is ongoing at about 1,650 req/s at the gateway.)_
- **immediate** - Shed load at api-gateway for checkout routes, returning a controlled response instead of queuing up to 500 requests. _(Limits latency for admitted requests while the pool is saturated.)_
- **short_term** - Watch inventory-service cache-miss rates and warm the SKU cache for campaign items. _(Reduces the secondary inventory latency and reservation expiries.)_
- **short_term** - Load-test checkout at 4x expected campaign traffic and size the worker pool and HPA to match, with autoscaling headroom. _(Prevents recurrence of the same saturation at the next campaign.)_
- **long_term** - Add a checkout saturation / HPA-capped alert and a campaign-launch traffic review gate between marketing and engineering. _(Current health checks showed healthy while checkout returned 503s, so detection depends on latency alerts.)_

## Open questions
- Is the 18:00 surge entirely from the email blast, or are there bot or retry storms as well? Gateway logs were not queried.
- Why did the HPA not add capacity earlier, and what is the node-pool capacity limit?
- Does the worker-pool size per pod match the stated 500 queue limit?
- Do the 'card declined' errors at 17:08 and 18:02 rise above their baseline rate after onset?
- Why does inventory cache-miss storm appear from 17:03, before the surge?

## Data gaps and tool failures (0 shown, 0 reported)
_None._
