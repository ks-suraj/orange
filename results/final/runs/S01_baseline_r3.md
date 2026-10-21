# Incident report S01

- **Status:** CONCLUSIVE (confidence 0.90, margin 0.85, 8 verified supporting and 1 contradicting evidence items (11%))
- **System:** baseline · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** agent_finished
- **Root cause:** `checkout-service` - deployment_regression (confidence 0.90)

## Summary
Checkout 5xx errors began at 14:00 UTC, about four minutes after checkout-service v2.14.0 deployed at 13:56. Checkout error rate jumped from about 0.3% to about 18%, and the logs show a NullPointerException in the new DiscountEngine.apply on every sampled failure. The api-gateway 5xx rate (about 6%) is the propagated effect of checkout's 500s on POST /api/v1/checkout. The deploy is the leading cause; the earlier node-pool upgrade and payment TLS are weakly supported or unsupported. Confidence is high but not verified by a rollback or a direct code-line check.

## Conclusion decision
- confidence 0.90, margin 0.85, 8 verified supporting and 1 contradicting evidence items (11%)
- Criteria: top `checkout-service / deployment_regression` confidence 0.90, margin 0.85, 8 verified supporting / 1 contradicting items (11% contradicting); 0 evidence-backed material critic objection(s), 0 non-blocking

## Ranked hypotheses
1. **checkout-service** - deployment_regression (confidence 0.90)
   - Mechanism: The v2.14.0 discount engine throws an unhandled NullPointerException at DiscountEngine.apply line 88 for some carts. Each failure returns HTTP 500 from checkout, which the gateway passes through as 5xx and which lowers conversion.
   - Supporting evidence: `C09, L0171, L0188, M12, M02, L0186, L0202, P04`
   - Contradicting evidence: `L0154`
   - Assumptions: Only the new deploy changed checkout behaviour at 14:00.; Failing carts are a subset of traffic (about 18%), so the failure depends on cart data.
2. **payment-service** - certificate_expiry (confidence 0.05)
   - Mechanism: An expired or mis-rotated TLS certificate on payment-service makes checkout's calls fail, producing 500s in checkout (as in P06).
   - Supporting evidence: `P06`
   - Contradicting evidence: `H11, L0188`
   - Assumptions: The health check does not exercise TLS.
3. **platform** - infrastructure_failure (confidence 0.04)
   - Mechanism: The node pool upgrade to 1.31 causes instability on some nodes, degrading checkout.
   - Supporting evidence: `C08`
   - Contradicting evidence: `M01, M11, M04, M14, H03`
   - Assumptions: The upgrade effect is delayed by about 9 hours.

## Observed facts
- checkout-service v2.14.0 (build 8f3a2c1) was deployed at 2026-09-01T13:56:00Z, described as 'new discount engine replaces legacy pricing rules'. `C09, L0171`
- checkout-service error_rate was about 0.26–0.35% from 13:00 to 13:55 and rose to 17.76% at 14:00:00, peaking at 19.5% at 14:25. `M12`
- api-gateway error_rate was 0.36–0.45% until 13:55 and rose to 6.06% at 14:00:00, peaking at 6.59% at 14:05. `M02`
- The first checkout NullPointerException in DiscountEngine.apply (DiscountEngine.java:88) was logged at 14:00:27; 40 such errors appear in the window, and the top WARN/ERROR signature is this NPE. `L0188, L0154`
- api-gateway logged 25 'upstream checkout-service returned 500 for POST /api/v1/checkout' errors, starting at 14:00:08. `L0186, L0192, L0202, L0205`
- checkout-service latency_p99 rose from about 325 ms (13:55) to 409 ms at 14:00 and stayed around 400–425 ms. `M13`
- Dependency health checks (api-gateway, checkout-service, payment-service, auth-service, inventory-service, notification-queue) all returned HTTP 200 at 14:28. `H01, H02, H03, H07, H08, H11`
- CPU and memory on api-gateway and checkout-service stayed in normal ranges (checkout cpu 39–43%, memory 55–60%; gateway cpu 36–39%, memory 50–54%) with no step change at 14:00. `M01, M04, M11, M14`
- Request rate was flat (about 412–437 req/s at the gateway, 82–88 req/s at checkout), so no traffic surge is visible. `M05, M15`
- A prior deploy v2.13.4 to checkout-service completed at 2026-08-31T18:00:00Z and checkout errors were normal after it. `C07, M12`
- A Kubernetes node pool upgrade 1.30→1.31 completed at 2026-09-01T05:00:00Z, about 9 hours before onset. `C08`
- A past incident (P04, 2026-05-12) had the same pattern: NullPointerException in pricing code after a deploy, causing checkout 5xx, fixed by rollback and null checks. `P04`

## Assumptions
- The 13:56 deploy is the only checkout-service change in the window; the change history shows none other.
- The health checks are shallow (HTTP /health only) and would not detect a failure in the discount code path or payment TLS.
- The NPE at DiscountEngine.java:88 is triggered by the new discount engine code path in v2.14.0, not by legacy data, since no pre-deploy NPEs appear in the logs.
- Gateway 5xx is mostly checkout's 500s passed through; the gateway error rate is about one third of checkout's, consistent with checkout being hit on a subset of traffic.

## Inferred conclusions
- The v2.14.0 deploy of checkout-service is the root cause: the new DiscountEngine throws an unhandled NPE on checkout requests, which causes the 500s, and the gateway 5xx rate follows. (confidence 0.90) `C09, L0188, M12, M02, L0186`
- The node pool upgrade is unlikely to be the cause: it was 9 hours before onset, and no resource or health signal changed at 14:00. (confidence 0.85) `C08, M01, M11, H03`
- A payment-service TLS or dependency failure is unlikely: checkout errors are NPEs in its own code, payment health is healthy, and no payment-side errors were returned in the sampled logs. (confidence 0.70) `H11, L0188`
- Checkout conversion drop (about 40%) is consistent with checkout returning 500s on roughly 18% of checkout attempts, plus client retries and abandonment. (confidence 0.50) `M12, L0193`

## Remediation
- **immediate** - Roll back checkout-service from v2.14.0 to v2.13.4 now. _(The NPE started within 4 minutes of the deploy and the prior version ran cleanly for 20 hours.)_
- **immediate** - Feature-flag or disable the new discount engine path if a rollback is delayed. _(Limits the blast radius while the rollback runs.)_
- **immediate** - Watch checkout 5xx, api-gateway 5xx and conversion for recovery after rollback. _(Confirms the mitigation worked.)_
- **short_term** - Fix the null handling at DiscountEngine.apply (line 88), e.g. null coupon or pricing-rule defaults, and add unit tests with null inputs. _(Addresses the defect before re-release.)_
- **short_term** - Add a canary or staged rollout for checkout with an error-rate gate. _(Would have caught an 18% error rate before full rollout.)_
- **long_term** - Make the health checks exercise the checkout and discount path, not only /health. _(Current health checks stayed green during the 18% error rate.)_
- **long_term** - Review the May 2026 pricing NPE postmortem and add a pre-deploy null-input check to the release checklist. _(Same failure mode recurred.)_

## Open questions
- Which discount or coupon inputs trigger the NPE (e.g., a null field from the new rules table)?
- Is the 13:56 to 14:00 gap explained by a rolling restart, with the new pods taking traffic gradually?
- Why do the repeated 'Starting checkout-service v2.14.0' lines appear three times at 13:56–13:57?
- Did any payment-side errors occur that the sampled logs did not show?

## Data gaps and tool failures (0 shown, 0 reported)
_None._
