# Incident report S01

- **Status:** INCONCLUSIVE (top hypothesis confidence 0.45 is below 0.50; contradicting evidence is 38% of the weighed evidence (max 35%))
- **System:** multi_agent · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** max_rounds_reached

## Summary
The system determination is INCONCLUSIVE: the top hypothesis (H-1, checkout-service v2.14.0 deployment regression with a DiscountEngine NullPointerException) has confidence 0.45, below the 0.50 threshold, and contradicting evidence is 38% of weighed evidence against a 35% maximum. The 5xx rise on api-gateway starts in the 14:00 metric bucket and is passed through from checkout-service, which is the strongest-supported component finding. The v2.14.0 deploy at 13:56 UTC is the only change in the window and is the leading candidate, but the logged NPE rate (about 1 per minute) cannot account for roughly 900 failing requests per minute, so the specific failure path is unresolved. Payment-service telemetry is flat across the onset, weakening the payment hypothesis. Remaining checks (rollout scope, per-version error counts, unlogged failure paths, clock alignment) could not be completed within the investigation budget.

## Conclusion decision
- top hypothesis confidence 0.45 is below 0.50
- contradicting evidence is 38% of the weighed evidence (max 35%)
- Criteria: top `checkout-service / deployment_regression` confidence 0.45, margin 0.25, 8 verified supporting / 5 contradicting items (38% contradicting); 1 evidence-backed material critic objection(s), 4 non-blocking
  - objection: ignored_contradiction: The NPE mechanism is presented as the cause of the checkout 500s, but the ledger shows roughly 1 NPE per minute against roughly 900 failing requests per minute. [L0188, L0340, M12, M15]

## Ranked hypotheses
1. **checkout-service** - deployment_regression (confidence 0.45)
   - Mechanism: The v2.14.0 deploy at 13:56:00Z introduced a new discount engine; a null-handling defect in DiscountEngine.apply (line 88) throws NullPointerException on checkout requests, which checkout returns as HTTP 500 and api-gateway passes through on POST /api/v1/checkout. The 14:00 step follows the deploy by about 4 minutes and the first NPE follows the v2.14.0 startup lines.
   - Supporting evidence: `C09, M12, M02, M13, L0171, L0177, L0188, L0340, L0339, D01, P04`
   - Contradicting evidence: `L0186, M15`
   - Assumptions: Log timestamps across services are aligned within a few seconds; v2.14.0 serves the failing traffic; rollout scope is unverified; Shallow health checks do not exercise the discount path
2. **checkout-service** - other (confidence 0.20)
   - Mechanism: An unlogged failure path inside checkout-service (for example request handling or pricing that returns 500 without an ERROR log) produces most of the roughly 900 failing requests per minute; the NPE is a minor visible symptom. This would explain why the logged NPE rate is far below the 18% error rate and why gateway 500s can precede logged NPEs.
   - Supporting evidence: `M12, M15, L0188, L0207, L0186`
   - Contradicting evidence: `L0340`
   - Assumptions: Logs are sampled or truncated, or the failure path does not log; The failure is inside checkout-service, not in a dependency it calls
3. **payment-service** - dependency_failure (confidence 0.05)
   - Mechanism: A payment-side fault returns errors or timeouts to checkout, which surfaces as checkout 500s and then gateway 500s without producing NPE logs.
   - Supporting evidence: `L0195, D04`
   - Contradicting evidence: `M33, M34, M32, M35, M36, H11`
   - Assumptions: Payment errors are hidden from payment-service metrics; Checkout would log payment errors rather than NPEs

## Observed facts
- api-gateway error_rate was about 0.4% from 13:00 to 13:45, then 6.06% at 14:00 and between 5.77% and 6.59% through 14:30. `M02`
- checkout-service error_rate was about 0.3% before 14:00, then 17.76% at 14:00 and between 17.25% and 19.5% through 14:30. `M12`
- Request rates on api-gateway (about 412-437 req/s) and checkout-service (about 82-88 req/s) did not change at the onset; CPU and memory stayed in normal ranges. `M05, M15, M01, M11, M04, M14`
- Of the sampled api-gateway WARN/ERROR lines, most are 'upstream checkout-service returned 500 for POST /api/v1/checkout', first at 14:00:08Z; this is a sample, not full counts. `L0186, L0339`
- checkout-service logged NullPointerException at DiscountEngine.apply(DiscountEngine.java:88) about once per minute from 14:00:27Z through 14:30:00Z; no NPE lines appear before 14:00. `L0188, L0340`
- checkout-service v2.14.0 deploy (new discount engine replacing legacy pricing rules) completed at 13:56:00Z by deploy-bot; it is the only change recorded across services from 13:00 to 14:30. `C09`
- Three checkout-service startup lines for v2.14.0 appear at 13:56:21Z, 13:56:31Z and 13:57:36Z. `L0171, L0172, L0177`
- payment-service error_rate, p99 latency, CPU, memory and request rate stayed flat across 13:55-14:05, with one WARN (617ms provider latency) and no ERROR lines. `M33, M34, M32, M35, M36, L0195`
- Shallow HTTP /health checks at 14:28Z returned 200 for api-gateway, checkout-service and all direct downstream dependencies. `H01, H02, H03, H07, H08, H11`
- The first api-gateway upstream-500 log (14:00:08Z) precedes the first checkout NPE log (14:00:27Z) by 19 seconds; log clocks are not verified as aligned. `L0186, L0188`
- Log lines carry no version, instance, coupon or cart-payload fields, so per-version and payload-shape comparisons could not be made; the checkout WARN+ log query for 13:55-14:05 was rejected for budget exhaustion. `L0188, L0207`

## Assumptions
- Log timestamps across api-gateway, checkout-service and payment-service are aligned within a few seconds.
- The v2.14.0 build serves the failing checkout traffic; rollout scope (canary vs full, instance split) is unverified.
- Shallow /health checks do not exercise the checkout discount or pricing path.
- Sampled log lines are representative of the 5xx mix; the NPE log stream is either sampled, truncated or the failure path does not log.
- Metrics at 5-minute resolution place onset in the 14:00 bucket only.

## Inferred conclusions
- The 5xx originates in checkout-service rather than api-gateway; api-gateway returns 500 as a pass-through of checkout 500s on POST /api/v1/checkout. (confidence 0.80) `L0186, L0339, M12, M02`
- The v2.14.0 deploy is the leading candidate trigger because it is the only change in the window and precedes onset by about 4 minutes; this is not confirmed as the cause. (confidence 0.45) `C09, L0171, M12`
- The DiscountEngine NPE is a real v2.14.0-window failure signature but is not established as the main failure path, since it accounts for well under 1% of the roughly 900 failing requests per minute. (confidence 0.40) `L0188, M12, M15`
- An unlogged or unsampled failure path inside checkout-service is a plausible alternative explaining most failing requests; it remains unexamined. (confidence 0.20) `M12, M15, L0340`
- Payment-service is unlikely to be the origin of the failures, since its error rate and latency show no step at 14:00. (confidence 0.30) `M33, M34, L0195`
- Resource exhaustion, traffic growth and api-gateway faults are unlikely to be the primary driver of the onset. (confidence 0.55) `M01, M05, M11, M15`

## Remediation
- **immediate** - Consider rolling back checkout-service from v2.14.0 to the previous version, after confirming the rollback target, to restore checkout success while the cause is unresolved. _(The deploy is the only change in the window and onset follows it by about 4 minutes; rollback is a reversible mitigation.)_
- **immediate** - Reduce exposure to the failing path, such as disabling or bypassing the new discount engine if a flag exists, or routing checkout traffic away from v2.14.0 instances. _(Limits customer impact while the failing path is unconfirmed; feasibility depends on whether a flag or instance split exists.)_
- **immediate** - Pull per-version and per-instance 5xx and NPE counts for checkout-service from 13:55 to 14:30 and the full per-status 5xx counts by route at 1-minute resolution. _(These checks would settle whether failures concentrate on v2.14.0 and quantify the gap between logged NPEs and failing requests.)_
- **short_term** - Review DiscountEngine.apply line 88 in the v2.14.0 diff for null handling of coupon and discount fields, and add a test with null inputs. _(The NPE is a concrete defect in the new code path, but its share of failures is not yet established.)_
- **short_term** - Add deep health checks or synthetic checkout transactions that exercise the discount and pricing path. _(Current shallow /health checks returned healthy during the failure and cannot detect this class of fault.)_
- **short_term** - Add version, instance and request-id fields to checkout-service error logs and ensure 5xx responses are logged. _(Current logs cannot separate versions, compare payloads or reconcile the NPE count with the error rate.)_
- **long_term** - Add a canary stage and automatic rollback on checkout error-rate thresholds for future deploys, and align service clocks for log correlation. _(Prevents a similar pricing regression reaching full traffic; prior incident P04 had the same pattern (pricing deploy, null-field NPE, rollback).)_
- **long_term** - Add null-input tests and contract checks for pricing and discount changes in CI. _(Past incident P04 was caused by an unhandled null coupon field in new pricing code; the same class of defect recurred as a risk.)_

## Open questions
- Which checkout-service instances or pods run v2.14.0, was the rollout canary or full, and what is the previous version for rollback?
- Does the 18% checkout error rate map to the NPE, or to an unlogged or unsampled failure path? Full per-status counts are needed.
- Is there a feature flag gating the new discount engine, and was it set before 13:00?
- What is the clock offset between api-gateway and checkout-service logs, and does the 19-second gateway-first ordering hold?
- What do failing and successful checkout requests share in coupon, discount or cart fields? Request-level payloads were not logged.
- Did the checkout-service WARN/ERROR query for 13:55-14:05 contain any non-NPE failure paths? That query was rejected for budget exhaustion.

## Data gaps and tool failures (10 shown, 44 reported)
- Past incidents were not searched in this task. (reported 2x)
- Per-version and per-instance breakdown of NPE and 5xx counts was not possible: log lines have no version or instance field, and no metric by version was queried. The claim that the previous version shows near-zero error rate is untested. (reported 2x)
- checkout-service WARN+ logs for 13:55 to 14:05 UTC: query rejected with 'tool-call budget exhausted', no records returned. (reported 2x)
- Metrics are at 5-minute resolution, so the exact onset is known only to the 14:00:00 bucket. The first errors in the logs (14:00:08 gateway, 14:00:27 checkout) bracket it.
- No per-route or per-status-code breakdown of 5xx was available. Route dominance comes from a sample of WARN/ERROR log lines (30 gateway, 43 checkout), not from full counts.
- checkout-service request-level logs at INFO level were not queried, so the upstream trigger (for example a specific cart or discount config) is unverified.
- No change-history or deploy data was queried within the call budget, so a correlated release around 14:00 is not confirmed or ruled out.
- Downstream service logs (payment-service, discount service) were not queried.
- Health checks are shallow (HTTP /health only), so they do not confirm the checkout business path or the discount engine.
- 32 further gap report(s) in 32 group(s) omitted here (mostly about: returned, 5xx, metrics, query, confirmed, queried); the full list is in the run record.
