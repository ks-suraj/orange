# Incident report S08

- **Status:** INCONCLUSIVE (contradicting evidence is 38% of the weighed evidence (max 35%))
- **System:** baseline · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** agent_finished

## Summary
payment-service error rate jumped from about 0.2% to 21% at 11:00 UTC, one step after the v3.2.0 deploy at 10:57 UTC. v3.2.0 changed payments-table writes (idempotency_key) and upgraded the ORM 5.x to 6.x, with the schema migration run separately. Infrastructure, database and dependency health look normal, and the payment-service log backend timed out on every query, so the leading hypothesis (deploy ahead of its schema migration) is unverified. Checkout-service errors are most likely downstream of payment-service failures.

## Conclusion decision
- contradicting evidence is 38% of the weighed evidence (max 35%)
- Criteria: top `payment-service / deployment_regression` confidence 0.60, margin 0.40, 5 verified supporting / 3 contradicting items (38% contradicting); 0 evidence-backed material critic objection(s), 0 non-blocking

## Ranked hypotheses
1. **payment-service** - deployment_regression (confidence 0.60)
   - Mechanism: The v3.2.0 deploy (idempotency_key writes plus ORM 5.x to 6.x) fails on payments-table writes, probably because the schema migration is missing or incompatible. Failing writes return errors to checkout, and shallow health checks do not detect it.
   - Supporting evidence: `C09, M33, M36, P02, H11`
   - Contradicting evidence: `M34, M32, M35`
   - Assumptions: The migration was not applied, which has not been verified.; Health checks do not exercise writes.
2. **payments-db** - dependency_failure (confidence 0.20)
   - Mechanism: A schema or permission change on payments-db (for example from the separately run migration) makes certain writes fail, while reads and connection counts look normal.
   - Supporting evidence: `M37, M38, M40`
   - Contradicting evidence: `H12, M41`
   - Assumptions: The migration touched the database at about 11:00 UTC; no database change event was returned.
3. **payment-provider** - dependency_failure (confidence 0.10)
   - Mechanism: The external payment provider rejects or times out payment calls, causing payment failures.
   - Supporting evidence: `M33`
   - Contradicting evidence: `H10`
   - Assumptions: The status page is accurate.

## Observed facts
- payment-service error_rate was 0.15–0.26% from 10:00 to 10:55 UTC, then 21.26% at 11:00 UTC, peaking at 23.55% at 11:10 UTC and at 20.61% at 11:30 UTC. `M33`
- Change C09 (deploy v3.2.0 to payment-service, status completed) was recorded at 10:57 UTC. It adds idempotency_key to payments table writes and upgrades the ORM 5.x to 6.x; the schema migration was run separately. `C09`
- payment-service request_rate stayed between 57.8 and 62.3 req/s across the window, with no step change at 11:00 UTC. `M36`
- payment-service cpu_pct (31.7–33.8%) and memory_pct (53–57%) stayed flat across the window. `M32, M35`
- payment-service latency_p99_ms stayed between 434 and 465 ms before and after 11:00 UTC. `M34`
- payments-db connections (116–125), cpu (33.8–35.9%), query_latency_p99 (11.6–12.5 ms) and replication lag (about 0.4 s) show no change at 11:00 UTC. `M37, M38, M40, M41`
- The health checks at 11:28 UTC report payment-service, payments-db, payment-provider and checkout-service as healthy; the payments-db check is SELECT 1 only. `H11, H12, H10, H03`
- Past incident P02 (2026-02-11) describes payment-service 500 errors and SQL column errors after an ORM migration, where the deploy shipped before its schema migration was applied. `P02`
- The only infra change in the window is the node pool upgrade (C08) at 02:00 UTC, roughly nine hours before the errors began. `C08`

## Assumptions
- The schema migration for v3.2.0 was not applied, or was applied incompletely, before traffic reached the new version (not verified; the migration record was not in the change history).
- The health checks are shallow and do not exercise payments-table writes or the new ORM code path.
- payment-provider status page is an accurate indicator of provider health.
- checkout-service errors are caused by payment-service errors, because checkout calls payment-service synchronously (edge D04).
- (unverified - no valid evidence cited) Every query to payment-service logs (WARN/ERROR, a 10:55–11:30 ERROR window, and a 'column' search) timed out after 3 attempts, so no log lines were retrieved.

## Inferred conclusions
- The most likely cause is the v3.2.0 deploy: the new idempotency_key writes or the ORM 6.x change fail against the payments schema, which would produce a fault only on write paths and explain why health checks pass. (confidence 0.60) `C09, M33, P02, H11, H12`
- The fault most likely originates in payment-service, not payments-db or payment-provider. Database metrics are flat and the database health check is shallow, but the database has not been shown to be fully clean. (confidence 0.60) `M37, M38, M40, M41, H12`
- The incident is not explained by traffic, capacity or the 02:00 node upgrade: request rate, CPU and memory are flat, and the node upgrade was about nine hours earlier. (confidence 0.70) `M36, M32, M35, C08`
- Confidence is limited because the log backend is unavailable, so the migration/ORM error signature has not been confirmed. The margin over the runner-up is modest. (confidence 0.50)

## Remediation
- **immediate** - Roll back payment-service to the pre-v3.2.0 version (or disable the idempotency_key write path via feature flag if one exists). _(The error onset coincides with the deploy at 10:57 UTC; rollback is the fastest way to stop payment failures.)_
- **immediate** - Check whether the v3.2.0 schema migration has been applied to payments-db, and apply it if it is missing. _(Past incident P02 had the same pattern: the deploy shipped before its migration.)_
- **immediate** - Restore log access for payment-service (the log backend timed out) and confirm the exception class and SQL error text. _(Without logs the root cause is unconfirmed.)_
- **short_term** - Watch checkout-service error rates and payment-provider responses after rollback to confirm recovery. _(Confirms that checkout errors are downstream and that the provider is not involved.)_
- **short_term** - Add a deploy gate that blocks release until schema migrations are applied. _(Prevents recurrence of P02.)_
- **long_term** - Make health checks exercise a payments-table write path and the ORM code path. _(The current health checks passed during a 21% error rate.)_
- **long_term** - Stage ORM major-version upgrades separately from feature changes, with canary coverage. _(Reduces the blast radius of combined changes.)_

## Open questions
- What exception does payment-service raise after 11:00 UTC? The log backend timed out, so this is unknown.
- Was the v3.2.0 schema migration applied, and when?
- Does the error rate split by endpoint or operation (idempotency writes versus reads)?
- Is checkout-service's 5xx error rate tracking payment-service's, and does it have its own errors?
- Could the payment-provider or a TLS certificate issue explain the failures? No evidence was found for either, but the provider check is only a status page.

## Data gaps and tool failures (3 shown, 3 reported)
- query_logs(start=2026-09-08T10:00:00Z, end=2026-09-08T11:30:00Z, service=payment-service, min_level=WARN, limit=20) -> timeout: Timed out after 10000 ms: log backend query for payment-service exceeded deadline (gave up after 3 attempts)
- query_logs(start=2026-09-08T10:55:00Z, end=2026-09-08T11:30:00Z, service=payment-service, min_level=ERROR, limit=10) -> timeout: Timed out after 10000 ms: log backend query for payment-service exceeded deadline (gave up after 3 attempts)
- query_logs(start=2026-09-08T11:00:00Z, end=2026-09-08T11:10:00Z, service=payment-service, min_level=INFO, contains=column, limit=5) -> timeout: Timed out after 10000 ms: log backend query for payment-service exceeded deadline (gave up after 3 attempts)
