# Incident report S01

- **Status:** CONCLUSIVE (confidence 0.85, margin 0.80, 7 verified supporting and 2 contradicting evidence items (22%))
- **System:** baseline · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** agent_finished
- **Root cause:** `checkout-service` - deployment_regression (confidence 0.85)

## Summary
Checkout 5xx errors began at 14:00:00Z, about four minutes after the checkout-service v2.14.0 deploy at 13:56:00Z. The checkout-service logs show a NullPointerException in DiscountEngine.apply (line 88) on nearly every failing request, and api-gateway reports 500s from checkout-service for POST /api/v1/checkout. Checkout errors went from about 0.3% to about 18%, and api-gateway 5xx went from about 0.4% to about 6%, which matches the alert. Dependencies (payment, inventory, auth) are healthy and show no correlated change, so the regression is most likely the new discount engine code in v2.14.0. A past incident (P04) had the same signature after a pricing deploy and was fixed by rollback. Rollback of v2.14.0 is the leading mitigation.

## Conclusion decision
- confidence 0.85, margin 0.80, 7 verified supporting and 2 contradicting evidence items (22%)
- Criteria: top `checkout-service / deployment_regression` confidence 0.85, margin 0.80, 7 verified supporting / 2 contradicting items (22% contradicting); 0 evidence-backed material critic objection(s), 0 non-blocking

## Ranked hypotheses
1. **checkout-service** - deployment_regression (confidence 0.85)
   - Mechanism: The v2.14.0 discount engine throws a NullPointerException in DiscountEngine.apply for some carts. Checkout POSTs return 500, and api-gateway passes them through as 5xx.
   - Supporting evidence: `C09, L0188, L0242, M12, M02, L0186, P04`
   - Contradicting evidence: `H01, H03`
   - Assumptions: Health checks are shallow and do not exercise the discount path.; No other change explains the NPE.
2. **payment-service** - certificate_expiry (confidence 0.05)
   - Mechanism: An expired TLS certificate on payment-service causes handshake failures and checkout 5xx, as in past incident P06.
   - Supporting evidence: `P06`
   - Contradicting evidence: `L0188, H11`
   - Assumptions: The same symptom pattern would appear in the checkout logs.
3. **api-gateway** - traffic_surge (confidence 0.03)
   - Mechanism: A traffic surge or gateway saturation drives 5xx rates.
   - Supporting evidence: none
   - Contradicting evidence: `M05, M01, M04`

## Observed facts
- api-gateway 5xx (error_rate) rose from about 0.4% at 13:55:00Z to 6.06% at 14:00:00Z and stayed between 5.8% and 6.6% through 14:30:00Z. `M02`
- checkout-service error_rate jumped from 0.35% at 13:55:00Z to 17.76% at 14:00:00Z, peaking at 19.5% at 14:25:00Z. `M12`
- checkout-service latency_p99 rose from about 325 ms before 14:00 to about 397-425 ms from 14:00 onward; checkout request_rate stayed roughly flat (82-88 req/s). `M13, M15`
- Deploy v2.14.0 to checkout-service (new discount engine replacing legacy pricing rules) completed at 13:56:00Z. `C09`
- checkout-service logged 40 ERROR lines of NullPointerException at DiscountEngine.apply(DiscountEngine.java:88), the first at 14:00:27Z, with distinct cart_ids. `L0188, L0190, L0242`
- api-gateway logged repeated 'upstream checkout-service returned 500 for POST /api/v1/checkout' errors from 14:00:08Z onward. `L0186, L0192, L0267`
- api-gateway and checkout-service CPU and memory stayed in normal ranges (about 37-39% and 55-60%) throughout the window. `M01, M04, M11, M14`
- Health checks for api-gateway, checkout-service, auth-service, inventory-service, notification-queue and payment-service all returned HTTP 200 at 14:28:00Z. `H01, H02, H03, H07, H08, H11`
- A past incident P04 (2026-05-12) recorded checkout 5xx from an unhandled null field in new pricing code, resolved by rollback. `P04`

## Assumptions
- The health checks are shallow and do not exercise the checkout POST path or discount logic, so their 200s do not rule out the regression.
- DiscountEngine.java line 88 belongs to the v2.14.0 change and not to older code.
- The telemetry window is complete, and no other deploy hit a dependency in the minutes before 14:00.
- The discount-engine is not a separate monitored service; it runs inside checkout-service.

## Inferred conclusions
- The v2.14.0 discount engine deploy in checkout-service is the most likely origin: it was completed 4 minutes before onset, and its NPE accounts for nearly all checkout 500s, which propagate to api-gateway as 5xx. (confidence 0.85) `C09, L0188, M12, L0186`
- Rolling back checkout-service to v2.14.0's predecessor should restore checkout conversion and bring the 5xx rate back to baseline. (confidence 0.75) `C09, M02, M12`
- Traffic surge, resource exhaustion at the gateway, and dependency failures are unlikely: request rate was flat and CPU/memory and dependency health were normal. (confidence 0.80) `M05, M01, M04, H11, H02, H07`

## Remediation
- **immediate** - Roll back checkout-service from v2.14.0 to the previous release, or disable the new discount engine via its feature path if one exists. _(The NPE started four minutes after the deploy and accounts for nearly all checkout 500s.)_
- **immediate** - Verify recovery: checkout error_rate and api-gateway 5xx return to about 0.3-0.4% and conversion recovers. _(Confirms the rollback addressed the cause.)_
- **short_term** - Fix the null handling in DiscountEngine.apply (line 88) for carts with missing discount/coupon fields, and add a regression test. _(Removes the root defect before re-release.)_
- **long_term** - Make the health check exercise the checkout POST path with discount logic, so a shallow 200 cannot mask 500s. _(Health checks currently reported healthy during a 19% checkout error rate.)_
- **long_term** - Add a canary or progressive rollout with an alert on checkout error_rate after deploys. _(A 4-minute detection gap plus a full rollout caused a P1; the prior pricing incident P04 shows this failure class recurs.)_

## Open questions
- Which carts trigger the NPE (for example, missing coupon field or legacy pricing data), and is the fraction of affected carts consistent with the 18% error rate?
- Was there any config or feature-flag change alongside v2.14.0? None appears in the change history, but the search covered only telemetry-era records.
- Why does the checkout error rate (18%) exceed what the gateway shows (6%) and is some of the gap a client retry or 499 effect?
- Is the checkout conversion drop of 40% fully explained by the 5xx rate, or does the discount logic also affect cart totals?

## Data gaps and tool failures (0 shown, 0 reported)
_None._
