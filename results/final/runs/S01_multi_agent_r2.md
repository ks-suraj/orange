# Incident report S01

- **Status:** INCONCLUSIVE (contradicting evidence is 53% of the weighed evidence (max 35%))
- **System:** multi_agent · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** max_rounds_reached

## Summary
Investigation S01 on the 14:00 UTC api-gateway 5xx spike and checkout conversion drop was determined INCONCLUSIVE by the system: contradicting evidence is 53% of weighed evidence against a 35% maximum, and the leading hypothesis's confidence is only 0.50. The errors are confined to POST /api/v1/checkout, and the gateway logs show them as upstream 500s from checkout-service. Checkout's only logged error is a DiscountEngine.apply NullPointerException at DiscountEngine.java:88, first logged at 14:00:27Z, about 4 minutes after checkout-service v2.14.0 was deployed at 13:56:00Z. The leading candidate is H-1, a regression in v2.14.0, but it is not established as the cause: the first gateway 500 at 14:00:08Z precedes the first logged NPE by 19 s, gateway and NPE counts do not reconcile one-to-one, and checkout's error rate (about 18%) does not reconcile with the gateway's (about 6%). Alternative candidates are H-2 (null cart or coupon input triggering the same NPE) and H-3 (gateway-generated 5xx), both still open. Mitigation should proceed on the basis of the leading candidate while the open checks are completed.

## Conclusion decision
- contradicting evidence is 53% of the weighed evidence (max 35%)
- Criteria: top `checkout-service / deployment_regression` confidence 0.50, margin 0.25, 7 verified supporting / 8 contradicting items (53% contradicting); 1 evidence-backed material critic objection(s), 4 non-blocking
  - objection: alternative_not_ruled_out: Checkout's 500 count (about 18% of about 85 req/s, roughly 15/s) cannot account for the gateway's about 25/s 5xx on the checkout route. The roughly 10/s excess  [M02, M12, M05, M15, L0186, L0339]

## Ranked hypotheses
1. **checkout-service** - deployment_regression (confidence 0.50)
   - Mechanism: checkout-service v2.14.0, deployed at 13:56:00Z to replace legacy pricing with a new discount engine, begins throwing NullPointerException in DiscountEngine.apply (DiscountEngine.java:88) from 14:00:27Z on a subset of carts. Checkout returns 500 and api-gateway relays these as upstream 500s on POST /api/v1/checkout, matching the onset of the error and conversion drop. The gateway's 6% rate exceeds the rate implied by checkout's share of traffic, so some gateway-side or unlogged failures are unexplained.
   - Supporting evidence: `C09, L0188, L0190, L0300, L0340, M12, M02, M13, P04`
   - Contradicting evidence: `L0186, L0192, M11, M05`
   - Assumptions: The NPE originates in v2.14.0 code rather than in upstream cart or coupon data, which is not verified; The 4-minute gap between deploy and onset reflects a deploy-triggered regression rather than a delayed rollout effect; The 14:00:08Z gateway 500 precedes the first logged NPE by 19 s due to an unlogged checkout failure or clock skew
2. **checkout-service** - dependency_failure (confidence 0.25)
   - Mechanism: Null or malformed cart, coupon or pricing data reaching DiscountEngine triggers the same NPE and checkout 500 signature, with the v2.14.0 deploy only coincident. Failures would be cart-level and intermittent, consistent with the scattered NPE pattern.
   - Supporting evidence: `L0188, L0300, M12, L0186`
   - Contradicting evidence: `C09, P04`
   - Assumptions: A pricing or coupon data change occurred near 14:00 outside the change ledger, which has not been checked; Upstream data sources for DiscountEngine were not inspected
3. **api-gateway** - other (confidence 0.10)
   - Mechanism: The api-gateway generates some 5xx on the checkout route itself, accounting for the excess of gateway 5xx (about 25/s) over checkout-attributed 5xx (about 15/s), while the upstream-500 messages reflect checkout failures. This is only weakly supported and is not established by the logs.
   - Supporting evidence: `M02, M12, M05, M15, C01`
   - Contradicting evidence: `L0186, L0188, M03, M01`
   - Assumptions: The gateway's upstream-500 log messages are misattributed or incomplete; Rate denominators from the metrics are correct

## Observed facts
- api-gateway error_rate rose from about 0.4% in the 13:00–13:55 buckets to 6.06% at 14:00 and stayed between 5.77% and 6.59% through 14:30. `M02`
- checkout-service error_rate rose from about 0.3% before 14:00 to 17.76% at 14:00 and stayed between 17.0% and 19.5% through 14:30. `M12`
- The only change recorded in the 12:00–14:30 UTC window is checkout-service v2.14.0 deployed at 13:56:00Z, described as replacing legacy pricing rules with a new discount engine; no api-gateway, config, feature-flag or infra changes appear. `C09`
- The first api-gateway 500 for POST /api/v1/checkout is logged at 14:00:08Z; the gateway's 5xx messages read 'upstream checkout-service returned 500', and about 25 such lines appear through 14:30:00Z. `L0186, L0339`
- checkout-service's first logged error is a NullPointerException at DiscountEngine.apply (DiscountEngine.java:88) at 14:00:27Z; no checkout WARN/ERROR precedes it except a 13:51:04Z slow-inventory WARN. `L0188, L0154`
- checkout-service logged 40 ERROR lines in the window, all the same DiscountEngine NPE signature, with no other exception types returned; the expected count of 43 was not reproduced. `L0340, L0188`
- Gateway 5xx lines and checkout NPE lines are not one-to-one in time; for example NPEs at 14:00:50Z and 14:01:51Z have no gateway 500 at the same moment, and the 14:00:08Z gateway 500 has no checkout log entry before it. `L0186, L0190, L0194, L0192`
- api-gateway and checkout-service request rates were flat across 13:00–14:30 (about 412–437 req/s and 82–88 req/s), and CPU and memory showed no step change at 14:00. `M05, M15, M01, M11, M04, M14`
- Health checks at 14:28Z were healthy for all services and dependencies, but they are shallow HTTP /health or SELECT 1 probes that do not exercise the discount or pricing path. `H01, H03, H11, H07, H06`
- Past incident P04 (2026-05-12) was checkout 5xx from a NullPointerException caused by an unhandled null coupon field in new pricing code, resolved by rollback. `P04`

## Assumptions
- The NullPointerException originates in v2.14.0 code rather than in null cart or coupon data supplied upstream; this was not verified.
- The roughly 4-minute gap between the deploy and onset reflects a deploy-triggered regression rather than a delayed rollout effect.
- The 14:00:08Z gateway 500 is explained by an unlogged checkout failure or clock skew between services; this was not tested.
- The gateway's upstream-500 log messages correctly attribute failures to checkout-service, and the metric denominators are correct.
- The shallow health checks would not detect a payment or inventory fault on the checkout path.

## Inferred conclusions
- The leading candidate is a regression in checkout-service v2.14.0's DiscountEngine, which is the best-supported hypothesis on timing and error content but is not established as the root cause. (confidence 0.50) `C09, L0188, M12, M02`
- The api-gateway 5xx are relayed checkout-side failures rather than gateway-originated errors, since the gateway has no change and its logged errors are upstream 500s on the checkout route. (confidence 0.60) `L0186, L0339, M02, M12`
- Null or malformed cart, coupon or pricing input reaching DiscountEngine (H-2) remains a plausible alternative origin, consistent with the NPE signature and the P04 pattern, and has not been tested. (confidence 0.25) `L0188, L0190, P04`
- Infrastructure saturation, traffic surge, and the api-gateway TLS upgrade are unlikely causes of the 14:00 onset. (confidence 0.70) `M01, M05, M11, C01`
- Some gateway 5xx volume and checkout failures are not explained by the logged NPEs, leaving an unlogged checkout failure path or gateway-originated errors (H-3) open. (confidence 0.35) `M02, M12, M15, L0186`

## Remediation
- **immediate** - Consider rolling back checkout-service from v2.14.0 to v2.13.4 or disabling the new discount engine path, and confirm whether a feature flag or canary gates it. _(The deploy is the only change in the window and precedes onset by about 4 minutes; rollback is a reversible mitigation that tests causality and restores checkout conversion.)_
- **immediate** - Monitor checkout 5xx rate and conversion for a recovery after rollback, and treat recovery as evidence for or against the leading candidate. _(A rollback test is the most direct check available given the inconclusive determination.)_
- **short_term** - Pull the cart and coupon/pricing input data for failing carts (e.g. 4db2c6e6, 6bee59e1) to separate null-input origin from a code defect. _(This tests H-2 directly, which the investigation did not examine.)_
- **short_term** - Review the v2.14.0 DiscountEngine code diff at line 88 and add null guards for coupon and cart fields. _(The NPE is the only checkout error signature and the P04 pattern points to unhandled null coupon fields.)_
- **short_term** - Reconcile per-route and per-status request and 5xx counts for api-gateway and checkout-service from 14:00 to 14:30 to explain the 18% versus 6% rates and the 25-versus-40 count gap. _(The current rates do not reconcile on traffic share, so H-3 and unlogged failure paths cannot be ruled out.)_
- **long_term** - Add deep health or synthetic checkout transactions that exercise the discount and pricing path, rather than relying on shallow /health checks. _(Shallow health checks reported healthy during an active checkout failure, so they gave no early warning.)_
- **long_term** - Require canary or progressive rollout with error-rate gating for checkout deploys that change pricing logic. _(A similar pricing-deploy null-input failure occurred in P04, and a canary would limit blast radius.)_

## Open questions
- Is the 14:00:08Z gateway 500 explained by an unlogged checkout failure or by clock skew between services?
- Why do checkout's error rate (about 18%) and the gateway's error rate (about 6%) differ beyond what traffic share explains, and is gateway-originated 5xx present?
- Does rolling back or disabling v2.14.0 restore checkout error rate and conversion to baseline?
- Were null or malformed cart, coupon or pricing inputs present near 14:00Z, and did any data change outside the change ledger?
- Is the new discount engine gated by a feature flag or canary, and what was its state before and during the window?
- Why did the NPE count return 40 rather than the expected 43, and are there any other exception types outside the returned sample?

## Data gaps and tool failures (10 shown, 30 reported)
- checkout-service log results are truncated (43 matching, 30 returned), so the full list of NPE timestamps and any earlier errors before 14:00:27 were not seen. The first-error time is likely but not certainly 14:00:27.
- No per-endpoint or per-status-code breakdown was available. The statement that only /api/v1/checkout returns 5xx is based on the log sample and the absence of other 5xx lines, not on a breakdown of error_rate by route or code.
- No downstream dependency metrics or logs were queried (payment-service, DiscountEngine's data sources, inventory). Whether the NPE is caused by bad input or bad data from upstream is not established.
- The 2 payment-service retry warnings in checkout logs were not investigated.
- Checkout-service error_rate (~18%) and gateway error_rate (~6%) do not reconcile on traffic share alone. The reason is not determined from these data.
- Change records are the only source for config, flag and infra changes. The empty api-gateway result cannot confirm the absence of flag-based or runtime changes. Only shallow /health checks were available, so no deep checkout-path or pricing-path health is known. Past-incident search and error-rate breakdowns by endpoint were not queried, and no telemetry was examined.
- Health checks are shallow (/health only), so they do not exercise payment or inventory calls, TLS handshakes or the discount engine path.
- No error-rate, latency or per-dependency telemetry was retrieved, so the claim that checkout is the origin of the 5xx, and not a downstream dependency, is unverified.
- No tool exposed checkout-service v2.14.0 code or config diffs, or whether a feature flag gates the discount engine.
- 21 further gap report(s) in 21 group(s) omitted here (mostly about: query, lines, metrics, checkout, checkout-service, 5xx); the full list is in the run record.
