# Incident report S01

- **Status:** CONCLUSIVE (confidence 0.85, margin 0.80, 7 verified supporting and 1 contradicting evidence items (12%))
- **System:** baseline · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** agent_finished
- **Root cause:** `checkout-service` - deployment_regression (confidence 0.85)

## Summary
api-gateway 5xx and checkout-service error rates jumped at about 14:00 UTC, one to two minutes after checkout-service v2.14.0 was deployed at 13:56. Checkout logs show a NullPointerException in the new DiscountEngine.apply (line 88) on nearly every failing request, and the gateway 500s are checkout upstream responses. The pattern matches the May 2026 pricing-deploy incident (P04). Health checks stayed green because they are shallow, and the P06 TLS cause is not supported by the logs. Confidence in the v2.14.0 discount-engine regression is high but not conclusive, since no code diff or rollback test was available.

## Conclusion decision
- confidence 0.85, margin 0.80, 7 verified supporting and 1 contradicting evidence items (12%)
- Criteria: top `checkout-service / deployment_regression` confidence 0.85, margin 0.80, 7 verified supporting / 1 contradicting items (12% contradicting); 0 evidence-backed material critic objection(s), 0 non-blocking

## Ranked hypotheses
1. **checkout-service** - deployment_regression (confidence 0.85)
   - Mechanism: v2.14.0 replaced the legacy pricing rules with a new discount engine. DiscountEngine.apply throws a NullPointerException on some carts (line 88), so POST /api/v1/checkout returns 500. api-gateway passes these through as 5xx, which lowers conversion.
   - Supporting evidence: `C09, L0188, L0257, M12, M02, L0186, P04`
   - Contradicting evidence: `L0181`
   - Assumptions: The deploy at 13:56 is the only relevant change in the window.; Only some carts trigger the NPE, which explains the roughly 18% error rate instead of 100%.
2. **payment-service** - certificate_expiry (confidence 0.05)
   - Mechanism: An expired TLS certificate on payment-service would make checkout calls fail and surface as checkout 5xx.
   - Supporting evidence: `P06, M12`
   - Contradicting evidence: `L0188, L0186`
   - Assumptions: Payment calls are on the failing path.
3. **inventory-service** - dependency_failure (confidence 0.05)
   - Mechanism: Slow inventory reservation could cause checkout timeouts and 500s. The only supporting sign is a single 925 ms reservation warning at 13:51, before onset.
   - Supporting evidence: `L0154, M13`
   - Contradicting evidence: `L0188, M13`
   - Assumptions: Inventory timeouts would surface as 500s rather than as NPEs.

## Observed facts
- api-gateway error_rate rose from about 0.4% (13:55 and earlier) to 6.06% at 14:00:00 and stayed between 5.8% and 6.6% through 14:30. `M02`
- checkout-service error_rate rose from 0.35% at 13:55 to 17.76% at 14:00 and stayed between 17% and 19.5% through 14:30. `M12`
- checkout-service latency_p99 rose from 325 ms at 13:55 to 408.98 ms at 14:00; api-gateway latency_p99 stayed flat near 175-187 ms; CPU and memory on both services stayed in normal ranges. `M13, M03, M11, M14, M01, M04`
- Deploy v2.14.0 (new discount engine replacing legacy pricing rules, build 8f3a2c1) was recorded for checkout-service at 13:56:00; startup logs appear 13:56:21 to 13:57:36, and an order was created successfully at 13:59:07. `C09, L0171, L0172, L0177, L0181`
- The first checkout ERROR is NullPointerException at DiscountEngine.apply(DiscountEngine.java:88) at 14:00:27; about 40 such ERRORs appear through 14:14:45, and they are the dominant error signature (40 of 43 WARN/ERROR lines). `L0188, L0257, L0154`
- api-gateway logged 'upstream checkout-service returned 500 for POST /api/v1/checkout' starting at 14:00:08, with 25 such lines in the window. `L0186, L0192, L0237`
- Health checks at 14:28 report api-gateway, checkout-service, payment-service, auth-service, inventory-service and notification-queue as healthy (HTTP /health 200). `H01, H03, H11, H02, H07, H08`
- Past incident P04 (2026-05-12) had checkout 5xx after a pricing deploy, caused by an unhandled null coupon field in new pricing code. `P04`
- Past incident P06 (2026-06-11) had checkout 5xx from an expired TLS certificate on payment-service; the logs here contain no TLS handshake errors. `P06`
- checkout-service request_rate stayed around 82-88 req/s and api-gateway request_rate around 404-437 req/s across the window, with no visible traffic step at 14:00. `M15, M05`

## Assumptions
- The discount engine is the only code path changed in v2.14.0 that handles the failing POST /api/v1/checkout requests.
- Health endpoints do not exercise the discount-engine code path or payment writes, so green health checks do not rule out the regression.
- The 13:56 deploy completed on all checkout instances, as the deploy record shows status completed.
- Null cart or coupon inputs are the trigger for the NPE; the logs do not show the input data.

## Inferred conclusions
- The v2.14.0 discount engine (DiscountEngine.apply) is the most likely origin: it deployed at 13:56, errors began at 14:00 with the NPE, and the gateway 5xx follows checkout's 500s. (confidence 0.85) `C09, L0188, M12, M02, L0186`
- The api-gateway 5xx rate (about 6%) is a dilution of checkout's roughly 18% error rate, since checkout is only one route; the gateway is a propagation point, not the origin. (confidence 0.70) `M02, M12, L0186`
- The P06 TLS certificate expiry is unlikely: the error signature is an application NPE, not handshake failures, and the failure started right at the deploy. (confidence 0.80) `P06, L0188`
- Traffic surge and resource exhaustion are unlikely: request rates and CPU/memory are flat, and the error onset is a step change. (confidence 0.80) `M05, M15, M01, M11`

## Remediation
- **immediate** - Roll back checkout-service from v2.14.0 to the previous release, or disable the new discount engine feature flag if one exists. _(The error onset is one minute after the deploy and the NPE is the dominant signature; rollback is the fastest restore of checkout conversion.)_
- **immediate** - Confirm recovery: checkout error_rate returns to about 0.3% and gateway 5xx falls under 2%. _(Verifies that the rollback addresses the failure.)_
- **short_term** - Fix DiscountEngine.apply null handling (line 88) for missing coupon or rule fields, and add a regression test with the cart inputs from the failing requests. _(Addresses the NPE directly, as in the P04 fix.)_
- **long_term** - Add a canary or staged rollout gate on checkout that compares the error rate against baseline before full rollout. _(The regression reached full production traffic within minutes.)_
- **long_term** - Make health checks exercise the checkout pricing path with a synthetic cart. _(The current health checks stayed green during a 17% checkout error rate.)_

## Open questions
- Is the NPE triggered by a specific cart or coupon type, or by all carts that use the new discount engine? The logs show only cart IDs.
- Did every checkout instance run v2.14.0, or is the failure limited to some pods?
- Is there a feature flag or config that gates the new discount engine?
- Why is the error rate about 18% and not near 100%, and does the failing share match the share of carts with a discount?

## Data gaps and tool failures (0 shown, 0 reported)
_None._
