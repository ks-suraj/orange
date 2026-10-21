# Incident report S06

- **Status:** CONCLUSIVE (confidence 0.60, margin 0.30, 13 verified supporting and 3 contradicting evidence items (19%))
- **System:** multi_agent · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** critic_accepted
- **Root cause:** `inventory-db` - infrastructure_failure (confidence 0.60)

## Summary
Incident S06 is a stock reservation failure affecting inventory-service and checkout-service from about 13:00 UTC. The system determination is conclusive at confidence 0.60, and the leading hypothesis H1 is that inventory-db write traffic is directed at read-only standby db-inv-2 after a replication loss to primary db-inv-1 at 12:59-13:00. All 40 inventory-service ERRORs in the window carry SQLSTATE 25006 (read-only transaction), first at 13:00:29Z and last at 13:30:00Z. Latency, CPU, request rate and DB query latency stayed flat at onset, which argues against load or contention. The DB primary endpoint still resolved to db-inv-2 at 13:28, and the standby logged promotion pending manual approval through 13:25. Confidence is limited because DB-side read-only status, db-inv-1 status and endpoint history were not directly retrieved, change history is empty, and checkout propagation is unverified; H2 (stale service connection pool) remains a live alternative.

## Conclusion decision
- confidence 0.60, margin 0.30, 13 verified supporting and 3 contradicting evidence items (19%)
- Criteria: top `inventory-db / infrastructure_failure` confidence 0.60, margin 0.30, 13 verified supporting / 3 contradicting items (19% contradicting); 0 evidence-backed material critic objection(s), 4 non-blocking

## Ranked hypotheses
1. **inventory-db** - infrastructure_failure (confidence 0.60)
   - Mechanism: Loss of replication connectivity to primary db-inv-1 at 12:59–13:00 (timeouts, lag spike to 48s, connections dropped to 20) left the write path on standby db-inv-2, which is still in recovery and read-only and awaiting manual promotion. Inventory-service UPDATEs on stock_reservations fail with SQLSTATE 25006 from 13:00:29Z, and checkout fails through its sync call, while the liveness-only health check stays green.
   - Supporting evidence: `L0180, L0183, M20, M16, L0185, L0199, L0233, L0265, L0299, H06, H07, M22, M12`
   - Contradicting evidence: `M19, M17, M18`
   - Assumptions: The read-only error reflects the standby being the write target, as H06 indicates; The DB primary failure is the trigger for the endpoint state, though no unlogged failover is ruled out; Errors persisting after 13:10 imply the write path was not restored
2. **inventory-service** - config_error (confidence 0.30)
   - Mechanism: Inventory-service holds a stale endpoint or connection pool still targeting the read-only standby after the 12:59 primary disruption, so writes fail after the DB primary and connections recover around 13:10. This explains persistence to 13:30 without a continuing DB fault.
   - Supporting evidence: `L0185, L0317, M16, M22, L0233`
   - Contradicting evidence: `H06`
   - Assumptions: The connection pool is not refreshed after failover; H06 reflects the endpoint seen by the DB, not necessarily the service's cached target; No pool or connect log lines exist in the window to confirm or refute this
3. **inventory-cache** - resource_exhaustion (confidence 0.05)
   - Mechanism: Cache eviction storms cause latency and reservation failures, as in past incident P03. This is a symptom match only and does not produce SQLSTATE 25006 write rejections.
   - Supporting evidence: `P03, L0112, L0243`
   - Contradicting evidence: `L0185, M23, M21, M25`
   - Assumptions: Cache misses are the cause rather than a secondary effect

## Observed facts
- inventory-service error_rate was about 0.17-0.21% from 12:00 to 12:55, then 15.43% at 13:00, peaking at 15.85% at 13:05 and ending at 14.93% at 13:30. `M22`
- All 40 inventory-service ERROR lines in the window read 'cannot execute UPDATE in a read-only transaction (SQLSTATE 25006)' on stock_reservations, first at 13:00:29Z and last at 13:30:00Z. `L0185, L0317`
- inventory-db logged 'lost connection to primary db-inv-1 (timeout after 10s)' at 12:59:32Z and 13:00:16Z, and replication lag rose to 48.38 s at 13:00 before returning to 0.29 s by 13:10. `L0180, L0183, M20`
- inventory-db connections fell to 20 at 13:00 and 13:05 and recovered to 86 by 13:30 sample range; the 13:10 recovery is reflected in the metric samples. `M16`
- inventory-db logged 'standby db-inv-2 still in recovery: promotion pending manual approval' at 13:03:34Z, 13:10:50Z, 13:18:10Z and 13:25:36Z. `L0199, L0233, L0265, L0299`
- inventory-db health is degraded at 13:28:00Z with primary endpoint resolving to db-inv-2 (standby, read-only), while inventory-service health is green and checks process liveness only. `H06, H07`
- inventory-service latency p99, CPU and request rate stayed flat across 13:00, and inventory-db query latency and CPU stayed flat as well. `M23, M21, M25, M19, M17`
- Checkout-service error_rate rose from 0.27% at 12:55 to 6.87% at 13:00 and stayed near 7% through 13:30, while checkout logs contain no error or warning lines for the window. `M12, L0083, L0151`
- No deployments, config changes, feature-flag flips or infra events were recorded for the affected services or inventory-db in the 12:00-13:30 window. `C03, C08`

## Assumptions
- The read-only error reflects writes reaching standby db-inv-2, as the H06 endpoint state indicates.
- The DB primary failure is the trigger for the endpoint state, and an unlogged failover or endpoint change is not ruled out.
- The primary connection and replication recovery around 13:10 comes from the task statement rather than directly verified telemetry.
- Health checks are liveness-only and do not exercise database writes.
- Checkout failures propagate from inventory reservation calls via its sync HTTP dependency.

## Inferred conclusions
- The root cause is most likely that inventory-db write traffic targets read-only standby db-inv-2 after the 12:59-13:00 replication loss to db-inv-1, with the standby not promoted. (confidence 0.60) `L0180, L0183, M20, H06, L0199, L0185`
- A stale inventory-service connection pool or endpoint still pointing at the standby (H2) remains a plausible alternative explaining persistence after DB recovery. (confidence 0.30) `H06, L0317, M16`
- Load, traffic spikes, CPU saturation and query latency did not cause the onset. (confidence 0.80) `M25, M21, M19, M23`
- Cache-miss storms and slow stock_levels reads are secondary effects, not the trigger. (confidence 0.35) `L0112, L0129, L0225, L0243`
- Checkout-service failures are propagated from inventory reservation failures, but this is unverified because checkout logs do not show the reservation error. (confidence 0.50) `M12, L0185`
- The unlogged endpoint switch was probably made by a DNS, alias or failover process outside the change tracker. (confidence 0.40) `H06`

## Remediation
- **immediate** - Confirm the db-inv-1 primary state and whether a promotion decision is needed, then direct inventory-service writes to the current writable primary. _(Writes are still rejected at 13:30 and the standby is awaiting manual promotion, so the reservation path remains broken.)_
- **immediate** - Apply a manual promotion or failover runbook step under change control, with an approver, to make a writable node available. _(Promotion is pending manual approval per repeated DB logs and is the most direct path to restoring writes.)_
- **immediate** - Restart or refresh inventory-service DB connections and pools after the write endpoint is confirmed, and verify reservations succeed. _(This tests H2 cheaply and clears any stale connection to the standby.)_
- **short_term** - Add a write-path health check to inventory-service that performs a safe transactional write probe. _(The current liveness-only check stayed green during a 15% write failure.)_
- **short_term** - Add alerting on the DB primary endpoint resolving to a read-only node and on replication loss. _(The endpoint state was visible in health data but did not trigger earlier detection.)_
- **short_term** - Add connection and endpoint-resolution logging to inventory-service for reconnects and pool refreshes. _(No pool or connect log lines exist, so H1 and H2 cannot be separated.)_
- **long_term** - Make failover automatic or documented with automatic promotion criteria, and record unlogged infra events in the change tracker. _(Manual promotion extended the outage and the change tracker missed the endpoint switch.)_
- **long_term** - Review checkout-service error logging and timeout or fallback handling for inventory reservation failures. _(Checkout logs did not show the failures, and checkout errors reached about 7%.)_

## Open questions
- Is db-inv-2 read-only with promotion pending at 13:00 and 13:30, and what is the status of db-inv-1 from 12:55 to 13:30?
- When and how did the inventory-db primary endpoint move to db-inv-2, and was there an unlogged failover or DNS change?
- Does inventory-service hold connections or endpoints to db-inv-2 after the primary recovered, separating H1 from H2?
- Do checkout-service logs at INFO or DEBUG level show reservation-call failures, confirming propagation?
- What caused the 12:59 replication timeout, such as network, primary load or lock contention?

## Data gaps and tool failures (10 shown, 30 reported)
- Log lines have no endpoint, SKU, or instance fields, so concentration by those dimensions could not be checked.
- No database metrics were queried (for example a read-only flag, failover, or replication state). The read-only cause sits on the database side and is not yet verified.
- Checkout-service logs returned almost no error lines, so its error messages were not characterised at the message level.
- Metrics are at 5-minute resolution, so the exact onset of the metric change is only known to be between 12:55 and 13:00. The first log error at 13:00:29Z is the more precise timestamp.
- Only 6 tool calls were available, so no change-history or past-incident checks were run.
- Change history returned zero records for every query. This could mean no changes happened, or that the change tracker is missing infra or failover events. An unlogged DB failover would not appear.
- No direct error-rate or database-write telemetry was retrieved, so the link between the read-only standby and the 15% error rate is not confirmed.
- Health checks are shallow (liveness only for inventory-service), so they cannot confirm write health.
- Did not query inventory-service or checkout-service change history separately; only the all-service window was checked.
- 21 further gap report(s) in 21 group(s) omitted here (mostly about: logs, metrics, retrieved, error, returned, info); the full list is in the run record.
