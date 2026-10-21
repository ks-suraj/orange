# Incident report S06

- **Status:** CONCLUSIVE (confidence 0.72, margin 0.52, 6 verified supporting and 2 contradicting evidence items (25%))
- **System:** baseline · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** agent_finished
- **Root cause:** `inventory-db` - dependency_failure (confidence 0.72)

## Summary
Stock reservation writes in inventory-service fail because its database primary endpoint resolves to db-inv-2, a standby in read-only mode. At 12:59-13:00 UTC inventory-db lost its replication connection to primary db-inv-1, and the standby was never promoted because it is 'pending manual approval'. Writes have failed with SQLSTATE 25006 since 13:00:29, and error rate has stayed near 15%. inventory-service health checks are green only because they check process liveness and not database writes. No deployment or config change explains this, and the root fault appears to be the primary-loss event plus the blocked promotion. Whether db-inv-1 is actually down or only partitioned is not established by the data.

## Conclusion decision
- confidence 0.72, margin 0.52, 6 verified supporting and 2 contradicting evidence items (25%)
- Criteria: top `inventory-db / dependency_failure` confidence 0.72, margin 0.52, 6 verified supporting / 2 contradicting items (25% contradicting); 0 evidence-backed material critic objection(s), 0 non-blocking

## Ranked hypotheses
1. **inventory-db** - dependency_failure (confidence 0.72)
   - Mechanism: The primary db-inv-1 became unreachable at about 12:59 UTC. Failover was not automatic, and the primary endpoint still resolves to read-only standby db-inv-2. Every reservation UPDATE fails with SQLSTATE 25006, producing about 15% errors at inventory-service and checkout-service.
   - Supporting evidence: `L0180, L0183, M20, M16, H06, L0199, L0185, M22`
   - Contradicting evidence: `M20, M16`
   - Assumptions: db-inv-1 is not accepting writes.; Promotion is the only path to restoring writes.
2. **inventory-db** - config_error (confidence 0.20)
   - Mechanism: The primary endpoint or DNS record was misconfigured to point to the standby during or after the replication event, so writes route to a read-only node even though a writable primary exists.
   - Supporting evidence: `H06, L0185`
   - Contradicting evidence: `L0180, L0183, M20`
   - Assumptions: db-inv-1 is healthy and writable now, given that replication recovered at 13:10.
3. **inventory-service** - other (confidence 0.10)
   - Mechanism: A connection-pool or application issue in inventory-service, such as stale connections to the old primary, keeps writes failing after the database failover. Memory pressure and cache miss storms may be contributing.
   - Supporting evidence: `L0185, M24`
   - Contradicting evidence: `H06, L0199`
   - Assumptions: Memory pressure in inventory-service is related to the failures.

## Observed facts
- inventory-service error_rate jumped from about 0.2% (12:55) to 15.43% at 13:00 and stayed between 14.4% and 15.85% through 13:30. `M22`
- The inventory-service ERROR logs are almost all 'UPDATE stock_reservations failed: cannot execute UPDATE in a read-only transaction (SQLSTATE 25006)', the first at 13:00:29Z and the last returned at 13:21:47Z; 40 such errors in the window. `L0185, L0280`
- inventory-db logged 'replication: lost connection to primary db-inv-1 (timeout after 10s)' at 12:59:32Z and 13:00:16Z. `L0180, L0183`
- The inventory-db dependency health check at 13:28:00Z is 'degraded': the primary endpoint resolves to db-inv-2 (standby, read-only). `H06`
- inventory-db replication lag rose to 48.38s at 13:00 and returned to about 0.29s by 13:10; inventory-db connections fell to 20 at 13:00-13:05 and were back to 86 by 13:10. `M20, M16`
- inventory-db logged 'standby db-inv-2 still in recovery: promotion pending manual approval' repeatedly, last at 13:25:36Z. `L0199, L0233, L0299`
- inventory-service health check is green (HTTP 200) and documented as checking process liveness only, not database writes. `H07`
- inventory-db CPU (about 30%) and query_latency_p99 (about 9 ms) stayed flat across the incident; slow SELECTs of 600-870 ms appeared only from 13:08 onward. `M17, M19, L0225, L0296`
- The only change in the window is a platform Kubernetes node-pool upgrade at 04:00Z; no deploys, config changes or feature flags were recorded for inventory-service, inventory-db or checkout-service. `C08`
- checkout-service's only WARN/ERROR in the window is a card decline from the issuer at 12:48:57Z, and checkout has no reservation-related errors in the log. `L0151`

## Assumptions
- db-inv-1 is unreachable or demoted, so no writable primary exists, based on the replication timeouts and the endpoint pointing to the standby.
- Automatic failover is disabled for inventory-db and promotion needs a human decision.
- The inventory-service error rate is the stock-reservation write failure rate, since the logs show nearly all errors are this write failure.
- The 13:10 return of replication lag to normal does not by itself prove db-inv-1 is healthy; the data does not show why it recovered.

## Inferred conclusions
- The primary root cause is a dependency failure at inventory-db: loss of the primary db-inv-1 with no writable primary, leaving the endpoint on read-only standby db-inv-2. (confidence 0.72) `L0180, L0183, H06, L0199, L0185`
- The incident persists because the promotion of db-inv-2 is pending manual approval and the health checks do not test writes, so the service stays green while reservations fail. (confidence 0.60) `L0199, H07, M22`
- The node-pool upgrade at 04:00Z and the checkout card-decline error are not the cause; there is no timing correlation with the 13:00 onset. (confidence 0.70) `C08, L0151`
- The slow stock_levels queries and cache miss storms are secondary load effects that began after the write failures, not the trigger. (confidence 0.40) `L0225, L0296`

## Remediation
- **immediate** - Get a human decision on promoting db-inv-2 to primary (or restoring db-inv-1 if it is healthy), then repoint the inventory-db primary endpoint to the writable node. _(Writes will keep failing until a writable primary is serving the endpoint.)_
- **immediate** - Confirm db-inv-1 state and check for a network partition or host failure around 12:59 UTC before promoting, to avoid split-brain. _(Promoting while the old primary is still accepting writes could cause divergence.)_
- **immediate** - Temporarily drain or shed checkout stock-reservation traffic, or return a clear retry-later error, until writes recover. _(Reduces customer-facing failures while the database is recovering.)_
- **short_term** - Add a write-path health check to inventory-service (e.g. a canary write or a check that the primary is writable) and alert on it. _(The current green check hid a 15% error rate.)_
- **short_term** - Review why replication lag and connection drops recovered at 13:10 without a failover, and verify replication and endpoint state after recovery. _(Stale endpoint state or a flapping primary could recur.)_
- **long_term** - Define and test automatic or pre-approved failover for inventory-db with fencing of the old primary. _(Manual promotion lengthened the outage to more than 30 minutes.)_

## Open questions
- Is db-inv-1 down, partitioned or demoted, and what caused the 12:59 replication timeout?
- Why did inventory-db connections and replication lag recover at 13:10 while the endpoint still points to the standby?
- Who holds the authority to approve the db-inv-2 promotion, and what is the expected time to approval?
- Does the stock_levels slowness after 13:08 indicate a separate problem or only the aftermath of load shifting?
- Were any stock reservations lost or double-counted during the window?

## Data gaps and tool failures (0 shown, 0 reported)
_None._
