# Incident report S04

- **Status:** CONCLUSIVE (confidence 0.85, margin 0.70, 9 verified supporting and 0 contradicting evidence items (0%))
- **System:** baseline · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** agent_finished
- **Root cause:** `payment-provider` - dependency_failure (confidence 0.85)

## Summary
Checkout and gateway errors began abruptly at 16:00:00Z. Payment-service error rate jumped from about 0.2% to about 39-42%, and its logs show repeated 503 responses from the external payment provider's charges API. Checkout's 502s are the propagated result: every sampled checkout error is 'payment-service returned 502'. The payment provider's status page reports elevated Charges API errors, which points to an upstream provider outage rather than a change in our own services. Our own signals are secondary: payment-service latency rose to about 10s p99 from retries against the failing provider, and the search-service deploy at 15:40 shows no matching symptoms. Confidence is high but not verified, because we have no direct metrics or logs for the provider itself.

## Conclusion decision
- confidence 0.85, margin 0.70, 9 verified supporting and 0 contradicting evidence items (0%)
- Criteria: top `payment-provider / dependency_failure` confidence 0.85, margin 0.70, 9 verified supporting / 0 contradicting items (0% contradicting); 0 evidence-backed material critic objection(s), 0 non-blocking

## Ranked hypotheses
1. **payment-provider** - dependency_failure (confidence 0.85)
   - Mechanism: The external Charges API started returning 503s at about 16:00:00Z. payment-service retries each charge three times, which pushes p99 latency to about 10 s and trips its 'payment-provider' circuit breaker. Checkout then receives 502s from payment-service, and the gateway returns 5xx to customers.
   - Supporting evidence: `M33, M34, L0186, L0200, L0256, H10, L0188, M12, M02`
   - Contradicting evidence: none
   - Assumptions: The status page is accurate and the outage is on the provider side.; payment-service's own health checks are shallow.
2. **payment-service** - config_error (confidence 0.15)
   - Mechanism: A misconfigured retry, timeout or circuit-breaker setting in payment-service turns a partial provider degradation into a full failure. The retry and wait behaviour adds about 10 s of latency and causes checkout 502s.
   - Supporting evidence: `L0186, L0200, M34`
   - Contradicting evidence: none
   - Assumptions: Payment-service retry and breaker settings are inadequate for provider errors.
3. **search-service** - deployment_regression (confidence 0.05)
   - Mechanism: The v5.3.2 ranking-model deploy at 15:40Z caused slow search-index shard responses, and this propagated to checkout. This is unlikely because the errors start at 16:00 in the payment path and search is not in checkout's dependency list.
   - Supporting evidence: `C09, L0097, L0225`
   - Contradicting evidence: none
   - Assumptions: search-service may be a hidden dependency that is not in the dependency graph.

## Observed facts
- checkout-service error_rate jumped from about 0.35% at 15:55:00Z to 21.17% at 16:00:00Z and stayed between 19.85% and 22.47% through 16:30:00Z. `M12`
- api-gateway error_rate jumped from 0.37% at 15:55:00Z to 7.73% at 16:00:00Z, and api-gateway request_rate and CPU stayed flat. `M02, M05, M01`
- payment-service error_rate jumped from 0.17% at 15:55:00Z to 39.13% at 16:00:00Z and peaked at 41.94% at 16:10:00Z. `M33`
- payment-service latency_p99_ms rose from 464 ms at 15:55:00Z to 9857 ms at 16:00:00Z, while its CPU (about 33%), memory (about 54%) and request rate (about 59 req/s) stayed normal. `M34, M32, M35, M36`
- payment-service logs show 35 ERROR lines 'POST https://api.payprovider.example/v2/charges failed: 503 Service Unavailable (attempt 3/3)' starting 16:00:02Z. `L0186, L0192, L0308`
- checkout-service logs show 60 ERROR lines 'order # failed: payment-service returned 502 Bad Gateway' starting 16:00:27Z. `L0188, L0190, L0255`
- payment-service's circuit breaker for 'payment-provider' changed CLOSED -> OPEN at 16:02:04Z, 16:10:06Z, 16:17:50Z and 16:25:02Z. `L0200, L0256, L0312, L0368`
- The dependency health check reports payment-provider as 'degraded' with the status page message 'Elevated error rates on Charges API (investigating)'; payment-service, payments-db and checkout-service health checks return HTTP 200. `H10, H11, H12, H03`
- The only change in the window is search-service deploy v5.3.2 at 15:40:00Z. The last payment-service deploy (v3.1.3) was 2026-09-03T10:00:00Z. `C09, C05`
- search-service WARN logs show shard 3 slow responses (about 700-980 ms) at 15:32, 15:49, 15:51 and 16:05; search-service has no ERROR lines. `L0097, L0150, L0155, L0225`

## Assumptions
- The health checks are shallow and do not exercise the payment charge path or the provider's TLS and API behaviour.
- The status page reflects the real provider outage and is not stale.
- payment-provider has no metrics in this telemetry, so its state is known only from the status page and from payment-service's view of it.
- The 16:00 onset is the same time the provider began failing, since no change of ours lines up with it.
- payments-db is not involved, since its health check passes and payment-service CPU and memory are normal.

## Inferred conclusions
- The primary fault is the external payment provider's Charges API outage, which returns 503s. payment-service then retries (3 attempts), its latency rises, and its circuit breaker opens. Checkout surfaces this as 502s, and the gateway surfaces checkout's failures as 5xx. (confidence 0.85) `M33, M34, L0186, L0200, H10, L0188, M12, M02`
- The search-service v5.3.2 deploy is unlikely to be the cause. Its timing does not match the 16:00 onset, its WARN logs are minor and it has no errors, and checkout and payment failures start only at 16:00. (confidence 0.75) `C09, L0097, M12`
- Checkout-service and api-gateway resource saturation is not the cause. Their CPU, memory and request rate are flat across the onset, and their errors are downstream of payment-service. (confidence 0.80) `M11, M14, M01, M04, M15, M05`

## Remediation
- **immediate** - Fail over or route payment charges to a secondary payment provider, or enable a degraded-mode 'pay later' path, while the provider's Charges API is down. _(The provider outage is the root cause, and our own services cannot fix it.)_
- **immediate** - Tune payment-service retries and timeouts so they stop amplifying load against the failing provider, and make checkout return a clear payment-pending state instead of 502. _(Retries add latency (about 10 s p99) and tie up checkout threads.)_
- **immediate** - Post a status update to customers and track affected orders for reconciliation or retry once the provider recovers. _(Customers report failed payments.)_
- **short_term** - Confirm the provider incident with the vendor and monitor their status page for recovery. _(The health signal currently comes only from the status page.)_
- **short_term** - Add provider-level metrics and deep synthetic charge checks to payment-service monitoring. _(Today there is no direct provider telemetry, and health checks return 200 during the outage.)_
- **long_term** - Review the search-service shard 3 latency under v5.3.2 separately, without tying it to this incident. _(It is a minor, unrelated warning to track.)_
- **long_term** - Add multi-provider or failover support for payments, with circuit-breaker-aware checkout behaviour. _(This removes the single external dependency.)_

## Open questions
- Is the provider's Charges API outage confirmed by the vendor, and what is its estimated recovery time?
- Why do payment-service's own health checks return 200 while charges fail (shallow health check)?
- Is the 15:40 search-service deploy coincidental, or does it affect payment or checkout paths indirectly?
- Did payment-service's retry and timeout settings allow the 9.8-10 s p99 latency and thread pool buildup?

## Data gaps and tool failures (0 shown, 0 reported)
_None._
