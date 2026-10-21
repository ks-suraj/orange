# Incident report S06

- **Status:** CONCLUSIVE (confidence 0.80, margin 0.68, 9 verified supporting and 1 contradicting evidence items (10%))
- **System:** baseline · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** agent_finished
- **Root cause:** `inventory-db` - infrastructure_failure (confidence 0.80)

## Summary
Inventory reservations are failing because inventory-service's writes are hitting a read-only database. At about 12:59 UTC the inventory-db replication link to primary db-inv-1 timed out, and replication lag spiked for roughly 10 minutes. The inventory-db health check now reports that its primary endpoint resolves to db-inv-2, a standby in read-only mode. Every UPDATE to stock_reservations since 13:00 has failed with SQLSTATE 25006, and the error rate has stayed near 15% since then. The probable fault is the database failover and endpoint routing, not inventory-service code or capacity. Inventory-service health checks stay green because they only test process liveness. Checkout errors rise in step because it calls inventory synchronously.

## Conclusion decision
- confidence 0.80, margin 0.68, 9 verified supporting and 1 contradicting evidence items (10%)
- Criteria: top `inventory-db / infrastructure_failure` confidence 0.80, margin 0.68, 9 verified supporting / 1 contradicting items (10% contradicting); 0 evidence-backed material critic objection(s), 0 non-blocking

## Ranked hypotheses
1. **inventory-db** - infrastructure_failure (confidence 0.80)
   - Mechanism: The primary db-inv-1 lost replication at about 12:59Z. A failover or endpoint switch then routed the primary alias to read-only standby db-inv-2, so inventory-service's UPDATE stock_reservations fails with SQLSTATE 25006. Checkout fails because it calls inventory synchronously.
   - Supporting evidence: `L0180, L0183, M20, M16, L0185, L0230, H06, M22, M12`
   - Contradicting evidence: `H07`
   - Assumptions: The health check's 'primary endpoint' reflects the endpoint inventory-service uses for writes.; The failover is not recorded in change history.
2. **inventory-service** - config_error (confidence 0.12)
   - Mechanism: inventory-service caches or pools connections to the old standby, or has a misconfigured write DSN, so writes keep going to the read-only node even after db-inv-1 recovers at 13:10Z.
   - Supporting evidence: `L0230, L0244, H06`
   - Contradicting evidence: `M20, M16`
   - Assumptions: Connection state persists past the database recovery.
3. **inventory-cache** - resource_exhaustion (confidence 0.05)
   - Mechanism: A cache miss storm and high heap in inventory-service cause errors and slow queries, which would fail reservations.
   - Supporting evidence: `M24`
   - Contradicting evidence: `L0185, M21, M25, M23`
   - Assumptions: Heap and cache warnings are sampled, not the full error set.

## Observed facts
- inventory-service error_rate jumped from about 0.18% at 12:55:00Z to 15.43% at 13:00:00Z and was 14.93% at 13:30:00Z. `M22`
- inventory-db logged 'replication: lost connection to primary db-inv-1 (timeout after 10s)' at 12:59:32Z and 13:00:16Z. `L0180, L0183`
- inventory-db replication_lag_s rose to 48.38s at 13:00:00Z and 47.51s at 13:05:00Z, then returned to 0.29s by 13:10:00Z. `M20`
- inventory-db connections dropped to 20 at 13:00 and 13:05, then recovered to 86 by 13:10. `M16`
- inventory-service logged 40 ERRORs 'UPDATE stock_reservations failed: cannot execute UPDATE in a read-only transaction (SQLSTATE 25006)', the first at 13:00:29Z; the latest sampled one is at 13:14:52Z. `L0185, L0250`
- Errors continued after 13:10:00Z, when replication had already recovered, with 27 read-only UPDATE errors in the window from 13:10 to 13:30. `L0230, L0244`
- The inventory-db health check at 13:28:00Z is 'degraded': 'primary endpoint resolves to db-inv-2 (standby, read-only)'. `H06`
- The inventory-service health check is 'healthy' and documented as checking process liveness only, not database writes. `H07`
- checkout-service error_rate rose from 0.27% at 12:55:00Z to 6.87% at 13:00:00Z and was 7.05% at 13:30:00Z; checkout calls inventory-service over sync HTTP. `M12, D05`
- No deploy, config or feature-flag change is recorded for inventory-service or inventory-db in the window. The only recent change is the platform node-pool upgrade at 04:00Z, which completed long before onset. `C08`
- inventory-service CPU stayed about 29-31%, and its request rate stayed about 134-146 req/s, with no step change at 13:00. `M21, M25`

## Assumptions
- The health check's 'primary endpoint' is a DNS or service alias that is now routed to db-inv-2, and it is not a stale read of db-inv-1.
- Inventory-service writes go through that primary alias with no separate read-replica path.
- Inventory-db's database-level health check does not exercise write transactions, so it can look healthy even while writes fail.

## Inferred conclusions
- The primary failure is in inventory-db: a primary-to-standby failover or endpoint switch around 12:59-13:00Z left writes routed to the read-only standby db-inv-2. (confidence 0.80) `L0180, M20, H06, L0185`
- The errors continue after replication recovers because the write endpoint or connection pool still points at the read-only standby, not at the recovered primary db-inv-1. (confidence 0.65) `H06, L0230, M20`
- inventory-service's own code, CPU and capacity are unlikely to be the root cause, since the failures are SQLSTATE read-only errors and its CPU and request rate are flat. (confidence 0.70) `M21, M25, L0185`
- Checkout failures are a downstream effect of inventory reservation errors. (confidence 0.70) `M12, D05, L0185`

## Remediation
- **immediate** - Repoint the inventory write endpoint or DNS alias to the current writable primary, and confirm which node is primary (db-inv-1 or db-inv-2). _(Stops the SQLSTATE 25006 write failures that cause the 15% error rate.)_
- **immediate** - Restart or recycle inventory-service connection pools so they re-resolve the database endpoint, if pooled connections still target the standby. _(Clears stale connections if the endpoint is fixed but writes still fail.)_
- **immediate** - Temporarily reduce checkout's dependence on synchronous reservation, for example by failing over to a degraded-reservation path, while the write path is restored. _(Reduces checkout's roughly 7% error rate during the outage.)_
- **short_term** - Make the inventory-service health check exercise a write, or check for read-only mode, so the P2 alert is not green during write failures. _(The current health check hid this failure.)_
- **short_term** - Add alerting on inventory-db replication loss and primary role changes, and on the health check's 'degraded' status. _(Would have flagged the 12:59 primary loss before the error rate rose.)_
- **long_term** - Review the failover runbook and DNS TTL and pool behaviour so that a failover re-points writers automatically. _(Prevents a repeat of this split between the database primary and the write endpoint.)_

## Open questions
- Why did db-inv-1 lose replication at 12:59:32Z? Was it a network blip, a node issue or a manual action? The change history has no inventory-db entry.
- Was a failover or promotion triggered automatically or by an operator, and when? That event is not in the logs or change history.
- Does the write endpoint or DNS record point to db-inv-2 now, and what is the TTL or connection-pool max age in inventory-service?
- Is db-inv-1 writable now, and has it been demoted or fenced?

## Data gaps and tool failures (0 shown, 0 reported)
_None._
