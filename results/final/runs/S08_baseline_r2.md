# Incident report S08

- **Status:** INCONCLUSIVE (contradicting evidence is 50% of the weighed evidence (max 35%))
- **System:** baseline · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** agent_finished

## Summary
Payment-service error rate jumped from about 0.2% to about 21% at 11:00 UTC, and checkout-service errors rose from about 0.3% to about 9% in the same bucket. The only change in the window is the payment-service v3.2.0 deploy at 10:57 UTC, which changed payments table writes (idempotency_key) and upgraded the ORM from 5.x to 6.x, with the schema migration run separately. Payments-db metrics stayed flat, and no database change was recorded. The most likely cause is the v3.2.0 deploy running ahead of its schema migration, but log queries timed out, so the SQL error messages could not be confirmed.

## Conclusion decision
- contradicting evidence is 50% of the weighed evidence (max 35%)
- Criteria: top `payment-service / deployment_regression` confidence 0.65, margin 0.50, 4 verified supporting / 4 contradicting items (50% contradicting); 0 evidence-backed material critic objection(s), 0 non-blocking

## Ranked hypotheses
1. **payment-service** - deployment_regression (confidence 0.65)
   - Mechanism: The v3.2.0 deploy changed the write path (idempotency_key column, ORM 6.x). If the schema migration is not applied, writes fail, causing about 21% of payment requests to error at 11:00 UTC, and checkout fails through its sync dependency.
   - Supporting evidence: `C09, M33, M12, P02`
   - Contradicting evidence: `H11, H12, M34, M32`
   - Assumptions: The migration was not applied.; Health checks do not cover write paths.
2. **payment-provider** - dependency_failure (confidence 0.15)
   - Mechanism: The external provider began rejecting or timing out payment calls at 11:00 UTC, and payment-service surfaces these as errors.
   - Supporting evidence: `M33`
   - Contradicting evidence: `H10, M34`
   - Assumptions: The provider status page is accurate or lagging.
3. **payments-db** - resource_exhaustion (confidence 0.05)
   - Mechanism: Database saturation or lock contention caused write failures.
   - Supporting evidence: none
   - Contradicting evidence: `M37, M38, M40, M41, H12`
   - Assumptions: Lock or contention problems would not show in aggregate CPU or connection metrics.

## Observed facts
- payment-service error_rate was about 0.15–0.26% from 10:00 to 10:55 UTC, then 21.26% at 11:00 UTC, peaking at 23.55% at 11:10 UTC and at 20.61% at 11:30 UTC. `M33`
- Deploy v3.2.0 to payment-service completed at 10:57 UTC: it adds idempotency_key to payments table writes and upgrades the ORM 5.x to 6.x, with the schema migration run separately. `C09`
- checkout-service error_rate rose from 0.27% at 10:55 UTC to 9.61% at 11:00 UTC and stayed between 8.4% and 9.4% through 11:30 UTC. `M12`
- payment-service latency p99 stayed between 434 and 465 ms and CPU between 31.7% and 33.8% across the window, with no step change at 11:00 UTC. `M34, M32`
- payments-db connections, CPU, disk, query latency p99 and replication lag stayed flat across 10:30–11:30 UTC. `M37, M38, M39, M40, M41`
- Past incident P02 (2026-02-11) had payment-service 500s and SQL column errors after an ORM migration, where the deploy shipped before its schema migration was applied. `P02`
- Health checks at 11:28 UTC reported payment-service, payments-db, checkout-service and payment-provider as healthy, but the health checks are shallow (e.g. HTTP /health and SELECT 1). `H11, H12, H03, H10`

## Assumptions
- The health checks do not exercise payments table writes, so they would not catch a write-path schema error.
- The payment-provider status page reflects the provider's real state.
- The v3.2.0 migration was not applied to payments-db, because no database change was recorded.
- Request volume was steady (about 58–62 req/s), so the error spike is not explained by traffic.
- The v3.2.0 deploy and the 11:00 error onset are causally linked, not coincidental.
- (unverified - no valid evidence cited) No database change was recorded for payments-db between 2026-09-07T12:00 and 11:30 UTC on 2026-09-08.
- (unverified - no valid evidence cited) payment-service WARN and ERROR log queries timed out three times, so no error messages were returned.

## Inferred conclusions
- The v3.2.0 deploy in payment-service is the most likely origin: its write-path changes (idempotency_key, ORM 6.x) fail at the 11:00 onset, and the errors are on the write path, where health checks are blind. (confidence 0.65) `C09, M33, M36, H11`
- checkout-service errors are downstream propagation from payment-service through the sync_http edge, since checkout's own health check is green. (confidence 0.70) `M12, H03`
- Database resource exhaustion is unlikely, since all payments-db metrics are flat. (confidence 0.80) `M37, M38, M40, M41`

## Remediation
- **immediate** - Roll back payment-service to the pre-v3.2.0 version (or disable the idempotency_key write path) to stop the payment failures. _(The onset coincides with the deploy at 10:57 and the 11:00 error jump.)_
- **immediate** - Check whether the v3.2.0 schema migration has been applied to payments-db and apply it if not, before any redeploy. _(The migration was run separately and no database change is recorded.)_
- **immediate** - Retrieve payment-service ERROR logs for 10:57–11:05 UTC with a narrower query (e.g. contains 'column' or 'SQL') to confirm the failure mode. _(Log queries timed out, so the mechanism is unconfirmed.)_
- **short_term** - Add a deploy gate that blocks rollout until schema migrations are applied. _(Matches past incident P02.)_
- **long_term** - Add a write-path synthetic check for payment-service so health checks catch failures like this. _(Current health checks stayed green during the outage.)_

## Open questions
- What do the payment-service error messages say? The log backend timed out.
- Was the v3.2.0 schema migration applied to payments-db, and when?
- Do the payment failures come from payment-provider responses or from the local write path? The provider status page is not an independent signal.

## Data gaps and tool failures (2 shown, 2 reported)
- query_logs(start=2026-09-08T10:00:00Z, end=2026-09-08T11:30:00Z, service=payment-service, min_level=WARN, limit=20) -> timeout: Timed out after 10000 ms: log backend query for payment-service exceeded deadline (gave up after 3 attempts)
- query_logs(start=2026-09-08T10:55:00Z, end=2026-09-08T11:10:00Z, service=payment-service, min_level=ERROR, limit=10) -> timeout: Timed out after 10000 ms: log backend query for payment-service exceeded deadline (gave up after 3 attempts)
