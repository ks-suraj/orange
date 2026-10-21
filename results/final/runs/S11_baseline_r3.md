# Incident report S11

- **Status:** CONCLUSIVE (confidence 0.85, margin 0.60, 8 verified supporting and 0 contradicting evidence items (0%))
- **System:** baseline · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** agent_finished
- **Root cause:** `payments-db` - resource_exhaustion (confidence 0.85)

## Summary
payment-service write failures (error rate about 0.2% to about 28% at 12:00 UTC, about 30% by 12:30) are caused by payments-db running out of disk space: every failing INSERT into payments returns 'could not extend file: No space left on device'. Disk usage crossed about 98% at 11:40 and reached 103.97% at 12:30, and the database logs show WAL archiving failing with WAL files accumulating. The v3.1.4 deploy at 09:55 is the only change to payment-service, but it is a logging-only change and does not explain a full database disk. The database health check (SELECT 1 ok) is shallow and reports healthy despite write failures. Checkout's alert is consistent with payment-service errors propagating via retries, but checkout shows no error-level logs.

## Conclusion decision
- confidence 0.85, margin 0.60, 8 verified supporting and 0 contradicting evidence items (0%)
- Criteria: top `payments-db / resource_exhaustion` confidence 0.85, margin 0.60, 8 verified supporting / 0 contradicting items (0% contradicting); 0 evidence-backed material critic objection(s), 0 non-blocking

## Ranked hypotheses
1. **payments-db** - resource_exhaustion (confidence 0.85)
   - Mechanism: payments-db volume filled to full (disk about 98% from 11:40, 104% at 12:30) and WAL archiving failed, so new INSERTs into payments fail with 'could not extend file: No space left on device'. Payment-service returns errors, and checkout retries calls to it.
   - Supporting evidence: `M39, M33, L0189, L0193, L0195, L0202, L0271, L0192`
   - Contradicting evidence: none
   - Assumptions: The health check does not exercise writes.; Disk growth source is not yet identified.
2. **payment-service** - deployment_regression (confidence 0.25)
   - Mechanism: v3.1.4 (deployed 09:55) changed request logging, which may have increased data written to the database volume or added load, leading to disk exhaustion and write failures.
   - Supporting evidence: `C09, M39`
   - Contradicting evidence: none
   - Assumptions: Detailed request logs are written to the same volume as the database.
3. **payment-provider** - dependency_failure (confidence 0.05)
   - Mechanism: Payment provider slowness or errors causing payment-service failures; the provider's status page reports healthy, and the logged provider timeouts are only 2 WARN lines.
   - Supporting evidence: `L0193`
   - Contradicting evidence: none
   - Assumptions: Provider health page reflects real availability.

## Observed facts
- payment-service error_rate was about 0.15–0.25% from 11:00 to 11:55, then jumped to 28.19% at 12:00:00 and was 30.32% at 12:30:00. `M33`
- payments-db disk_used_pct rose from 87.84% at 11:00 to 98.51% at 11:40, peaked at 103.97% at 12:30 (last value), and was above 98% from 11:40 onward. `M39`
- payment-service logged 35 ERROR lines of 'INSERT INTO payments failed: could not extend file: No space left on device (SQLSTATE 53100)' between 12:00:21 and 12:17:17. `L0193, L0198, L0201, L0271`
- payments-db logged 'could not extend file base/16384/24576: No space left on device' from 11:59:29 onward, and 6 archive-command failures with WAL files accumulating. `L0189, L0195, L0202`
- payments-db connections (about 116–125), cpu (about 34–36%), query p99 latency (about 12 ms) and replication lag (about 0.4 s) stayed flat across 11:00–12:30. `M37, M38, M40, M41`
- payment-service v3.1.4 was deployed at 09:55:00Z; it is described as 'more detailed request logging'. No other change to payment-service or payments-db appears in 00:00–12:30. `C09, C08`
- Health checks at 12:28 report payment-service, payments-db and checkout-service as healthy; payments-db check is 'accepting connections; SELECT 1 ok'. `H11, H12, H03`
- checkout-service has 2 WARN lines in 11:30–12:30 (one retry of an idempotent payment-service call at 12:00:08, one slow inventory reservation) and no ERROR lines in that window. `L0192, L0292`
- payment-service CPU (about 32–34%), memory (about 53–57%) and request rate (about 58–62 req/s) show no step change at 12:00. `M32, M35, M36`

## Assumptions
- The health checks do not exercise database writes, so 'healthy' does not reflect the disk-full state.
- The payments-db disk_used_pct series reflects the volume that holds the payments table and WAL directory.
- The v3.1.4 change only affects payment-service logging and does not write to the database volume.
- Payment-service error rate is driven by failed INSERTs, as the logs show; other error sources are not separately measured.

## Inferred conclusions
- Primary cause: payments-db ran out of disk space (WAL accumulation after archive failures), so payment INSERTs fail; payment-service is the symptomatic service, not the origin. (confidence 0.85) `M39, L0189, L0193, L0195`
- The v3.1.4 deploy is unlikely to be the root cause: it is logging-only, the failures are database-side write errors, and the disk was already at 88–93% before the deploy's effects would be expected to matter; the 12:00 step lines up with the disk crossing its limit, not with the deploy. (confidence 0.30) `C09, M39, M33`
- Checkout errors are a downstream effect of payment-service failures via retries; checkout is not the origin. (confidence 0.60) `L0192, M33`

## Remediation
- **immediate** - Free disk space on payments-db immediately (archive or remove old WAL segments once the archive target is fixed, and clear other large files), then confirm writes succeed. _(Disk at 104% is the direct cause of INSERT failures.)_
- **immediate** - Fix the failing WAL archive command so WAL segments stop accumulating. _(Archive failures are the likely driver of disk growth.)_
- **short_term** - Consider rolling back payment-service to v3.1.3 only if disk recovery does not stop errors; it is not expected to help. _(Keeps the deploy hypothesis tested cheaply without assuming it is the cause.)_
- **short_term** - Add disk-usage and WAL-archive alerts on payments-db with headroom thresholds well below 90%. _(Disk crossed 98% without an alert firing before failures.)_
- **long_term** - Make the database health check exercise a write or check free space, since SELECT 1 reported healthy during failures. _(Shallow health checks hid the write outage.)_

## Open questions
- What filled the payments-db disk between 11:00 and 11:40 (WAL growth, table growth, or a batch job), and what was disk usage before 11:00?
- Why are WAL archive commands failing, and since when?
- Does checkout's error rate also rise, or only its retries and latency?
- Was disk usage growing before the 09:55 deploy, which would rule the deploy out?
- Are refund queries (slow SELECT on refunds, 8 occurrences) contributing to disk or temp-file use?

## Data gaps and tool failures (0 shown, 0 reported)
_None._
