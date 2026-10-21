# Incident report S08

- **Status:** INCONCLUSIVE (contradicting evidence is 44% of the weighed evidence (max 35%))
- **System:** multi_agent · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** tool_budget_exhausted

## Summary
Incident S08 is inconclusive: payment-service error rate stepped from about 0.2% to about 21% at 11:00 UTC and stayed near 20-24% through 11:30, while checkout-service 500 warnings began at 11:00:14Z. The only change in the window is payment-service deploy v3.2.0 at 10:57Z, about 3 minutes before onset, which adds idempotency_key writes and an ORM 5.x to 6.x upgrade. Payment-service's own error logs could not be retrieved because every query timed out, and payment-provider has no telemetry, so the failing path is unverified. The system's determination is inconclusive because the leading hypothesis (H1, confidence 0.60) does not meet the criteria, with contradicting evidence at 44% of weighted evidence against a 35% maximum. The deploy is the leading candidate but no cause is asserted; the schema migration status is unknown and checkout's ~9% versus payment-service's ~21% error rate is unexplained.

## Conclusion decision
- contradicting evidence is 44% of the weighed evidence (max 35%)
- Criteria: top `payment-service / deployment_regression` confidence 0.60, margin 0.25, 5 verified supporting / 4 contradicting items (44% contradicting); 1 evidence-backed material critic objection(s), 5 non-blocking
  - objection: alternative_not_ruled_out: The payment-provider failure (H3) is not excluded by the evidence. Provider telemetry is entirely absent, and the status-page check ran after onset and is shall [M33, C09, H10]

## Ranked hypotheses
1. **payment-service** - deployment_regression (confidence 0.60)
   - Mechanism: Deploy v3.2.0 at 10:57Z added idempotency_key writes and an ORM 5.x to 6.x upgrade on the payments write path, so writes fail and payment-service returns 500s from about 11:00, which checkout then propagates as its own 500 warnings. Shallow SELECT 1 and /health checks would not detect a write-path fault.
   - Supporting evidence: `C09, M33, M12, L0182, L0333, D04, H12`
   - Contradicting evidence: `H11`
   - Assumptions: Onset at about 11:00 is caused by C09 rather than coincidence; Errors are on the write path changed by C09; Payment-service log data that could confirm the exception type remains unavailable
2. **payment-service** - config_error (confidence 0.35)
   - Mechanism: The v3.2.0 schema migration adding the idempotency_key column was run separately and may not have been applied, so inserts that reference the column fail with SQL errors and return 500, matching the P02 pattern. This is a specific sub-case of H1 with the migration as the fault.
   - Supporting evidence: `C09, P02, L0182`
   - Contradicting evidence: none
   - Assumptions: The migration was not applied before traffic reached the new build; A missing column produces 500s rather than being silently tolerated
3. **payment-provider** - dependency_failure (confidence 0.20)
   - Mechanism: A failure in calls from payment-service to the external payment provider begins at about 11:00 and surfaces as payment-service 500s to checkout, with no payments-db or deploy change needed to explain it. Its status-page check was taken after onset and does not show partial call failures.
   - Supporting evidence: `M33, D09, H10`
   - Contradicting evidence: `C09`
   - Assumptions: Provider failures are partial and not visible on the status page; Provider telemetry being absent does not mean the provider is healthy

## Observed facts
- payment-service error_rate was about 0.2% from 10:00 to 10:55, then 21.26% at 11:00, peaking at 23.55% at 11:10 and 20.61% at 11:30. `M33`
- checkout-service error_rate was about 0.3% before 11:00, then 9.61% at 11:00 and 9.35% at 11:30. `M12`
- Checkout-service logged 25 'payment-service returned 500 Internal Server Error' warnings, the first at 11:00:14Z and the last at 11:30:00Z. `L0182, L0333`
- Deploy v3.2.0 to payment-service completed at 10:57:00Z, adding idempotency_key to payments table writes and upgrading the ORM from 5.x to 6.x; the schema migration was run separately. `C09`
- payment-service CPU, memory, latency p99 and request rate stayed flat across 10:55-11:15 with no step change at 11:00. `M32, M34, M35, M36`
- payments-db connections, CPU, disk, query p99 latency and replication lag stayed flat across 10:50-11:30; only two slow refunds SELECT warnings appeared, both before 11:00. `M37, M38, M39, M40, M41, L0155, L0170`
- payment-provider has no logs or metrics in the telemetry store; its status-page check at 11:28Z reported operational. `H10`
- Health checks at 11:28Z reported payment-service /health 200, payments-db accepting connections with SELECT 1 ok, and checkout-service /health 200; these checks do not exercise payment writes. `H11, H12, H03`

## Assumptions
- The onset at about 11:00 is caused by deploy C09 rather than by coincidence.
- The failing errors are on the payments write path changed by C09 rather than in provider calls.
- The v3.2.0 idempotency_key schema migration may or may not have been applied before traffic reached the new build; its status is unknown.
- Provider failures may be partial and invisible on the status page, and absent provider telemetry does not mean the provider is healthy.
- Shallow health checks (HTTP /health and SELECT 1) would not detect a write-path fault.
- (unverified - no valid evidence cited) Every payment-service log query timed out after 3 attempts, so no payment-service error signatures, status codes or downstream call failures were retrieved.

## Inferred conclusions
- The error step at about 11:00 is a discrete event, not a capacity or load problem, since resource and traffic metrics were flat. (confidence 0.60) `M32, M34, M36, M33`
- Payment-service deploy v3.2.0 (C09) is the leading candidate for the onset, with a write-path regression as the most likely mechanism, but this is not confirmed because payment-service error logs are unavailable. (confidence 0.60) `C09, M33, L0182`
- A missing idempotency_key column from an unapplied migration is a possible sub-mechanism of the deploy regression, but migration status is unknown. (confidence 0.35) `C09, P02`
- A payment-provider call failure starting at 11:00 cannot be excluded, because the provider has no telemetry and its status-page check was taken after onset. (confidence 0.20) `H10, M33`
- payments-db is unlikely to be the origin, because its aggregate metrics and logs show no failure at 11:00, although aggregate metrics would not reveal a specific write error. (confidence 0.40) `M37, M38, M40, M41, L0155, L0170`
- Checkout-service is probably a downstream victim of payment-service errors rather than the origin, since its 500 warnings begin after payment-service's error step. (confidence 0.50) `L0182, M33, M12`

## Remediation
- **immediate** - Consider rolling back payment-service to v3.1.3 as an immediate mitigation, after confirming with the on-call owner that the rollback is safe for the idempotency_key data already written. _(The deploy is the only change near onset, and rollback is a reversible test of whether the error rate recovers, though the determination remains inconclusive.)_
- **immediate** - Retrieve payment-service ERROR logs for 10:55-11:10 using a different log source or narrower query, to identify exception types and the failing endpoint or downstream call. _(This is the single check that would most directly separate a write-path fault from a provider-call failure.)_
- **immediate** - Verify whether the v3.2.0 idempotency_key migration was applied to payments-db and when, relative to 10:57Z. _(A missing column would produce the observed 500 pattern and matches past incident P02.)_
- **short_term** - Add a deep health check or canary write that exercises the payments table and the provider call path, and run it against payment-service. _(The existing shallow checks reported healthy during a 22% error rate and cannot detect a write-path fault.)_
- **short_term** - Obtain payment-provider call error rate and latency, or instrument the provider integration, so the provider hypothesis can be tested. _(Provider telemetry is entirely absent, so H3 cannot be excluded.)_
- **short_term** - Investigate why checkout's error rate (~9%) is lower than payment-service's (~21%), checking for partial routing or retries masking failures. _(The gap weakens the claim that payment-service is the sole origin and may reveal retry masking.)_
- **long_term** - Make schema migrations a gated step of deploys, so code is not released ahead of its migration. _(This would prevent recurrence of the P02 pattern, which is the closest past incident.)_
- **long_term** - Extend health checks and alerting to cover payment write success and provider call success, not only HTTP status and SELECT 1. _(Telemetry gaps and shallow checks delayed diagnosis of this incident.)_

## Open questions
- What exception types and status codes does payment-service return from 10:55-11:10, and on which endpoint or downstream call?
- Was the v3.2.0 idempotency_key migration applied to payments-db, and at what time?
- Does reverting to v3.1.3 restore the payment-service error rate to baseline?
- What is the payment-provider call error rate for 10:55-11:30?
- Why is checkout's error rate about half of payment-service's, and is there partial routing or retry masking?

## Data gaps and tool failures (10 shown, 27 reported)
- query_logs(start=2026-09-08T10:00:00Z, end=2026-09-08T11:30:00Z, service=payment-service, min_level=WARN, limit=50) -> timeout: Timed out after 10000 ms: log backend query for payment-service exceeded deadline (gave up after 3 attempts)
- query_logs(start=2026-09-08T10:55:00Z, end=2026-09-08T11:10:00Z, service=payment-service, min_level=ERROR, limit=20) -> timeout: Timed out after 10000 ms: log backend query for payment-service exceeded deadline (gave up after 3 attempts)
- query_logs(start=2026-09-08T10:58:00Z, end=2026-09-08T11:05:00Z, service=payment-service, min_level=ERROR, limit=50) -> timeout: Timed out after 10000 ms: log backend query for payment-service exceeded deadline (gave up after 3 attempts)
- query_logs(start=2026-09-08T10:50:00Z, end=2026-09-08T11:30:00Z, service=payment-service, min_level=WARN, limit=10) -> timeout: Timed out after 10000 ms: log backend query for payment-service exceeded deadline (gave up after 3 attempts)
- query_logs(start=2026-09-08T11:00:00Z, end=2026-09-08T11:02:00Z, service=payment-service, min_level=ERROR, limit=20) -> timeout: Timed out after 10000 ms: log backend query for payment-service exceeded deadline (gave up after 3 attempts)
- payment-service log queries timed out on all 3 attempts for both the broad window (10:00–11:30, WARN) and the narrow window (10:55–11:10, ERROR). The server-side error signatures, exception types and downstream call failures (timeouts vs 5xx vs auth) for payment-service are therefore unknown.
- Checkout logs were only the WARN/ERROR lines (27 total, capped at 50), so INFO-level context around the onset is missing.
- Only error_rate, cpu_pct, memory_pct, latency_p99_ms and request_rate were checked for payment-service. Database and downstream dependency metrics (e.g. issuer or fraud calls) were not queried, so which payment-service downstream call fails remains unknown.
- Only the 11:00 onset is confirmed. Its exact start within the 10:55–11:00 interval is not resolvable from the 5-minute metric buckets.
- 18 further gap report(s) in 18 group(s) omitted here (mostly about: error, payments-db, logs, checks, telemetry, payment-provider); the full list is in the run record.
