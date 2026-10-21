# Incident report S11

- **Status:** CONCLUSIVE (confidence 0.70, margin 0.55, 14 verified supporting and 1 contradicting evidence items (7%))
- **System:** multi_agent · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** max_rounds_reached
- **Root cause:** `payments-db` - resource_exhaustion (confidence 0.70)

## Summary
Payment writes failed from about 12:00 UTC because the payments-db data volume ran out of space, which the investigation treats as the conclusive determination with confidence 0.70. The metric crossed 100% at 11:50Z and the first 'could not extend file: No space left on device' error from payments-db is at 11:59:29Z, before the first payment-service ERROR at 12:00:21Z. All 35 payment-service ERROR lines carry the same SQLSTATE 53100 signature, and payment-service and checkout-service error rates step up in the 12:00 bucket. Connection counts and other database metrics stayed flat, arguing against connection exhaustion. The source of the 11:00-12:00 growth is unidentified, free bytes and table size were never measured, and the disk_used_pct series is non-monotonic, so the confidence should be read as moderate rather than certain.

## Conclusion decision
- confidence 0.70, margin 0.55, 14 verified supporting and 1 contradicting evidence items (7%)
- Criteria: top `payments-db / resource_exhaustion` confidence 0.70, margin 0.55, 14 verified supporting / 1 contradicting items (7% contradicting); 0 evidence-backed material critic objection(s), 4 non-blocking

## Ranked hypotheses
1. **payments-db** - resource_exhaustion (confidence 0.70)
   - Mechanism: The payments-db data volume ran out of space (disk_used_pct at or above 100% from 11:50Z per the metric, with ENOSPC logged by payments-db from 11:59:29Z), so INSERT INTO payments could not extend the table file and failed with SQLSTATE 53100. payment-service surfaced these failures on roughly 28-32% of requests from the 12:00 bucket, and checkout-service saw about 12-13% through retries of the payment call.
   - Supporting evidence: `L0189, L0193, L0330, M39, M33, M12, L0192, L0195, L0142, L0177, M37, M38, M40, M41`
   - Contradicting evidence: `H12`
   - Assumptions: disk_used_pct above 100% reflects a real full volume, though free bytes were not measured; The disk-full error originates on payments-db rather than a payment-service local volume; The SELECT 1 health check does not test free space, so its green result does not contradict the hypothesis
2. **payment-service** - deployment_regression (confidence 0.15)
   - Mechanism: Deploy v3.1.4 at 09:55Z added detailed request logging that may write large volumes to the database host or shared storage, filling the volume used by payments-db. If so, it would be the growth source behind H-A's full volume rather than a separate cause. The onset is about 2h05m later, so the link is weak and untested.
   - Supporting evidence: `C09, P06`
   - Contradicting evidence: `M39, L0189, L0193`
   - Assumptions: v3.1.4 logging writes to the database host or shared storage; The unretrieved diff would show such a write
3. **payments-db** - resource_exhaustion (confidence 0.04)
   - Mechanism: Connection pool saturation on payments-db, as in P07, would cause write timeouts that might be reported as write failures. However the logged error is disk-full and connection counts stayed flat at 116-125, so this is unlikely.
   - Supporting evidence: `P07`
   - Contradicting evidence: `M37, L0193, L0330`
   - Assumptions: Pool exhaustion would produce a connection-wait error, not a storage error

## Observed facts
- payment-service error_rate was 0.15-0.25% from 11:00 to 11:55Z, then 28.19% in the 12:00 bucket, staying between 27.9% and 32.0% through 12:30Z. `M33`
- payments-db disk_used_pct rose from 87.84% at 11:00Z to 100.88% at 11:50Z and 103.97% at 12:30Z, dipping to 97.82-98.11% between 12:00Z and 12:15Z. `M39`
- The first payments-db ERROR 'could not extend file base/16384/24576: No space left on device' is at 11:59:29Z; 20 such errors occur through 12:30Z. `L0189, L0195, L0331`
- The first payment-service ERROR is at 12:00:21Z, and all 35 payment-service ERROR lines carry 'INSERT INTO payments failed: could not extend file: No space left on device (SQLSTATE 53100)'. `L0193, L0330`
- checkout-service error_rate rose from about 0.3% to 12.47% in the 12:00 bucket and stayed between 12.2% and 13.6% through 12:30Z. `M12`
- checkout-service logged a payment retry warning at 12:00:08Z, before the first payment-service ERROR at 12:00:21Z. `L0192`
- payments-db connections stayed between 116 and 125, with CPU, p99 query latency and replication lag flat across 11:00-12:30Z. `M37, M38, M40, M41`
- WAL archive command failures were logged at 11:44:18Z and 11:55:37Z, noting WAL files accumulating. `L0142, L0177`
- No change events were recorded for any service in 11:00-12:30Z; the nearest change is payment-service v3.1.4 deployed at 09:55Z described as more detailed request logging. `C09`
- Health checks at 12:28Z reported payment-service, checkout-service and payments-db healthy, but these checks are shallow (HTTP /health and SELECT 1) and do not exercise writes. `H11, H03, H12`

## Assumptions
- disk_used_pct above 100% reflects a real full volume, though free bytes and table size were not measured.
- The disk-full error originates on the payments-db data volume rather than a payment-service local volume.
- The SELECT 1 and /health checks do not test free space or writes, so their green results do not contradict the hypothesis.
- The v3.1.4 diff was not retrievable, so whether request logging writes to the database host or shared storage is unknown.
- The change log captures all relevant changes, including batch jobs, although this is not verified.

## Inferred conclusions
- The payments-db data volume ran out of space, and INSERTs into payments failed to extend the table file, causing the payment-service write failures and the checkout-service errors that followed. (confidence 0.70) `M39, L0189, L0193, M33, M12`
- Connection pool exhaustion is unlikely as the cause, since connection counts were flat and the failure signature is storage-related. (confidence 0.70) `M37, L0193`
- The propagation direction from payments-db to payment-service to checkout-service is likely but not fully established, because the checkout retry at 12:00:08Z precedes the first payment ERROR at 12:00:21Z. (confidence 0.50) `L0192, L0193, L0189`
- WAL accumulation after archive failures may have contributed to the space pressure, but this was not separated from table growth or autovacuum activity. (confidence 0.35) `L0142, L0177, L0050`
- The v3.1.4 deployment is an unverified possible source of extra disk growth; the link is weak because the onset is about 2 hours later and no write path is shown. (confidence 0.15) `C09`
- The root cause of the 11:00-12:00 volume growth is unidentified, so the root cause of the space pressure remains open even though the proximate cause is established. (confidence 0.40) `M39, L0050`

## Remediation
- **immediate** - Free space on the payments-db data volume immediately, for example by removing or archiving accumulated WAL segments after confirming the archive target, or by extending the volume. _(ENOSPC errors are ongoing through 12:30Z and every payment write fails while the volume is full.)_
- **immediate** - Clear the WAL archive failure so WAL files stop accumulating, and confirm pg_wal size. _(Archive failures at 11:44Z and 11:55Z suggest WAL accumulation contributed to space pressure.)_
- **short_term** - Confirm the free bytes and total relation size of public.payments and the volume, and identify the writer of the 11:00-12:00 growth. _(Free bytes were never measured and the disk_used_pct series is non-monotonic, so the mitigation effect and root cause remain uncertain.)_
- **short_term** - Add disk free-space alerting on the payments-db volume with a threshold well below 100%. _(The volume filled without a logged warning before the failures began.)_
- **short_term** - Check the v3.1.4 diff to determine whether request logging writes to the database host or shared storage, and roll back if it does. _(The change is the only nearby change and its write behaviour is unverified.)_
- **long_term** - Add deep health checks that exercise a write and check free space on the database volume. _(Current shallow checks reported healthy during an outage.)_
- **long_term** - Set retention or purge policies and monitor WAL and table growth on payments-db. _(Prevents unbounded growth from recurring.)_
- **long_term** - Add retries and backoff handling for the payment call in checkout-service, and review the payment-service error handling of storage failures. _(Checkout retries amplify the impact of database write failures.)_

## Open questions
- What were the free bytes and total relation size of public.payments and the payments-db volume from 10:00 to 12:30Z?
- What process or job wrote the 11:00-12:00 growth (batch job, logging, WAL, or table churn) and on what schedule?
- Does the v3.1.4 diff write to the database host or shared storage?
- Is the disk_used_pct dip at 12:00-12:15Z a real change or a metric artefact, and how is the metric defined above 100%?
- What were the payment-service error logs before 11:55Z that would explain the checkout retry at 11:22:30Z and the 12:00:08Z retry?

## Data gaps and tool failures (10 shown, 40 reported)
- The v3.1.4 diff could not be retrieved; no tool returns diff content. Whether request logging writes to the database host or shared storage is unknown. (reported 2x)
- Telemetry (error rates, latency, per-dependency error breakdown) was not queried, so the 30% error rate and its onset were not verified against the data.
- Health checks are shallow; no write-path or payment-provider API check was run.
- The dependencies of payments-db and payment-provider (second-order dependencies) were not examined.
- No diff or content detail for C09 or C05 was retrieved beyond the description field.
- Past incidents were not searched; no hypotheses were tested against postmortems.
- Changes for api-gateway, auth-service, inventory-service and notification-queue were covered only by the all-service window query, not checked individually.
- No endpoint, instance, pod or version breakdown was available from the tools used, so the question of whether errors concentrate on specific endpoints, instances or versions remains unanswered. Logs carry no such fields in the returned records.
- Payment-service deployment version and time were not checked. The alert says it was deployed earlier today, and the change history was not queried.
- 30 further gap report(s) in 30 group(s) omitted here (mostly about: payments-db, disk_used_pct, queried, payment-service, checked, cannot); the full list is in the run record.
