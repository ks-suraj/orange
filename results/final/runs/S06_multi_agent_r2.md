# Incident report S06

- **Status:** INCONCLUSIVE (contradicting evidence is 50% of the weighed evidence (max 35%))
- **System:** multi_agent · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** tool_budget_exhausted

## Summary
Stock reservation failures in inventory-service began at 13:00:29Z and continued at a steady cadence through 13:30Z, with the error rate rising from about 0.2% to about 15%. Almost all errors are 'cannot execute UPDATE in a read-only transaction (SQLSTATE 25006)' on stock_reservations. inventory-db lost its replication connection to primary db-inv-1 just before onset, and at 13:28Z its health check reported the primary endpoint resolving to db-inv-2, a read-only standby. The system determination is INCONCLUSIVE: the leading hypothesis (H1, endpoint repointed to read-only standby, confidence 0.60) has contradicting evidence at 50% of weighed evidence, above the 35% limit, and the stale-connection-pool alternative (H2, 0.25) cannot be excluded. Checkout-service impact is not confirmed by its logs.

## Conclusion decision
- contradicting evidence is 50% of the weighed evidence (max 35%)
- Criteria: top `inventory-db / infrastructure_failure` confidence 0.60, margin 0.35, 5 verified supporting / 5 contradicting items (50% contradicting); 1 evidence-backed material critic objection(s), 5 non-blocking
  - objection: ignored_contradiction: Replication and connections recovered at 13:10 but the read-only UPDATE errors continue at a steady cadence to 13:30. H1 attributes this to the endpoint still r [M16, M20, M22, L0317, H06]

## Ranked hypotheses
1. **inventory-db** - infrastructure_failure (confidence 0.60)
   - Mechanism: At about 12:59-13:00 inventory-db lost its replication connection to primary db-inv-1, and connections and lag disturbed; the primary endpoint now resolves to db-inv-2, a read-only standby, so inventory-service UPDATE stock_reservations writes fail with SQLSTATE 25006 from 13:00:29. The liveness-only health check stays green.
   - Supporting evidence: `L0180, L0183, L0185, L0317, M16, M20, M22, H06, H07, D10`
   - Contradicting evidence: `M16, M20`
   - Assumptions: The endpoint repoint or failover is the origin, though its timing and cause are not in change records; Connection and lag recovery at 13:10 does not fix the endpoint, so errors persist to 13:30; Node role of db-inv-2 at 13:28 held during the whole error window
2. **inventory-service** - config_error (confidence 0.25)
   - Mechanism: Inventory-service connection pool still targets the old primary or a read-only node after the 13:00 DB disruption, and does not re-resolve the endpoint, so write connections keep failing after DB metrics recover at 13:10. This fits the persistence to 13:30 but needs the DB event as the trigger.
   - Supporting evidence: `L0317, M16, M20, M22, H06`
   - Contradicting evidence: `M22`
   - Assumptions: Pool host and reconnect behaviour were not checked, so this is untested; The DB event at about 13:00 is the trigger
3. **inventory-service** - deployment_regression (confidence 0.08)
   - Mechanism: A latent write-path change in deploy v4.1.9 (SKU bulk lookup, 2026-09-03) misroutes reservation UPDATEs to a read-only connection, activating only when DB conditions change at 13:00.
   - Supporting evidence: `C03, L0185`
   - Contradicting evidence: `C03, M22`
   - Assumptions: v4.1.9 touched write routing, which the data does not show; A DB event at 13:00 is the trigger for the latent bug

## Observed facts
- inventory-service error_rate was about 0.15-0.21% from 12:00 to 12:55, then 15.43% in the 13:00 bucket, staying between 14.4% and 15.85% through 13:30. `M22`
- The first inventory-service ERROR was at 13:00:29Z: 'UPDATE stock_reservations failed: cannot execute UPDATE in a read-only transaction (SQLSTATE 25006)'; the same error continued to 13:30:00Z. `L0185, L0317`
- inventory-db logged 'lost connection to primary db-inv-1 (timeout after 10s)' at 12:59:32Z and 13:00:16Z. `L0180, L0183`
- inventory-db connections fell from 93 to 20 at 13:00-13:05 and recovered to 86 by 13:10; replication lag rose to about 48s and returned to 0.29s by 13:10. `M16, M20`
- inventory-db health at 13:28Z is 'degraded': primary endpoint resolves to db-inv-2 (standby, read-only); inventory-service health is 'healthy' but checks process liveness only, not database writes. `H06, H07`
- Deploy v4.1.9 of inventory-service completed 2026-09-03T09:00Z and checkout-service v2.13.4 on 2026-09-05T17:00Z; no change record for inventory-db or the services falls between 2026-09-05T17:00Z and 13:30Z on 09-06. A node pool upgrade completed at 04:00Z. `C03, C07, C08`
- inventory-service CPU, memory, p99 latency and request rate show no step change at 13:00; inventory-db CPU, disk and query latency stay in normal ranges. `M21, M23, M24, M25, M17, M18, M19`
- Checkout-service error_rate rose from about 0.3% to 6.87% in the 13:00 bucket, but its logs in 12:55-13:30 contain no inventory reservation failure errors; its only related line is a 12:26Z slow-reservation WARN. `M12, L0083, L0151`
- Heap usage warnings (91% of 1Gi) and cache miss storm warnings occur at times both before and after 13:00. `L0034, L0092, L0112, L0212, L0220`

## Assumptions
- The primary endpoint repoint or failover is the origin of the read-only condition, though its timing and cause are not recorded in any change or log entry.
- Connection and lag recovery at 13:10 did not repair the endpoint, so the errors persisted to 13:30 because the endpoint still resolved to a standby.
- The node role of db-inv-2 held through the whole error window; the 13:28 health detail is taken as representative.
- Inventory-service health checks do not exercise database writes, so their green status does not indicate reservation health.
- The sampled error counts (40 ERROR lines) are representative of the full error population.

## Inferred conclusions
- The reservation failures are most likely caused by inventory-service writes reaching a read-only database node after a disruption to inventory-db's primary connection at about 12:59-13:00 (H1). The inference is not conclusive because the cause of the endpoint repoint is unlogged and the persistence after 13:10 is unexplained. (confidence 0.60) `L0180, L0183, L0185, M16, M20, H06`
- A stale inventory-service connection pool still bound to the old primary or a read-only node (H2) is a viable alternative that explains the persistence after 13:10; pool target and reconnect state were not checked, so it cannot be excluded. (confidence 0.25) `M22, M20, M16, L0317`
- The v4.1.9 deploy (H3) is unlikely to be the cause: it is three days before onset with no timing match, and the data does not show it changed write routing. (confidence 0.08) `C03, M22`
- Checkout-service impact is probably indirect via sync calls to inventory-service, but no log or metric links checkout errors to inventory failures in time. (confidence 0.30) `D05, M12, L0151`
- Heap pressure and cache miss storms are background noise and not the trigger, since they do not align with the 13:00 step. (confidence 0.60) `L0034, L0220, M24`

## Remediation
- **immediate** - Verify which node is the current writable primary and repoint inventory-service's primary endpoint or connection pool to the writable node (db-inv-1 or its promoted successor), after confirming the role. _(The 13:28 health check shows the primary endpoint on a read-only standby, and the SQLSTATE 25006 errors persist to 13:30.)_
- **immediate** - Restart or reset inventory-service connection pools so that they re-resolve the database endpoint, and confirm whether new connections still fail with SQLSTATE 25006. _(This tests the stale-pool alternative (H2) and is a low-risk mitigation if H1 is wrong.)_
- **immediate** - Watch the reservation error rate and checkout error rate; consider temporarily failing reservations safely or queueing them until writes succeed, to avoid oversell. _(Writes are failing at about 15% and the cause is not yet settled, so a safe holding mitigation limits customer impact.)_
- **short_term** - Make the inventory-service health check exercise a database write or a read-write role check, so green health does not mask write failures. _(Health checks stayed green during a 15% write failure, which hid the outage.)_
- **short_term** - Add alerting on the inventory-db primary endpoint role and on replication connection loss, with failover events logged to the change record. _(The endpoint repoint was unlogged, and the replication timeouts at 12:59 and 13:00 gave no alert path.)_
- **long_term** - Make connection pools re-resolve the primary endpoint on read-only errors and handle SQLSTATE 25006 with reconnect and retry. _(Stale pools would keep failing after any future failover, which is the persistence pattern seen here.)_
- **long_term** - Document and test the database failover runbook, including endpoint repoint and rollback steps. _(The failover path was not recorded, so the next event would again lack an audit trail.)_
- **long_term** - Check the v4.1.9 write-routing diff only if the database and pool checks do not explain the failures. _(H3 is weakly supported, so this is a low-priority check.)_

## Open questions
- Which node was primary before and after 12:59, and why did the primary endpoint resolve to db-inv-2? The failover or repoint record is missing.
- Is db-inv-2 still read-only now, and do new inventory-service connections fail with SQLSTATE 25006?
- What host does each inventory-service connection pool target, and were there reconnect or pool-reset events after 13:00?
- Does checkout-service's 6.9% error rise map to inventory reservation calls? Its logs and metrics for the window were not fully checked.
- Were inventory-service WARN/ERROR logs and metrics for the full error population checked, given that only 40 error lines were sampled?

## Data gaps and tool failures (10 shown, 40 reported)
- Logs contain no SKU, region, endpoint or request-pattern fields, so the concentration question could not be answered from these logs.
- Checkout-service has only 2 WARN/ERROR lines and 1 INFO match for 'reserv' in the window. Checkout's own failed-reservation calls are not visible, so the checkout-to-inventory time match cannot be established.
- Checkout-service metrics were not queried, so checkout error rate and onset are unknown.
- The inventory-db metrics do not name the node role (primary or replica), so the failover theory is unconfirmed.
- The error_rate metric is 5-minute resolution, so onset is only known to the minute from the first ERROR log (13:00:29Z).
- Only 40 of the ERROR lines were returned (limit 50, with WARNs included), so the full error count is not confirmed.
- The inventory-db database name was guessed; the metrics returned for it match the expected series, but this was not confirmed against a service registry.
- The log sample was capped at 30 of 50 matching lines, so later errors and timing of the WARN lines were not fully examined.
- No checkout-service log lines were returned for WARN/ERROR in 12:55–13:30, even though its error rate rose to about 7%. Its errors may be logged at INFO or under a different message, so this is unexplained.
- 31 further gap report(s) in 31 group(s) omitted here (mostly about: change, failover, unknown, checkout-service, read-only, logs); the full list is in the run record.
