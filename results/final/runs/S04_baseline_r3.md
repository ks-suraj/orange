# Incident report S04

- **Status:** CONCLUSIVE (confidence 0.85, margin 0.70, 10 verified supporting and 0 contradicting evidence items (0%))
- **System:** baseline · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** agent_finished
- **Root cause:** `payment-provider` - dependency_failure (confidence 0.85)

## Summary
Checkout and payment failures start at 16:00:00Z and originate in the external payment provider's Charges API, which returns 503s. payment-service retries to 3/3 and its 'payment-provider' circuit breaker opens, so checkout-service gets 502s from payment-service, and api-gateway surfaces them as 5xx. payment-service's own metrics show a jump in error rate to about 40% and p99 latency to about 10s starting at the same minute. The provider's status page reports elevated Charges API errors, which fits. Health checks are shallow and show everything healthy, so they do not reflect this failure. A search-service deploy at 15:40Z and a payment-service deploy on 09-03 were checked and do not line up with the onset.

## Conclusion decision
- confidence 0.85, margin 0.70, 10 verified supporting and 0 contradicting evidence items (0%)
- Criteria: top `payment-provider / dependency_failure` confidence 0.85, margin 0.70, 10 verified supporting / 0 contradicting items (0% contradicting); 0 evidence-backed material critic objection(s), 0 non-blocking

## Ranked hypotheses
1. **payment-provider** - dependency_failure (confidence 0.85)
   - Mechanism: The external payment provider's Charges API started returning 503s at about 16:00Z. payment-service retries to 3/3 and then fails, so its error rate reaches about 40% and p99 latency about 10s. Its circuit breaker opens, and checkout-service returns 502s for failed orders, which api-gateway surfaces as 5xx.
   - Supporting evidence: `L0186, L0308, M33, M34, L0200, L0256, H10, L0188, M12, M02`
   - Contradicting evidence: none
   - Assumptions: The provider has no telemetry in this dataset.; The status page entry is accurate.
2. **payment-service** - config_error (confidence 0.15)
   - Mechanism: A payment-service configuration or retry/timeout setting turns a partial provider degradation into a full outage, for example by amplifying retries and holding requests open for about 10s. This is a lower-probability alternative because the 503s originate at the provider.
   - Supporting evidence: `M34, L0186, L0256`
   - Contradicting evidence: none
   - Assumptions: payment-service's retry/timeout configuration has not changed, since no config change is recorded.
3. **payment-service** - certificate_expiry (confidence 0.05)
   - Mechanism: An expired TLS certificate causes failed calls to the payment path, as in past incident P06. The log signature is 503 rather than TLS handshake failure, so this is unlikely.
   - Supporting evidence: `P06`
   - Contradicting evidence: `L0186, L0308`
   - Assumptions: The 503 responses are not caused by a TLS error, based only on the log text.

## Observed facts
- checkout-service error_rate jumped from about 0.35% at 15:55:00Z to 21.17% at 16:00:00Z and stayed at about 20-22% through 16:30:00Z. `M12`
- api-gateway error_rate jumped from 0.37% at 15:55:00Z to 7.73% at 16:00:00Z; api-gateway CPU, memory and request rate stayed in their normal ranges. `M02, M01, M04, M05`
- payment-service error_rate rose from 0.17% at 15:55:00Z to 39.13% at 16:00:00Z, peaking at 41.94% at 16:10:00Z. `M33`
- payment-service latency_p99 rose from about 465ms at 15:55:00Z to 9857ms at 16:00:00Z and stayed near 10s through 16:30:00Z. `M34`
- checkout-service logs show 60 ERROR lines of the form 'order failed: payment-service returned 502 Bad Gateway', starting at 16:00:27Z. `L0188, L0190, L0255`
- payment-service logs show 'POST https://api.payprovider.example/v2/charges failed: 503 Service Unavailable (attempt 3/3)' errors starting at 16:00:02Z. `L0186, L0308`
- payment-service logged 4 state changes of circuit breaker 'payment-provider' from CLOSED to OPEN, at 16:02:04Z, 16:10:06Z, 16:17:50Z and 16:25:02Z. `L0200, L0256, L0312, L0368`
- The dependency graph lists payment-provider with status 'degraded' and the status page message "Elevated error rates on Charges API (investigating)"; payment-service, payments-db, checkout-service and api-gateway all report healthy /health 200 checks at 16:28:00Z. `H10, H11, H12, H03, H01`
- The only change in the window is search-service deploy v5.3.2 at 15:40:00Z; search-service error_rate stayed at 0.15-0.23% throughout. payment-service's last deploy (v3.1.3) was 2026-09-03T10:00:00Z. `C09, M43, C05`
- payment-service CPU (about 32-34%), memory (about 53-57%) and request rate (about 58-62 req/s) stayed flat across the 16:00Z onset. `M32, M35, M36`

## Assumptions
- payment-provider has no telemetry in this dataset, so its outage is inferred from the status page and from the 503 responses that payment-service receives.
- The health checks are shallow (HTTP /health only) and do not exercise the payment provider path or TLS, so their 'healthy' results do not rule out this failure.
- The payment-provider status page entry is accurate and current as of 16:28:00Z.

## Inferred conclusions
- The primary fault originates at the external payment provider's Charges API. payment-service fails fast with 503s, retries, and opens its circuit breaker. checkout-service then returns 502s for failed orders, which api-gateway surfaces as 5xx. (confidence 0.85) `L0186, L0200, H10, L0188, M33, M12, M02`
- The incident is not a payment-service regression. Its CPU, memory and request rate are flat, and its errors start at the provider-error boundary rather than at a deploy. (confidence 0.70) `M32, M35, M36, C05`
- The search-service deploy at 15:40Z is unlikely to be the cause. Its error rate is flat, and checkout errors begin 20 minutes later and only on the payment path. (confidence 0.80) `C09, M43, M12`

## Remediation
- **immediate** - Fail over or route payment traffic to a secondary payment provider, or enable a degraded-payment mode (queue or retry orders) while the provider is down. _(The provider is the origin, and payment-service cannot fix it locally.)_
- **immediate** - Notify support and customers about failed payments, and set up reconciliation for orders that failed with 502 so they are not double-charged on retry. _(60 checkout orders failed in the sampled logs and the impact is customer-facing.)_
- **short_term** - Tune the payment-service retry and timeout settings so that retries are not stacked on a degraded provider, and confirm the circuit breaker behaves as intended. _(Retries add about 10s of latency and load while the provider is failing.)_
- **short_term** - Add a deep health check that exercises the payment-provider Charges API path, and alert on payment-service error rate and on circuit breaker OPEN events. _(Current health checks report healthy during a 40% error rate.)_
- **long_term** - Add provider-side telemetry (latency and error rate per provider) to the dataset and to dashboards. _(The provider's failure was known only through the status page and inferred from payment-service logs.)_

## Open questions
- Is the provider's outage ongoing, and what is its estimated recovery time?
- Does the 503 response body or headers from the provider give a reason code?
- Why does the payment-service /health check pass during the outage?
- Could the 15:40Z search-service deploy have contributed to any part of the checkout path? Not supported so far, but no direct trace data was checked.
- Are there any TLS handshake errors in payment-service logs? None were seen in the sampled WARN/ERROR lines, but the sample was limited to 20 lines.

## Data gaps and tool failures (0 shown, 0 reported)
_None._
