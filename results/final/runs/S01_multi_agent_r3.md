# Incident report S01

- **Status:** INCONCLUSIVE (contradicting evidence is 44% of the weighed evidence (max 35%))
- **System:** multi_agent · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** tool_budget_exhausted

## Summary
Incident S01 is a P1 5xx spike on api-gateway and checkout-service starting at 14:00:00 UTC, with checkout error rate rising from about 0.3% to about 18% and gateway 5xx from about 0.4% to about 6%. The system determination is INCONCLUSIVE because contradicting evidence is 44% of weighed evidence, above the 35% limit. The leading hypothesis H1 is a v2.14.0 deploy regression causing a DiscountEngine NullPointerException in checkout-service, at confidence 0.60, but the first gateway 500 at 14:00:08 precedes the first logged NPE at 14:00:27 and no checkout-side record exists for that request. H2, an unrecorded null pricing or discount input, is not excluded because feature flags, config and discount data sources were not verified. The gateway is best treated as a relay rather than the origin, though its 25/s versus 15/s volume gap is unreconciled. No cause is asserted; the deploy is the leading candidate pending the checks listed below.

## Conclusion decision
- contradicting evidence is 44% of the weighed evidence (max 35%)
- Criteria: top `checkout-service / deployment_regression` confidence 0.60, margin 0.40, 5 verified supporting / 4 contradicting items (44% contradicting); 2 evidence-backed material critic objection(s), 4 non-blocking
  - objection: ignored_contradiction: The gateway 500 at 14:00:08 (L0186) precedes the first DiscountEngine NPE at 14:00:27 (L0188), and no checkout-side error exists for that request. The NPE canno [L0186, L0188]
  - objection: alternative_not_ruled_out: H2 (unrecorded null pricing/discount input) fits the NPE signature and the 14:00 onset equally well for the checkout-side failure. The deploy-coincidence argume [C09, L0188, P04]

## Ranked hypotheses
1. **checkout-service** - deployment_regression (confidence 0.60)
   - Mechanism: Deploy v2.14.0 at 13:56:00Z replaced legacy pricing rules with a new discount engine; DiscountEngine.apply (line 88) throws a NullPointerException on checkout requests, so checkout returns HTTP 500 and the gateway relays them as 5xx from 14:00 onward. The deploy precedes the step by about 4 minutes and the NPE signature begins in the same minute as the error step.
   - Supporting evidence: `C09, L0188, L0190, L0340, M12, M02, M13, P04`
   - Contradicting evidence: `L0186, L0188`
   - Assumptions: The NPE comes from the v2.14.0 code path rather than a pre-existing path; The 14:00:08 gateway 500 precedes the first logged NPE at 14:00:27 because of log timing or sampling skew; No NPEs occurred before 13:50 at INFO or DEBUG level
2. **checkout-service** - dependency_failure (confidence 0.20)
   - Mechanism: A null or malformed discount/pricing input from an unrecorded data source change near 14:00 makes DiscountEngine.apply fail for carts; checkout returns 500 and the gateway relays it. The deploy would be coincidental or only contributory.
   - Supporting evidence: `L0188, M12, L0186, P04`
   - Contradicting evidence: `C09`
   - Assumptions: A discount or pricing data source changed around 14:00 without a recorded change; The deploy at 13:56 is coincidental in timing
3. **api-gateway** - other (confidence 0.05)
   - Mechanism: A gateway-side fault would generate 5xx at the gateway. However, gateway logs attribute every 500 to upstream checkout-service and gateway CPU, memory, latency and request rate are flat, so the gateway is a relay rather than the origin. Unexplained gateway 5xx volume versus checkout errors remains an open question.
   - Supporting evidence: `L0186, M02`
   - Contradicting evidence: `L0192, M03, M05, M01, M04`
   - Assumptions: Gateway logs correctly attribute the upstream status code; The volume gap between gateway and checkout 5xx is an artifact of log sampling

## Observed facts
- api-gateway 5xx onset is a step at 14:00 bucket: error_rate about 0.4% before and 6.06% at 14:00, staying 5.77% to 6.59% through 14:30, with flat request rate (404 to 437 req/s) and flat CPU and memory. `M02, M05, M01, M04`
- checkout-service error_rate stepped from about 0.3% to 17.76% at 14:00 and stayed between 17.25% and 19.5% through 14:30, with p99 latency stepping from about 325 ms to 409 ms. `M12, M13`
- checkout-service request rate (82 to 88 req/s) and CPU and memory showed no step at 14:00. `M15, M11, M14`
- Checkout-service deployed v2.14.0 (new discount engine replacing legacy pricing rules) at 13:56:00Z, about 4 minutes before onset; it is the only change in the 13:30 to 14:05 window and no rollback or canary record exists. `C09`
- The first api-gateway 500 for POST /api/v1/checkout is logged at 14:00:08Z, and the first checkout-service DiscountEngine.apply NullPointerException (DiscountEngine.java:88) is logged at 14:00:27Z; no checkout-side 500 record for the 14:00:08 request was found. `L0186, L0188`
- Checkout-service logs show 40 DiscountEngine NPEs from 14:00:27 to 14:30:00, each with a different cart_id, and no ERROR lines in 13:50 to 14:00:08. `L0188, L0190, L0340, L0154, L0166`
- api-gateway logs contain 26 ERROR lines, nearly all 'upstream checkout-service returned 500 for POST /api/v1/checkout'; no gateway 5xx was found on other routes, and the only other error is a 499 client close. `L0186, L0192, L0339, L0193`
- Health checks at 14:28 UTC report all direct downstreams of checkout-service healthy, but these checks are shallow HTTP /health or status-page checks. `H01, H02, H03, H07, H08, H10, H11, H12`
- Past incident P04 (2026-05-12) was checkout 500s with an NPE caused by an unhandled null coupon field in new pricing code after a pricing deploy. `P04`

## Assumptions
- The NPE signature in checkout-service logs is the same failure that causes the checkout 500s returned to the gateway.
- Log timestamps are accurate to within a few seconds, so the 19-second gap between the first gateway 500 and first NPE is either skew or an unlogged checkout-side record.
- Health checks are shallow and do not exercise discount, checkout or payment authorization paths.
- Gateway logs correctly attribute 500 responses to upstream checkout-service.
- No feature-flag, config or discount data-source change occurred in the window, based on the change-history query, which may be incomplete.
- (unverified - no valid evidence cited) Feature-flag, config-change and discount data-source queries were not completed because the tool budget was exhausted; the status-code distribution and per-route breakdown were not obtained.

## Inferred conclusions
- The incident began as a discrete step at 14:00 on checkout-service and api-gateway rather than a gradual or load-driven degradation; load and resource saturation are unlikely causes. (confidence 0.85) `M02, M12, M13, M05, M15, M11, M14`
- The v2.14.0 deploy is the leading candidate cause of the checkout DiscountEngine NPE and the resulting 5xx, but the first gateway 500 precedes the first logged NPE, so causation of the first failure is not established. (confidence 0.60) `C09, L0186, L0188`
- A null pricing or discount input from an unrecorded data change (H2) cannot be excluded and fits the NPE signature and onset equally well, so the deploy is not uniquely implicated. (confidence 0.35) `L0188, P04, C09`
- The api-gateway is a relay rather than the origin of the failure, but the 25/s versus 15/s 5xx volume gap remains unexplained by the sampled logs. (confidence 0.50) `L0186, M02, M05`
- Downstream dependency failure of payment or inventory propagating upward is weakly excluded, since health checks are shallow and no error metrics exist for 13:45 to 14:15. (confidence 0.30) `H11, H07, C05`

## Remediation
- **immediate** - Roll back checkout-service to v2.13.4 or disable the new discount engine path if a rollback is safe, then watch checkout error_rate and the DiscountEngine NPE count. _(The deploy is the leading candidate and rollback is the only available test that can confirm or refute it without further investigation.)_
- **immediate** - Route or canary checkout traffic away from v2.14.0 while the cause is confirmed, and monitor conversion. _(Safe mitigation is recommended for an inconclusive determination, limiting customer impact while the causal link is open.)_
- **short_term** - Capture the checkout-service request record and any error for the 14:00:08Z gateway 500, plus discount and pricing input data for cart 4db2c6e6, to explain the timing gap. _(This is the decisive check on whether the NPE is the origin of the first failure.)_
- **short_term** - Review the v2.14.0 diff at DiscountEngine.java:88 and its null-handling path, and check the 13:56 to 13:57 restart lines. _(Confirms whether the NPE comes from new code and whether the restarts were a pre-onset change.)_
- **short_term** - Check feature-flag, config and discount or coupon data-source changes for 13:30 to 14:05 UTC. _(Needed to test the H2 null-input hypothesis, which could not be verified.)_
- **short_term** - Reconcile api-gateway status-code and per-route 5xx counts from metrics against the 25/s and 15/s figures. _(Resolves whether non-checkout 5xx exist, which the sampled logs cannot show.)_
- **long_term** - Add null-safety checks and tests for missing coupon or pricing fields in the discount engine, and add deep-path synthetic checks for checkout. _(Matches the lessons of P04 and addresses the blind spot where shallow health checks reported healthy during a checkout failure.)_
- **long_term** - Improve checkout logging so that every failed request carries a request id and status, and add per-route status-code metrics to the gateway. _(Would have made the 14:00:08 versus 14:00:27 ordering and the volume gap directly answerable.)_

## Open questions
- Is there a checkout-service record of the request behind the gateway 500 at 14:00:08Z, and does log clock skew explain the 19-second ordering gap?
- Does reverting v2.14.0 stop the DiscountEngine NPE and the gateway 5xx, which would confirm or refute the deploy as the cause?
- Were any feature-flag, config or discount/coupon data-source changes made near 13:55 to 14:00, and do null pricing inputs appear in the data?
- Why does the gateway 5xx volume (about 25/s) exceed checkout errors (about 15/s), and is there any non-checkout 5xx by status code or route?
- Did payment-service or inventory-service error or latency rise between 13:45 and 14:15, which the current data cannot test?

## Data gaps and tool failures (10 shown, 35 reported)
- No status-code distribution (e.g., 500 vs 502/503/504) was returned. Only 500s and one 499 appeared in logs, so the distribution is inferred, not measured.
- No per-route, per-host or per-region breakdown was available. Route is only known from log text (POST /api/v1/checkout). Hosts and regions were not checked.
- Logs were queried at WARN and above only. INFO-level logs, including the checkout NPE's upstream request context, were not searched.
- Metrics are 5-minute resolution, so the exact onset is bounded to the 13:55–14:00 interval.
- Downstream services (payment-service, the discount/pricing data source) were not queried, so the NPE's input data cause is unknown.
- Change history was not checked, though the task allowed it to cover a longer period.
- Dependency graph and health checks were not queried, so the api-gateway -> checkout-service call relationship and neighbour health are unverified.
- Change history only covers changes recorded in the tool; untracked changes (e.g., upstream dependencies, external payment/pricing providers) cannot be ruled out.
- Change-history results do not include error or telemetry data, so the causal link between C09 and the 5xx rate is not established.
- 26 further gap report(s) in 26 group(s) omitted here (mostly about: checkout-service, 5xx, discount, api-gateway, checked, available); the full list is in the run record.
