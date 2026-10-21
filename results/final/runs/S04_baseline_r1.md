# Incident report S04

- **Status:** CONCLUSIVE (confidence 0.80, margin 0.70, 8 verified supporting and 0 contradicting evidence items (0%))
- **System:** baseline · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** agent_finished
- **Root cause:** `payment-provider` - dependency_failure (confidence 0.80)

## Summary
Checkout and API-gateway 5xx began at 16:00:00Z, and every checkout failure sampled in the logs is a 502 from payment-service. payment-service in turn is failing its calls to the external payment-provider with 503s, and its 'payment-provider' circuit breaker opened. The provider's own status page reports degraded Charges API errors. The most likely origin is the external payment provider outage, not the internal services. The search-service v5.3.2 deploy at 15:40 is coincident but has no visible path to payment or checkout.

## Conclusion decision
- confidence 0.80, margin 0.70, 8 verified supporting and 0 contradicting evidence items (0%)
- Criteria: top `payment-provider / dependency_failure` confidence 0.80, margin 0.70, 8 verified supporting / 0 contradicting items (0% contradicting); 0 evidence-backed material critic objection(s), 0 non-blocking

## Ranked hypotheses
1. **payment-provider** - dependency_failure (confidence 0.80)
   - Mechanism: The external payment provider's Charges API began failing with 503s at about 16:00Z. payment-service retries three times per charge, its latency rises to about 10 s, and the circuit breaker opens. checkout-service then fails orders with payment-service 502s, which the gateway reports as 5xx.
   - Supporting evidence: `L0186, M33, M34, L0200, H10, L0188, M02, M12`
   - Contradicting evidence: none
   - Assumptions: The status page is accurate and the outage is ongoing at 16:28Z.; No other caller of the provider is involved.
2. **payment-service** - config_error (confidence 0.10)
   - Mechanism: An internal payment-service issue (for example, a TLS or client config for the provider, or retry/timeout settings) causes the provider calls to fail with 503s, and checkout shows 502s.
   - Supporting evidence: `L0186, L0200, M34`
   - Contradicting evidence: none
   - Assumptions: The change history covers all config changes to payment-service.
3. **search-service** - deployment_regression (confidence 0.05)
   - Mechanism: The v5.3.2 ranking model refresh loads the system or adds latency that spills over to checkout.
   - Supporting evidence: `C09`
   - Contradicting evidence: none
   - Assumptions: There is a hidden dependency that the graph does not show.

## Observed facts
- checkout-service error_rate was flat at about 0.24–0.35% until 15:55:00Z, then jumped to 21.17% at 16:00:00Z and stayed between 19.85% and 22.47% through 16:30:00Z. `M12`
- api-gateway error_rate went from 0.33–0.45% before 16:00:00Z to 7.73% at 16:00:00Z, with values of 7.47–8.28% through 16:30:00Z. `M02`
- payment-service error_rate jumped from 0.20% at 15:55:00Z to 39.13% at 16:00:00Z and peaked at 41.94% at 16:10:00Z. `M33`
- payment-service latency_p99 rose from 464.17 ms at 15:55:00Z to 9857.35 ms at 16:00:00Z and was 10355.04 ms at 16:30:00Z. `M34`
- Checkout logs show 'order ... failed: payment-service returned 502 Bad Gateway' errors starting at 16:00:27Z. `L0188, L0190`
- payment-service logs show 'POST https://api.payprovider.example/v2/charges failed: 503 Service Unavailable (attempt 3/3)' starting at 16:00:02Z, which is before the first checkout 502. `L0186, L0192`
- The payment-service circuit breaker 'payment-provider' changed CLOSED -> OPEN at 16:02:04Z, with further OPEN transitions at 16:10:06Z, 16:17:50Z and 16:25:02Z. `L0200, L0256, L0312, L0368`
- The payment-provider dependency has health 'degraded' with status page text 'Elevated error rates on Charges API (investigating)'. The health checks for payment-service, payments-db, checkout-service, api-gateway and auth-service all returned HTTP 200 or SELECT 1 OK at 16:28:00Z. `H10, H11, H12, H01, H03`
- payment-service CPU (about 32–34%), memory (about 53–57%) and request rate (about 58–62 req/s) stayed in their normal ranges across the incident window. `M32, M35, M36`
- The only change in the window is search-service deploy v5.3.2 ('ranking model refresh') at 15:40:00Z. The only other change is a Kubernetes node pool upgrade at 07:00:00Z. `C09, C08`
- search-service logs show only four shard-3 latency WARNs (703–983 ms) between 15:32 and 16:05, and it has no dependency edge to payment-service or checkout-service. `L0097, L0150, L0155, L0225`

## Assumptions
- The payment-provider status-page entry reflects the real provider outage, and the provider is not a service with its own telemetry here.
- The health checks are shallow and do not exercise the payment charge path, so 'healthy' for payment-service does not prove it can charge successfully.
- payment-service is the only caller of payment-provider in this window.
- The 502s seen by checkout-service are passed through from payment-service's failed upstream calls.

## Inferred conclusions
- The primary origin is the external payment provider's Charges API outage. payment-service surfaces it as 503s and its circuit breaker opens, and checkout and gateway 5xx are downstream propagation of that failure. (confidence 0.80) `L0186, L0200, H10, M33, L0188, M02`
- The search-service v5.3.2 deploy at 15:40 is unlikely to be the cause. Its timing is about 20 minutes before onset, it has no dependency path to checkout or payment, and its only WARNs are modest shard latency. (confidence 0.85) `C09, L0097, M12`
- Internal payment-service fault is unlikely as a primary cause. Its CPU, memory and request rate are flat, its health check is OK, and the failures are 503s from the provider call. (confidence 0.70) `M32, M35, M36, H11, L0186`

## Remediation
- **immediate** - Confirm the payment-provider outage with the provider's status and incident channel, and fail over to a secondary payment provider or route to a degraded-mode queue if one is available. _(The root failure is outside our systems, so only a failover or queueing stops the customer-facing payment failures.)_
- **immediate** - Keep the payment-provider circuit breaker open and reduce the retry count (3 attempts) and the 10 s latency, so checkout fails fast and threads are not exhausted. _(payment-service p99 is about 10 s, and the retries add load and latency.)_
- **immediate** - Tell customers about the payment failures and suppress automatic retries of failed orders until the provider recovers. _(Customers are reporting failed payments.)_
- **short_term** - Add a payment-provider dependency health check that exercises a real charge path (in a sandbox) and alert on the circuit breaker opening. _(Current health checks return 200 while payments fail, so they hide the outage.)_
- **long_term** - Add a multi-provider payment fallback and timeouts/bulkheads on the checkout to payment call. _(Prevents a single external provider from causing a P1 outage.)_

## Open questions
- Is the provider outage confirmed by the provider's own telemetry? Only the status page entry was returned.
- Why does payment-service return 502 to checkout while its own logs show 503 from the provider? The mapping should be verified.
- Did any failures come from a provider-side change rather than a generic outage?
- Is search-service v5.3.2 really unrelated? Its timing is coincidental and no direct path exists in the data.

## Data gaps and tool failures (0 shown, 0 reported)
_None._
