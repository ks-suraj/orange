# Incident report S11

- **Status:** CONCLUSIVE (confidence 0.70, margin 0.50, 10 verified supporting and 5 contradicting evidence items (33%))
- **System:** multi_agent · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** tool_budget_exhausted
- **Root cause:** `payments-db` - resource_exhaustion (confidence 0.70)

## Summary
Payment-service write failures began at about 12:00Z and are attributed to payments-db running out of disk space, with ENOSPC errors on the INSERT path; the system determination is conclusive at confidence 0.70. payments-db logged WAL archive failures from 11:00Z and its first ENOSPC error at 11:59:29Z, about 52 seconds before the first payment-service error at 12:00:21Z, while payment-service and payments-db CPU, memory, latency, connections and request rate stayed flat. Checkout errors (about 13%) are consistent with downstream propagation through its sync call to payment-service, but its own ERROR logs are absent and clock alignment is unverified. Two unresolved issues limit certainty: disk_used_pct already read above 100% at 11:50 and 11:55 while payment errors were at baseline, so the exact 12:00 trigger is unexplained and the >100% readings are unverified. The v3.1.4 logging deploy at 09:55Z was not ruled out but has weak support.

## Conclusion decision
- confidence 0.70, margin 0.50, 10 verified supporting and 5 contradicting evidence items (33%)
- Criteria: top `payments-db / resource_exhaustion` confidence 0.70, margin 0.50, 10 verified supporting / 5 contradicting items (33% contradicting); 1 evidence-backed material critic objection(s), 5 non-blocking
  - objection: ignored_contradiction: Disk was at 100.88% at 11:50 and 100.77% at 11:55 while payment error rate stayed at 0.15-0.25%, and the first ENOSPC error came only at 11:59:29Z. If a full di [M39, M33, L0189, L0193]

## Ranked hypotheses
1. **payments-db** - resource_exhaustion (confidence 0.70)
   - Mechanism: payments-db data volume filled up: WAL archiving failed repeatedly from 11:00Z so WAL segments accumulated, disk_used_pct climbed from 87.84% to about 100% by 11:50Z, and INSERTs into payments fail with 'could not extend file: No space left on device'. payment-service surfaces this as about 28-32% write errors and checkout sees about 13% through its sync call to payment-service.
   - Supporting evidence: `M39, L0002, L0177, L0189, L0193, L0195, L0324, M33, M12, L0192, M32, M35, M36, M37`
   - Contradicting evidence: `M39, L0181`
   - Assumptions: The payments-db ENOSPC errors are the origin of the payment INSERT failures, not a secondary symptom.; The disk_used_pct values above 100% reflect real conditions or a reporting artifact that does not change the ordering.; The 12:00 step reflects a threshold or allocation event on top of pre-existing disk pressure, which is not directly observed.
2. **payment-service** - deployment_regression (confidence 0.20)
   - Mechanism: Deploy v3.1.4 (more detailed request logging) at 09:55Z may have raised log or write volume on the shared payments-db, accelerating disk consumption so the volume filled and failed at about 12:00Z. The deploy would act as an indirect trigger of the storage failure.
   - Supporting evidence: `C09, M39, L0193`
   - Contradicting evidence: `C09, M39, L0189, L0002`
   - Assumptions: Logging volume from v3.1.4 is large enough to change database disk growth, which was never measured.; The roughly 2 hour lag between deploy and onset is explained by gradual accumulation.; Disk growth before 11:00Z is not available, so the pre-deploy slope cannot be compared.
3. **payments-db** - dependency_failure (confidence 0.20)
   - Mechanism: A WAL archiving failure (archive command failing with WAL files accumulating) is the root driver: pg_wal growth consumes the data volume and produces the ENOSPC errors. This places the origin in the archive pipeline rather than in data size.
   - Supporting evidence: `L0002, L0177, L0195, M41`
   - Contradicting evidence: `M41`
   - Assumptions: The archive command failures are the cause of WAL accumulation rather than a symptom of the disk filling.; Replication lag being normal means the archive failure is not caused by replication.

## Observed facts
- payment-service error_rate was 0.15-0.25% from 11:00 to 11:55Z, then 28.19% in the 12:00 bucket, peaking at 32.03% at 12:25Z. `M33`
- payments-db logged WAL archive failures ('archive command failed for WAL segment; WAL files accumulating') from 11:00:11Z, six times through 11:55:37Z. `L0002, L0177`
- payments-db logged 'could not extend file: No space left on device' at 11:59:29Z, and the error recurs through 12:30:00Z. `L0189, L0331`
- The first payment-service ERROR is 'INSERT INTO payments failed: could not extend file: No space left on device (SQLSTATE 53100)' at 12:00:21Z, and all 35 payment-service ERROR lines in the window share this message. `L0193, L0330`
- payments-db disk_used_pct rose from 87.84% at 11:00Z to 98.51% at 11:40Z, 100.88% at 11:50Z, 98.04% at 12:00Z and 103.97% at 12:30Z. `M39`
- payment-service cpu_pct, memory_pct, latency_p99_ms and request_rate show no step change at 12:00Z, and payments-db connections, cpu_pct, query_latency_p99_ms and replication_lag_s are also flat across the window. `M32, M35, M34, M36, M37, M38, M40, M41`
- checkout-service error_rate was 0.27-0.31% before 12:00Z, then 12.47% at 12:00Z and 12.2-13.6% through 12:30Z, with no ERROR lines in its logs in the window. `M12`
- checkout-service logged a retry WARN 'retrying idempotent call to payment-service (attempt 2)' at 12:00:08Z, 13 seconds before the first payment-service ERROR; no trace or payment error response linking the two was retrieved. `L0192, L0193`
- The only change to payment-service in the 6 hours before 12:30Z was deploy v3.1.4 ('more detailed request logging') at 09:55:00Z, about 2h05m before onset; no config, flag or infra changes were recorded for payments-db, payment-provider or checkout-service. `C09`
- Health checks at 12:28Z reported payment-service, checkout-service, payments-db and payment-provider healthy; these checks are shallow and do not exercise write paths. `H11, H03, H12, H10`

## Assumptions
- The payments-db ENOSPC errors are the origin of the payment INSERT failures, not a secondary symptom.
- The payment-service and checkout-service log and metric timestamps are accurately aligned to UTC.
- The disk_used_pct values above 100% reflect either real conditions or a metric artifact that does not change the ordering of events.
- The 12:00Z step reflects a threshold or allocation event on top of pre-existing disk pressure, which was not directly observed.
- The shallow health checks (HTTP /health, SELECT 1, status page) do not exercise the payment write path.

## Inferred conclusions
- The payment write failures are caused by payments-db storage exhaustion (WAL accumulation after failed archiving filling the data volume, producing ENOSPC on INSERT), not by overload or connection-pool saturation in payment-service. (confidence 0.70) `L0189, L0193, L0002, M39, M32, M37`
- Checkout-service errors are downstream propagation of payment-service failures through the sync_http call, not an independent origin. (confidence 0.50) `D04, M12, L0192`
- The exact 12:00Z trigger is unexplained: disk was above 100% at 11:50Z and 11:55Z while payment errors stayed at baseline, so a threshold, allocation event or different write path remains plausible. (confidence 0.50) `M39, M33`
- The v3.1.4 logging deploy is a weak candidate for accelerating disk growth; it is not ruled out because log volume and the pre-11:00Z disk slope were not measured. (confidence 0.20) `C09, M39`
- The disk_used_pct readings above 100% are unverified; no filesystem-level free-space check was obtained. (confidence 0.40) `M39`
- Payment-service ENOSPC errors began at 12:00:21Z, and the payments-db error at 11:59:29Z precedes them, but clock alignment between services was not verified. (confidence 0.40) `L0189, L0193`

## Remediation
- **immediate** - Free space on the payments-db data volume immediately (clear or archive pg_wal backlog, expand the volume) and confirm with a filesystem-level free-space check. _(ENOSPC on the INSERT path is the only consistent failure signature, and payment errors persist at about 30% through 12:30Z.)_
- **immediate** - Restore WAL archiving by fixing the archive command failures so WAL segments stop accumulating. _(WAL archive failures from 11:00Z precede the disk fill and are the likely driver of pg_wal growth.)_
- **short_term** - Consider rolling back payment-service to v3.1.3 only if the storage fix does not restore writes, and only as a secondary test. _(The deploy is an unlikely cause, but a rollback is low-cost to rule out an indirect contribution from logging volume.)_
- **short_term** - Add deep health checks that exercise an INSERT on the payments write path and alert on disk_used_pct and WAL archive failures. _(Current checks reported healthy during an outage, so they gave no warning.)_
- **short_term** - Verify disk_used_pct measurement and set alerts at 80% and 90% with an autogrow policy for payments-db. _(Readings above 100% indicate a metric defect, and no autogrow or threshold event was logged.)_
- **long_term** - Add monitoring of payment-service and checkout-service ERROR logs and request IDs to correlate checkout retries with payment errors. _(Checkout has no ERROR lines despite about 13% errors, and clock alignment could not be verified.)_
- **long_term** - Establish log-volume and WAL-growth baselines for payments-db to test deploy-related disk pressure in future releases. _(The v3.1.4 deploy effect on disk growth was never measured.)_
- **long_term** - Review the archive pipeline and disk capacity planning for payments-db as a prevention measure. _(Storage exhaustion is a recurring-risk class and the archive pipeline failed silently for over an hour before impact.)_

## Open questions
- Is the payments-db data volume truly full? A filesystem-level free-space check is needed to confirm whether disk_used_pct above 100% is real.
- What triggered the failure at 12:00Z, given disk was above 100% at 11:50Z and 11:55Z while payment errors were at baseline?
- Did the v3.1.4 deploy at 09:55Z change log volume or disk growth? Pre-11:00Z disk history and payment-service log volume are needed.
- Does checkout-service receive a payment error response before its 12:00:08Z retry? Checkout call traces and attempt-1 records for 11:55Z to 12:05Z are needed.
- Are the payment-service ERROR lines the only failures, or are there earlier failures in the 11:00 to 12:00 window not captured in the logs queried?

## Data gaps and tool failures (10 shown, 40 reported)
- Health checks are shallow (HTTP /health, SELECT 1, status page) and do not exercise payment write paths, so healthy results do not rule out write failures. (reported 2x)
- Deployment time for payment-service was not returned by my tools (change history is outside my scope). I cannot state the deploy-to-onset interval.
- I did not query the payments database metrics (disk_used_pct, connections, replication_lag_s), so the disk-full condition is inferred from the log message only.
- Checkout-service has no ERROR lines in the window despite ~13% error rate. Its errors may be logged under another service or at a level I did not query. The 2 retry WARNs are the only error-related checkout signal I have.
- Query results were capped at 50 lines, but the returned count (37) was below the cap, so no payment-service lines were truncated.
- Change history for payments-db, payment-provider and checkout-service was covered only by the unfiltered query; no separate per-service result was retrieved for them.
- No telemetry or error-log data was consulted in this task; the link between C09 and the error onset is untested.
- Tool budget was exhausted after 6 calls, so no further queries were made.
- No error-rate, latency or throughput telemetry for payment-service, checkout-service or any dependency during 11:00–12:30Z; the timing of which signal changed first could not be established.
- 30 further gap report(s) in 30 group(s) omitted here (mostly about: payments-db, returned, payment-service, error, metrics, retrieved); the full list is in the run record.
