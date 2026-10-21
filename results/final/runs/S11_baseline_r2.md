# Incident report S11

- **Status:** CONCLUSIVE (confidence 0.88, margin 0.78, 8 verified supporting and 4 contradicting evidence items (33%))
- **System:** baseline · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** agent_finished
- **Root cause:** `payments-db` - resource_exhaustion (confidence 0.88)

## Summary
payment-service's 30% error rate is caused by payments-db running out of disk space: INSERTs into payments fail with 'No space left on device' from about 11:57 to 12:17 UTC onward. Disk usage rose from 87.8% at 11:00 to 100.9% at 11:50 and reached 104% at 12:30, while WAL archiving had been failing since 11:00. checkout-service's errors are downstream retries of payment-service. The payments-db health check (SELECT 1) reports healthy and does not exercise writes, which is why it did not flag the fault. The v3.1.4 deploy at 09:55 is a coincident change with no evidence linking it to the disk growth.

## Conclusion decision
- confidence 0.88, margin 0.78, 8 verified supporting and 4 contradicting evidence items (33%)
- Criteria: top `payments-db / resource_exhaustion` confidence 0.88, margin 0.78, 8 verified supporting / 4 contradicting items (33% contradicting); 0 evidence-backed material critic objection(s), 0 non-blocking

## Ranked hypotheses
1. **payments-db** - resource_exhaustion (confidence 0.88)
   - Mechanism: The payments-db volume filled (87.8% at 11:00 to over 100% by 11:50), so INSERTs into payments fail with SQLSTATE 53100. WAL archiving failed from 11:00, which likely added to the growth. payment-service and checkout-service errors follow.
   - Supporting evidence: `M39, M33, L0189, L0193, L0324, L0002, L0177, L0192`
   - Contradicting evidence: `M37, M38, M40, H12`
   - Assumptions: Disk usage is measured on the data and WAL volume; The shallow health check did not detect the write failure
2. **payment-service** - deployment_regression (confidence 0.10)
   - Mechanism: Deploy v3.1.4 (more detailed request logging) at 09:55 may have raised write volume to payments-db, which would have filled the disk and produced the same errors.
   - Supporting evidence: `C09, M33`
   - Contradicting evidence: `M32, M35, M36, M39`
   - Assumptions: The added logging writes to the database; Disk growth before 11:00 is unobserved
3. **payment-provider** - dependency_failure (confidence 0.03)
   - Mechanism: The external payment provider could be failing charges, which would show as payment errors.
   - Supporting evidence: `L0192`
   - Contradicting evidence: `H10, L0193, L0189`
   - Assumptions: Provider errors would show in payment-service logs

## Observed facts
- payment-service error_rate rose from about 0.2% at 11:55 to 28.19% at 12:00 and reached 30.32% at 12:30. `M33`
- payments-db disk_used_pct was 87.84% at 11:00, 98.51% at 11:40, 100.88% at 11:50, and 103.97% at 12:30. `M39`
- payments-db logged 'could not extend file ... No space left on device' errors from 11:59:29 onward, and payment-service logged 'INSERT INTO payments failed: No space left on device (SQLSTATE 53100)' from 12:00:21 onward. `L0189, L0193, L0324`
- payments-db logged 'archive command failed for WAL segment ... WAL files accumulating' warnings every ~11 minutes from 11:00:11 to 11:55:37. `L0002, L0177`
- payment-service latency_p99_ms stayed in a 436–468 ms band across the window, and payment-service cpu_pct and memory_pct show no step change. `M32, M34, M35`
- payments-db cpu_pct, query_latency_p99_ms, replication_lag_s and connections show no step change across 11:00–12:30. `M37, M38, M40, M41`
- payment-service request_rate stayed between 57.7 and 62.2 req/s throughout the window, with no traffic surge. `M36`
- The only change in the window to payment-service is deploy v3.1.4 ('more detailed request logging') at 09:55:00; an infra node-pool upgrade completed at 03:00. `C09, C08`
- checkout-service logged 'retrying idempotent call to payment-service' at 12:00:08; the only other WARN was a slow inventory reservation at 12:21:50. `L0192, L0292`
- The health checks for payments-db ('SELECT 1 ok'), payment-service (/health 200), payment-provider (status page) and checkout-service (/health 200) all report healthy at 12:28. `H12, H11, H10, H03`
- payments-db logged 8 slow-query warnings on 'SELECT * FROM refunds WHERE created_at > $#', and one 'canceling statement due to user request' ERROR at 11:57:06. `L0181`

## Assumptions
- The payments-db health check only runs SELECT 1 and does not exercise writes or disk allocation, so it cannot detect a full disk.
- payments-db disk_used_pct is measured on the volume holding the payments data files and WAL.
- No disk-cleanup or retention job ran in the window (none appears in the change history).
- The payment-provider is not the origin, since payment errors are write-side SQLSTATE 53100 errors and not provider responses.

## Inferred conclusions
- The 30% payment error rate is caused by payments-db exhausting disk space, which blocks INSERTs into payments; WAL archive failures between 11:00 and 11:55 were likely accumulating WAL and consuming the disk. (confidence 0.90) `M39, M33, L0193, L0002, L0189`
- checkout-service's errors are a downstream effect of payment-service failures (retries and sync HTTP dependency), not an independent fault. (confidence 0.80) `L0192, D04`
- The v3.1.4 deploy at 09:55 is unlikely to be the root cause: payment-service's resource metrics are flat and the errors come from the database volume, not from the service's logging path. (confidence 0.60) `C09, M32, M35, L0193`
- The health checks passed while payments were failing, so the monitoring gap is that the payments-db check is shallow. (confidence 0.80) `H12, M33`

## Remediation
- **immediate** - Free disk on payments-db now: purge or archive old WAL segments once archiving is restored, and remove other large temporary files; confirm disk_used_pct falls below 90%. _(Writes fail while the disk is at or above 100%.)_
- **immediate** - Fix the WAL archive command failure (check archive target, credentials and space) so WAL stops accumulating. _(Archive failures were the leading indicator and will refill the disk.)_
- **immediate** - If disk cannot be freed quickly, extend the payments-db volume or fail over to the replica. _(Restores payment writes at the fastest rate.)_
- **short_term** - Replace the payments-db health check with a write probe and a disk-free threshold check. _(The current SELECT 1 check reported healthy during a P1 outage.)_
- **short_term** - Add alerts for disk_used_pct above 80% and for WAL archive failures. _(The disk climbed from 88% to 100% over 50 minutes with no alert.)_
- **long_term** - Identify what grew the disk between about 10:00 and 11:50 (table bloat, WAL retention, the refunds query) and add retention or vacuum. _(Root growth is not yet explained.)_
- **short_term** - Confirm that v3.1.4 logging volume does not write to payments-db, and roll it back only if it does. _(Rules out the coincident deploy.)_

## Open questions
- What consumed roughly 12% of disk between 10:00 and 11:40 UTC, and is it WAL, table growth or temp files?
- Why did WAL archiving begin failing at 11:00 UTC, and what is the archive target's state?
- Does the refunds slow query contribute to disk growth through temp or sort files?
- Did the v3.1.4 logging change increase writes to the payments database?
- Is there any disk-usage data before 11:00 UTC to show when growth began?

## Data gaps and tool failures (0 shown, 0 reported)
_None._
