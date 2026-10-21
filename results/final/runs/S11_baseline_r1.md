# Incident report S11

- **Status:** CONCLUSIVE (confidence 0.85, margin 0.70, 9 verified supporting and 1 contradicting evidence items (10%))
- **System:** baseline · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** agent_finished
- **Root cause:** `payments-db` - resource_exhaustion (confidence 0.85)

## Summary
payment-service's 30% error rate since about 12:00 UTC comes from INSERT failures ('could not extend file: No space left on device') against payments-db. payments-db disk usage climbed from about 88% at 11:00 to over 100% by 11:50 and was at 103.97% at 12:30. The database logs show the same ENOSPC errors from 11:59:29, and WAL archiving was failing with WAL files accumulating. Checkout errors are downstream: checkout retries payment-service calls. The shallow health checks (SELECT 1 and /health) report healthy, which masks the disk-full condition. The v3.1.4 deploy at 09:55 is a weaker, unconfirmed lead.

## Conclusion decision
- confidence 0.85, margin 0.70, 9 verified supporting and 1 contradicting evidence items (10%)
- Criteria: top `payments-db / resource_exhaustion` confidence 0.85, margin 0.70, 9 verified supporting / 1 contradicting items (10% contradicting); 0 evidence-backed material critic objection(s), 0 non-blocking

## Ranked hypotheses
1. **payments-db** - resource_exhaustion (confidence 0.85)
   - Mechanism: payments-db volume reached 100% disk usage (WAL accumulating after archive failures, plus growth). Postgres cannot extend data files, so payment INSERTs fail with ENOSPC. payment-service returns errors, and checkout's sync calls to it fail.
   - Supporting evidence: `M39, L0189, L0193, M33, L0181, L0192, M37, M38, M40`
   - Contradicting evidence: `H12`
   - Assumptions: The health check does not test writes or disk space.; WAL accumulation shares the data volume.
2. **payment-service** - deployment_regression (confidence 0.15)
   - Mechanism: Deploy v3.1.4 (09:55Z) introduced more detailed logging or write behavior that increased database writes or disk use, filling the payments-db volume.
   - Supporting evidence: `C09`
   - Contradicting evidence: `M39, L0189, M36, M34`
   - Assumptions: The logging change writes to the database volume, which is not shown in the data.
3. **payments-db** - infrastructure_failure (confidence 0.10)
   - Mechanism: Storage or volume issue (e.g., archive target or WAL volume filling, or a platform change after the 03:00Z node upgrade) reduced usable disk space, so ENOSPC errors appear.
   - Supporting evidence: `C08, L0181`
   - Contradicting evidence: `M39`
   - Assumptions: Storage is backed by the cluster node changed in C08. No data links them.

## Observed facts
- payment-service error_rate jumped from about 0.2% (11:55) to 28.19% at 12:00:00Z and stayed between 28% and 32% through 12:30. `M33`
- payment-service logs show 35 ERROR lines, all 'INSERT INTO payments failed: could not extend file: No space left on device (SQLSTATE 53100)', first at 12:00:21Z. `L0193, L0271`
- payments-db disk_used_pct was 87.84% at 11:00, rose to 98.51% at 11:40, reached 100.88% at 11:50, and was 103.97% at 12:30. `M39`
- payments-db logs show 'could not extend file base/16384/24576: No space left on device' errors from 11:59:29Z through 12:28:38Z. `L0189, L0324`
- payments-db logs also show 6 'archive command failed for WAL segment; WAL files accumulating' warnings. `L0181`
- payments-db CPU, connections, query_latency_p99 and replication_lag stayed flat across 11:00–12:30 (CPU about 34–36%, connections 116–125, p99 about 12 ms). `M37, M38, M40, M41`
- payment-service latency_p99, CPU, memory and request_rate stayed in normal ranges through 12:30 (p99 about 437–468 ms, request_rate about 58–62 req/s). `M32, M34, M35, M36`
- The only change in the window is payment-service deploy v3.1.4 at 09:55Z ('more detailed request logging'), about 2 hours before errors began. An infra node-pool upgrade completed at 03:00Z. `C09, C08`
- Health checks report payment-service, payments-db and payment-provider healthy at 12:28Z (HTTP /health 200, SELECT 1 ok, status page operational). `H11, H12, H10`
- checkout-service logged a retry of an idempotent call to payment-service at 12:00:08Z, and one 1293 ms slow inventory reservation at 12:21:50Z. `L0192, L0292`

## Assumptions
- The health checks are shallow: they do not exercise INSERT/write paths or disk space, so 'healthy' does not contradict the disk-full condition.
- The payments-db disk is the same volume that holds WAL and data, so WAL accumulation from failed archiving consumes the same space.
- The telemetry for disk_used_pct is accurate and not sampled at a coarse interval that hides an earlier spike.
- The checkout errors come from payment-service failures being propagated over the sync_http edge, not from a separate checkout fault.
- Data before 11:00Z is not available here, so the start of disk growth (before 11:00 the disk was already at 88%) is not visible.

## Inferred conclusions
- The primary fault is payments-db running out of disk space; payment INSERTs fail with ENOSPC, which produces the ~30% payment-service error rate and the checkout failures that depend on it. (confidence 0.85) `M39, L0189, L0193, M33, L0192`
- WAL archiving failures are a likely contributor to disk growth. Unarchived WAL segments accumulate on the same volume and need to be cleared or archiving restored before space is recovered. (confidence 0.50) `L0181, M39`
- The v3.1.4 deploy is unlikely to be the primary cause. Its logging change does not explain database disk growth, and errors began about 2 hours after the deploy, with errors at the database layer. It remains unverified: nothing in the data shows payment-service writing to the database disk. (confidence 0.20) `C09, M39, L0189`
- The health checks gave false assurance (healthy while writes fail), so monitoring missed the incident until the alert fired. (confidence 0.70) `H12, H11`

## Remediation
- **immediate** - Free disk space on payments-db immediately: clear or archive unarchived WAL segments, and remove temporary or log files if safe. Then verify that the archive_command succeeds again. _(The ENOSPC condition is the direct cause of the 30% error rate and disk usage is over 100%.)_
- **immediate** - Extend the payments-db volume, or temporarily enlarge it, to restore headroom. _(Stops recurrence while the root cause of growth is found.)_
- **immediate** - Confirm payment-service error rate returns to baseline and checkout recovers; watch for retry storms from checkout. _(Verifies the mitigation worked.)_
- **short_term** - Find out why WAL archiving failed (the archive target may be full or unreachable) and fix it. _(WAL accumulation is a likely driver of disk growth and will recur if not fixed.)_
- **short_term** - Add disk-usage and WAL-growth alerts on payments-db, plus a write-path health check that detects ENOSPC. _(The current health checks (SELECT 1) reported healthy during the outage.)_
- **short_term** - Review whether v3.1.4 verbose request logging writes to the database or shared volume. If it does, roll it back or reduce its verbosity. _(Rules out the deploy as a contributing factor; cheap to check.)_
- **long_term** - Set retention and capacity planning for payments-db storage, and automate WAL cleanup. _(Prevents repeat of disk exhaustion.)_

## Open questions
- What is consuming disk on payments-db: WAL, table growth, or temp files? Which of these grew after 11:00Z?
- Why did WAL archiving begin failing, and when?
- Why was disk already at 88% at 11:00Z, and when did growth start?
- Does v3.1.4 change how much data payment-service writes to the database?
- Were any payment writes lost or partially committed at the time of the ENOSPC errors, and is reconciliation needed?
- Has checkout's retry behavior amplified load on payment-service?

## Data gaps and tool failures (0 shown, 0 reported)
_None._
