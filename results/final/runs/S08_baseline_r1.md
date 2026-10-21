# Incident report S08

- **Status:** CONCLUSIVE (confidence 0.60, margin 0.40, 5 verified supporting and 2 contradicting evidence items (29%))
- **System:** baseline · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** agent_finished
- **Root cause:** `payment-service` - deployment_regression (confidence 0.60)

## Summary
payment-service error rate jumped from about 0.2% to about 21% starting 11:00:00Z, one reading after the v3.2.0 deploy at 10:57:00Z. v3.2.0 changed payments table writes (idempotency_key) and upgraded the ORM 5.x to 6.x, with the schema migration run separately. Database, CPU, memory, latency and traffic metrics stayed flat, and no config or database changes were recorded. The leading hypothesis is that v3.2.0 was deployed without its schema migration, causing write failures. Log queries timed out on all attempts, so the error signature is unconfirmed, and confidence is moderate.

## Conclusion decision
- confidence 0.60, margin 0.40, 5 verified supporting and 2 contradicting evidence items (29%)
- Criteria: top `payment-service / deployment_regression` confidence 0.60, margin 0.40, 5 verified supporting / 2 contradicting items (29% contradicting); 0 evidence-backed material critic objection(s), 0 non-blocking

## Ranked hypotheses
1. **payment-service** - deployment_regression (confidence 0.60)
   - Mechanism: v3.2.0 writes idempotency_key and uses ORM 6.x against payments tables; if the migration was not applied, or ORM 6 mapping differs, payment writes fail, giving about 21% errors and checkout 5xx via sync_http.
   - Supporting evidence: `C09, M33, M36, P02, D04`
   - Contradicting evidence: `H11, H12`
   - Assumptions: Migration not applied (unverified).; Errors are write-path only.
2. **payments-db** - config_error (confidence 0.20)
   - Mechanism: A schema or config difference on the database side causes write rejections for the new columns, without showing up in CPU, connections or the health check.
   - Supporting evidence: `M33`
   - Contradicting evidence: `M37, M38, M40, M41, H12`
   - Assumptions: The database has no tracked changes, so the schema change is untracked.
3. **payment-provider** - dependency_failure (confidence 0.10)
   - Mechanism: The external provider starts rejecting or timing out payment calls, causing the failures.
   - Supporting evidence: `M33`
   - Contradicting evidence: `H10, M34`
   - Assumptions: The status page reflects the real provider state.

## Observed facts
- payment-service error_rate went from 0.15–0.26% (10:00–10:55) to 21.26% at 11:00:00Z, peaking at 23.55% at 11:10:00Z and at 20.61% at 11:30:00Z. `M33`
- A deploy of payment-service v3.2.0 completed at 10:57:00Z: it adds idempotency_key to payments table writes and upgrades the ORM 5.x to 6.x; the schema migration was run separately. `C09`
- payment-service request_rate stayed between 57.8 and 62.3 req/s with no visible surge across 10:00–11:30. `M36`
- payment-service latency_p99 stayed between 434 and 465 ms; cpu_pct 31.7–33.8%; memory_pct 53–57%. `M34, M32, M35`
- payments-db connections (116–125), cpu (33.8–35.9%), query_latency_p99 (11.6–12.5 ms) and replication lag (about 0.4 s) stayed flat across the window. `M37, M38, M40, M41`
- The payments-db health check passed (SELECT 1 ok) and payment-service /health returned 200 at 11:28:00Z. `H12, H11`
- The only infra change was the Kubernetes node pool upgrade at 02:00Z, about nine hours before onset. `C08`
- A past incident (2026-02-11) had payment-service 500s and SQL column errors after an ORM migration, where the deploy shipped before its schema migration was applied. `P02`

## Assumptions
- The v3.2.0 schema migration has not been applied to payments-db, based on the 'run separately' note; this has not been verified.
- The health checks are shallow and do not exercise payments table writes, so a passing health check does not rule out write failures.
- The payments-db change history shows no changes, so the database schema was not altered by a tracked change.
- The error rate of about 21% matches the share of payment writes that fail, which is consistent with the new code path hitting a missing column or type mismatch.
- (unverified - no valid evidence cited) payment-service log queries (WARN and ERROR, and narrow 'column' queries) timed out on every attempt, so no log lines were retrieved.

## Inferred conclusions
- v3.2.0 deployed without its schema migration (or with an ORM 6.x incompatibility) is the most likely root cause, with payment-service as the origin. (confidence 0.60) `C09, M33, P02`
- The payment-provider and database infrastructure are unlikely to be the origin, because their signals are flat and the database health check passes. (confidence 0.60) `M37, M38, M40, M41, H10, H12`
- Checkout errors are most likely propagated from payment-service via the sync_http dependency; checkout-service's own health check is shallow and reports healthy. (confidence 0.60) `D04, H03`
- The TLS certificate expiry from P06 is an unlikely explanation, since the error onset coincides with a deploy and no certificate change was recorded. (confidence 0.30) `P06, C09`

## Remediation
- **immediate** - Roll back payment-service to v3.1.x now to stop failed payments. _(The deploy at 10:57Z immediately precedes the onset at 11:00Z, and rollback is the fastest way to restore service.)_
- **immediate** - Confirm whether the v3.2.0 schema migration has been applied to payments-db; if not, run it or hold the rollback until the schema is verified. _(A deploy without its migration would produce write errors, which the logs could not confirm.)_
- **immediate** - Check payment-service error logs once the log backend recovers, looking for SQL column or type errors. _(Log queries timed out, so the error signature is unverified.)_
- **short_term** - Add a deploy gate that blocks rollout until migrations are applied and a write-path smoke test passes. _(Repeats the 2026-02-11 failure mode (P02).)_
- **short_term** - Make health checks exercise payments table writes, and add alerting on payment-service error rate. _(The current /health check reported healthy during a 21% error rate.)_
- **long_term** - Stage ORM major-version upgrades separately from behavioural changes. _(v3.2.0 combined an ORM major upgrade with a schema change.)_

## Open questions
- What do the payment-service error log lines show (SQL column error, ORM mapping error, or provider error)? Logs timed out on all retries.
- Was the v3.2.0 schema migration applied, and when?
- Is the 21% error rate limited to payment writes, or does it also affect reads and the payment-provider calls?
- Did the payment-provider return errors? Its health was reported only from the status page.
- Why are checkout-service's health checks healthy during a sustained error rate?

## Data gaps and tool failures (3 shown, 3 reported)
- query_logs(start=2026-09-08T10:00:00Z, end=2026-09-08T11:30:00Z, service=payment-service, min_level=WARN, limit=30) -> timeout: Timed out after 10000 ms: log backend query for payment-service exceeded deadline (gave up after 3 attempts)
- query_logs(start=2026-09-08T10:55:00Z, end=2026-09-08T11:30:00Z, service=payment-service, min_level=ERROR, limit=10) -> timeout: Timed out after 10000 ms: log backend query for payment-service exceeded deadline (gave up after 3 attempts)
- query_logs(start=2026-09-08T11:00:00Z, end=2026-09-08T11:05:00Z, service=payment-service, min_level=INFO, contains=column, limit=5) -> timeout: Timed out after 10000 ms: log backend query for payment-service exceeded deadline (gave up after 3 attempts)
