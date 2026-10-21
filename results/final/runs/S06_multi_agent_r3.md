# Incident report S06

- **Status:** INCONCLUSIVE (contradicting evidence is 56% of the weighed evidence (max 35%))
- **System:** multi_agent · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** max_rounds_reached

## Summary
Incident S06 is inconclusive: the system determination is that contradicting evidence makes up 56% of weighed evidence against a 35% maximum, so no root cause is asserted. The strongest candidate (H1) is an inventory-db replication break at about 12:59:32Z with the endpoint resolving to read-only standby db-inv-2, which is awaiting manual promotion, and inventory reservation UPDATEs failing with SQLSTATE 25006 from 13:00:29Z. H2 (inventory-service misconfigured to write to the standby) fits the same error signature and is not excluded, because no connection-string or DSN evidence was retrieved. The 15% inventory and 7% checkout error rates cannot be reconciled with the roughly 40 sampled ERROR lines, and checkout's link to inventory rests on timing only. The primary db-inv-1 was never observed directly, and the DNS, config and approval records were not obtained within the investigation budget. Mitigation should focus on restoring a writable primary and confirming write routing, pending the checks listed in open_questions.

## Conclusion decision
- contradicting evidence is 56% of the weighed evidence (max 35%)
- Criteria: top `inventory-db / infrastructure_failure` confidence 0.50, margin 0.25, 4 verified supporting / 5 contradicting items (56% contradicting); 2 evidence-backed material critic objection(s), 4 non-blocking
  - objection: unsupported_claim: The analysis asserts that inventory writes are routed to read-only standby db-inv-2 and that db-inv-1 is unavailable. No ledger record shows the write connectio [L0185, L0206, H06, L0180, L0183]
  - objection: alternative_not_ruled_out: H2 (inventory-service connection target misconfigured to the standby) fits the same 25006 error signature and is not excluded. The replication break at 12:59:32 [L0185, M16, H07, L0180]

## Ranked hypotheses
1. **inventory-db** - infrastructure_failure (confidence 0.50)
   - Mechanism: The replication stream from primary db-inv-1 broke at about 12:59:32Z (lag rose from 0.3s to 48s, connections dropped from 93 to 20 at 13:00), and the endpoint now resolves to standby db-inv-2, which is read-only and awaiting manual promotion. Inventory UPDATE stock_reservations statements fail with SQLSTATE 25006 from 13:00:29Z while reads and the liveness check still succeed.
   - Supporting evidence: `L0180, L0183, M20, M16, L0199, L0185, L0317, H06, H07, M22`
   - Contradicting evidence: `M12`
   - Assumptions: The endpoint switch to db-inv-2 occurred around 12:59-13:00, not later; The 13:28 degraded snapshot reflects onset-time state; Checkout errors are downstream of inventory reservation failures; db-inv-1 is actually unavailable, which is not verified
2. **inventory-service** - config_error (confidence 0.25)
   - Mechanism: inventory-service's database connection target was misconfigured to point at read-only standby db-inv-2, so writes fail with SQLSTATE 25006 from the time of the change. The replication break at 12:59 would then be a coincident event rather than the origin of the write failures.
   - Supporting evidence: `L0185, L0317, H07`
   - Contradicting evidence: `M16`
   - Assumptions: Change history is complete for inventory-service and inventory-db (zero changes 11:00-13:30); Connection-string content was never inspected; The replication break and the endpoint state are independent

## Observed facts
- inventory-service error_rate rose from about 0.2% to 15.43% at 13:00:00Z and peaked at 15.85% at 13:05; it was 14.93% at 13:30. `M22`
- checkout-service error_rate rose from about 0.3% to 6.87% at 13:00:00Z and was 7.05% at 13:30. `M12`
- inventory-db logged replication errors 'lost connection to primary db-inv-1' at 12:59:32Z and 13:00:16Z; replication_lag_s rose from 0.3s to 48.38s at 13:00 and connections fell from 93 to 20. `L0180, L0183, M20, M16`
- All sampled inventory-service ERROR lines from 13:00:29Z through 13:30:00Z share the message 'UPDATE stock_reservations failed: cannot execute UPDATE in a read-only transaction (SQLSTATE 25006)'. `L0185, L0317, L0206`
- At 13:03:34Z inventory-db logged that standby db-inv-2 is still in recovery with promotion pending manual approval. `L0199`
- At 13:28:00Z the inventory-db health check was degraded with its primary endpoint resolving to db-inv-2 (standby, read-only); the inventory-service health check was green and checks liveness only. `H06, H07`
- inventory-service latency, CPU, request rate and inventory-db CPU, latency and disk showed no step change at 13:00; before 13:00 the only inventory warnings were heap and cache-miss warnings. `M23, M21, M25, M17, M19, M18, L0034, L0112`
- No change events were returned for inventory-service or inventory-db in the windows queried, and no log line records a promotion, failover or endpoint change. `L0199`
- checkout-service has no ERROR or WARN log lines mentioning inventory between 12:55 and 13:10. `L0083, L0151`

## Assumptions
- The endpoint switch to db-inv-2 occurred around 12:59-13:00 rather than later, since the 13:28 snapshot is a single later observation.
- db-inv-1 is actually unavailable; its telemetry could not be retrieved under that name.
- Checkout errors are downstream of inventory reservation failures.
- Change history is complete for inventory-service and inventory-db over the window queried.
- inventory-service's health check does not exercise database writes.
- The sampled ERROR lines are representative of the failure signature, although the sample is capped and incomplete.

## Inferred conclusions
- Inventory reservation writes are failing because they reach a read-only database endpoint, most likely db-inv-2 after the replication break; this is the leading candidate (H1) but is not confirmed, because no log shows the write connection target. (confidence 0.50) `L0185, L0180, L0199, H06`
- A misconfigured inventory-service connection target pointing at standby db-inv-2 (H2) remains a viable alternative that the available evidence does not rule out. (confidence 0.25) `L0185, H07, M16`
- Database CPU, latency and disk did not cause the failure, since they stayed flat through the window. (confidence 0.60) `M17, M19, M18`
- Checkout's error increase is a downstream effect of inventory reservation failures, based on timing only. (confidence 0.40) `M12, M22`
- The 15% and 7% error rates are not explained by the sampled log volume, so the failure is either broader than the 25006 signature or the logs are incomplete. (confidence 0.50) `M22, L0185, L0317`
- Past incident P03 (cache eviction storm) is a weak match and is not supported by the current cache health or the read-only error signature. (confidence 0.20) `P03, H05`

## Remediation
- **immediate** - Restore a writable primary for inventory-db (approve and complete promotion of a writable node, or restore db-inv-1) and confirm inventory writes succeed. _(Reservation writes fail with SQLSTATE 25006 on a read-only standby, and the promotion is pending manual approval.)_
- **immediate** - Verify the database host used by inventory-service for stock_reservations writes via live connection or DSN inspection. _(This separates H1 from H2 and determines whether a config rollback is needed.)_
- **immediate** - Pause or route checkout reservations to a fallback or queue while writes fail, to limit customer impact. _(Checkout is seeing about 7% errors and inventory about 15%, and no safe write path is confirmed.)_
- **short_term** - Add a write-path health check to inventory-service that performs a test write or checks read-only state. _(The current liveness check stayed green while reservations failed, which hid the outage.)_
- **short_term** - Add alerting on replication lag and standby read-only state for inventory-db. _(The replication break and lag rise preceded the errors by about 30 seconds and were not alerted.)_
- **short_term** - Collect unsampled ERROR counts and checkout reserve call errors to reconcile the 15% and 7% rates. _(The sampled logs do not explain the reported error rates.)_
- **long_term** - Document and automate failover approval and endpoint-switching procedures for inventory-db, with change records for any endpoint change. _(A promotion awaiting manual approval and an endpoint change with no recorded change indicate a process gap.)_

## Open questions
- Did db-inv-1 fail, become unreachable, or stay up at 12:59:32Z? Its health and logs must be checked under the correct host name.
- Which host did inventory-service write to? Connection-open or DSN log lines for 12:50-13:05 are needed.
- When and by whom did the inventory-db primary endpoint change to db-inv-2? DNS or endpoint resolution history and approval records are needed.
- What explains the pending promotion of db-inv-2, and who is responsible for approving it?
- What accounts for the gap between the 15% error rate and the roughly 40 sampled ERROR lines, and does checkout's 7% come from reserve calls to inventory?
- Was the inventory-service connection-string or pool configuration changed before 13:05? The configuration content was never inspected.

## Data gaps and tool failures (10 shown, 43 reported)
- get_change_history for service inventory-db (window ending 2026-09-06T13:30:00Z) was rejected: budget exhausted. No endpoint/DNS change records were obtained. (reported 2x)
- The inventory ERROR log count is capped at 50 returned lines, so the 40 ERROR lines are a sample, not the full set. Error volume and SKU/warehouse spread cannot be measured from this sample.
- Logs carry no HTTP status codes, endpoints, SKUs or warehouse IDs on the error lines, so error-signature breakdown by request pattern is not possible.
- No database telemetry was queried (I did not query the database service for read-only state, replication or failover events). Read-only cause is unverified.
- Checkout-service has no ERROR lines explaining its ~7% error rate, so the checkout failure mechanism and its exception types are unknown.
- The 13:00 metric bucket is 5-minute resolution, so the exact onset is bounded to the 12:55–13:00 interval by the metrics, and to 13:00:29Z by the first log line.
- Infra events were not returned by the change-history queries. get_change_history was not filtered by change_type, so this gap is unlikely to be a filter problem. Failover or DNS events may still be missing from the log.
- No telemetry (error rates, DB logs) was accessible through my tools, so the 15% error rate and the ~13:00 onset are unverified by this role.
- Health checks are shallow (inventory-service checks liveness only). inventory-db health is a single snapshot at 13:28:00Z and does not show when the degradation started.
- 33 further gap report(s) in 33 group(s) omitted here (mostly about: inventory-service, inventory-db, queried, checked, error, unknown); the full list is in the run record.
