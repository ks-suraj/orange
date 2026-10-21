# Incident report S06

- **Status:** CONCLUSIVE (confidence 0.80, margin 0.70, 8 verified supporting and 0 contradicting evidence items (0%))
- **System:** baseline · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** agent_finished
- **Root cause:** `inventory-db` - infrastructure_failure (confidence 0.80)

## Summary
inventory-service reservation failures start at 13:00 UTC because its writes go to inventory-db's primary endpoint, which resolves to a read-only standby (db-inv-2). The original primary db-inv-1 lost replication connectivity at 12:59:32Z, and the standby's promotion is still pending manual approval. The 40 SQLSTATE 25006 errors match this exactly, while inventory-service health checks only test process liveness and do not exercise writes. No deploy or config change appears in the change history, so the trigger for the primary's loss is not established. Recovery needs a human-approved promotion (or repointing the primary endpoint to a writable node) and verification that stock writes succeed.

## Conclusion decision
- confidence 0.80, margin 0.70, 8 verified supporting and 0 contradicting evidence items (0%)
- Criteria: top `inventory-db / infrastructure_failure` confidence 0.80, margin 0.70, 8 verified supporting / 0 contradicting items (0% contradicting); 0 evidence-backed material critic objection(s), 0 non-blocking

## Ranked hypotheses
1. **inventory-db** - infrastructure_failure (confidence 0.80)
   - Mechanism: The primary db-inv-1 became unreachable at 12:59Z. The failover left the inventory-db primary endpoint on standby db-inv-2, which is read-only until promotion is manually approved. inventory-service UPDATEs on stock_reservations therefore fail with SQLSTATE 25006, producing the 15% error rate.
   - Supporting evidence: `L0180, L0183, L0199, H06, L0185, L0250, M22, M20`
   - Contradicting evidence: none
   - Assumptions: The endpoint switch to db-inv-2 was automatic and happened after the primary was lost.; Read-only errors from the standby account for all failing reservations.
2. **inventory-service** - resource_exhaustion (confidence 0.10)
   - Mechanism: High heap usage and a cache-miss storm drove slow or failing stock reservations. This is a plausible secondary failure mode because of a prior cache eviction incident.
   - Supporting evidence: `M24, M21`
   - Contradicting evidence: none
   - Assumptions: The cache-miss log lines are real and not noise.
3. **inventory-db** - dependency_failure (confidence 0.10)
   - Mechanism: Slow queries on stock_levels (WARN lines 603-1076ms, after autovacuum) raised database load and may have made the primary less responsive, contributing to its loss at 12:59.
   - Supporting evidence: `L0107, L0225, L0266, L0296, L0102`
   - Contradicting evidence: none
   - Assumptions: Slow query WARN lines are not an artefact of logging.

## Observed facts
- inventory-service error_rate jumped from about 0.2% (12:55 and earlier) to 15.43% at 13:00:00Z, and stayed between 14.4% and 15.85% through 13:30. `M22`
- inventory-service logs show 40 ERROR lines 'UPDATE stock_reservations failed: cannot execute UPDATE in a read-only transaction (SQLSTATE 25006)', the first at 13:00:29Z. `L0185, L0188, L0250`
- inventory-db replication lag went from 0.3s to 48.38s at 13:00:00Z and returned to 0.29s by 13:10:00Z. `M18, M20`
- inventory-db logged 'replication: lost connection to primary db-inv-1 (timeout after 10s)' at 12:59:32Z and 13:00:16Z. `L0180, L0183`
- inventory-db logged 'standby db-inv-2 still in recovery: promotion pending manual approval' at 13:03:34Z. `L0199`
- The health check for inventory-db reports 'degraded: primary endpoint resolves to db-inv-2 (standby, read-only)' at 13:28:00Z. `H06`
- The inventory-service health check returns 200 and is documented as checking process liveness only, not database writes. `H07`
- inventory-db connections dropped to 20 at 13:00 and 13:05 and were back to 86 by 13:10. `M16`
- checkout-service logs show no WARN or ERROR lines between 12:55 and 13:30 UTC, and its health check returns healthy. `H03`

## Assumptions
- The health check for inventory-service does not exercise database writes, so a green result does not indicate reservation capability.
- The 'primary endpoint' DNS or VIP for inventory-db was switched to db-inv-2 at or after the 12:59 primary loss, or db-inv-2 has been read-only since then.
- The change history is complete for the period; infra-level changes such as failover automation may not be logged there.
- Errors are counted per request, so the 15% error rate corresponds to the share of reservation writes that fail.
- (unverified - no valid evidence cited) No deployments, config changes, feature flags or infra events were recorded for inventory-service or inventory-db in the change history from 06:00 to 13:30 UTC.

## Inferred conclusions
- Primary cause: loss of db-inv-1 (primary) at ~12:59Z, followed by failover that left the primary endpoint on read-only standby db-inv-2 because promotion is awaiting manual approval. This is what stops stock reservation writes. (confidence 0.80) `L0180, L0183, L0199, H06, L0185, M20`
- The cache-miss storm and high heap usage in inventory-service are secondary. Memory has stayed at 88-94% since before 12:00 and the cache has no failures, so they do not explain the 25006 errors. (confidence 0.60) `M24, M22`
- The 13:10 recovery of replication lag and connections did not restore writes, so the fault is the unpromoted standby and not transient replication lag. (confidence 0.70) `M20, M16, H06`

## Remediation
- **immediate** - Approve and execute promotion of db-inv-2 (or restore db-inv-1 as primary), then repoint the inventory-db primary endpoint to a writable node. _(Stops the read-only SQLSTATE 25006 errors that are causing reservation failures.)_
- **immediate** - Verify writes succeed end to end, e.g. a test reservation, rather than relying on the inventory-service liveness health check. _(The current health checks are green while writes fail.)_
- **immediate** - Confirm checkout retries or fallbacks for failed reservations and check for oversell or stale stock during the window. _(Failed reservations may have left orders or stock levels inconsistent.)_
- **short_term** - Find out why db-inv-1 lost replication at 12:59 (network, host, or resource) before failing back. _(Root cause of the primary loss is not established by the data.)_
- **long_term** - Add a write-path health check to inventory-service and an alert on read-only or standby endpoints. _(The health check is shallow, so the failure went unnoticed by health monitoring.)_
- **long_term** - Automate or pre-approve the failover promotion runbook to cut manual wait time. _(Promotion was pending manual approval, which extended the outage.)_

## Open questions
- Why did db-inv-1 stop responding at 12:59:32Z (host crash, network partition, or resource exhaustion)?
- Who or what changed the primary endpoint to db-inv-2, and when?
- Has the promotion of db-inv-2 been requested, and who must approve it?
- Did any reservations fail silently or get lost between 13:00 and the fix, and what is the stock impact?
- Is the cache-miss storm and high heap a separate issue that could resurface once writes recover?

## Data gaps and tool failures (0 shown, 0 reported)
_None._
