# Incident report S11

- **Status:** CONCLUSIVE (confidence 0.75, margin 0.55, 8 verified supporting and 3 contradicting evidence items (27%))
- **System:** multi_agent · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** max_rounds_reached
- **Root cause:** `payments-db` - resource_exhaustion (confidence 0.75)

## Summary
Payment write failures on payment-service (error rate about 28-32% from 12:00 UTC) and the downstream checkout-service retries (about 12-13%) are attributed by the system's conclusive determination to exhaustion of the payments-db data volume, with ENOSPC 'could not extend file' errors from 11:59:29Z and disk_used_pct near or above 100% from 11:50Z. Connections, CPU, latency and replication lag stayed flat, which argues against load or connection-pool causes. The leading hypothesis has confidence 0.75 with a margin of 0.55 over the runner-up, and 27% of evidence is contradicting. The v3.1.4 deploy at 09:55Z (logging-only, described as 'more detailed request logging') remains an unresolved alternative because the diff was not retrieved and it is unknown whether its logs are written to the database volume. The SQLSTATE 53100 code is masked in tool output and was not found in database logs, so the storage cause rests on the ENOSPC message text and disk metric rather than the SQLSTATE. Disk values above 100% are unexplained and may be a metric artifact.

## Conclusion decision
- confidence 0.75, margin 0.55, 8 verified supporting and 3 contradicting evidence items (27%)
- Criteria: top `payments-db / resource_exhaustion` confidence 0.75, margin 0.55, 8 verified supporting / 3 contradicting items (27% contradicting); 1 evidence-backed material critic objection(s), 5 non-blocking
  - objection: alternative_not_ruled_out: H2 is a competing cause that fits the evidence as well on the disk side: if v3.1.4 request/payload logging writes to the payments-db volume, that would explain  [C09, M39, L0189]

## Ranked hypotheses
1. **payments-db** - resource_exhaustion (confidence 0.75)
   - Mechanism: The payments-db data volume ran out of space: disk_used_pct stepped from 87.8% at 11:00Z to about 98.5% at 11:40Z and above 100% by 11:50Z, and ENOSPC errors on base/16384/24576 begin at 11:59:29Z. Payment INSERTs then fail with 'could not extend file' from 12:00:21Z, which payment-service surfaces as a roughly 28-32% error rate, and checkout sees failed payment calls and retries.
   - Supporting evidence: `L0189, L0193, L0195, L0330, L0331, M39, M33, M12, L0192, H12`
   - Contradicting evidence: `M39`
   - Assumptions: The ENOSPC errors originate in payments-db as the log text states; disk_used_pct values above 100% are a metric artifact but still indicate near-full storage; SQLSTATE 53100 is masked in tool output and inferred from message text; Shallow SELECT 1 health check does not exercise storage growth
2. **payment-service** - deployment_regression (confidence 0.20)
   - Mechanism: The v3.1.4 deploy at 09:55Z added verbose request/payload logging that wrote to the payments-db volume, accelerating growth until the disk filled near 12:00Z. The deploy would then be the root cause of the storage exhaustion.
   - Supporting evidence: `C09, M39, L0193`
   - Contradicting evidence: `L0189, M39`
   - Assumptions: v3.1.4 contents beyond the logging description were not verified; Payment logs are written to the database volume, which is not confirmed; Disk growth began after 09:55Z, which sub-hourly data cannot confirm
3. **payments-db** - dependency_failure (confidence 0.05)
   - Mechanism: A connection-pool or connection-leak problem on payments-db, as in past incident P07, causes write failures that the SELECT 1 health check does not catch, with the disk-full text being a misattribution.
   - Supporting evidence: `P07, H12`
   - Contradicting evidence: `M37, M38, L0193, L0189`
   - Assumptions: The explicit disk-full errors are misattributed; No connection-pool metrics were retrieved

## Observed facts
- payments-db disk_used_pct rose from 87.84% at 11:00Z to 98.51% at 11:40Z and 100.88% at 11:50Z, with step-like increases and a series maximum of 103.97% at 12:30Z. `M39`
- The first payments-db 'could not extend file base/16384/24576: No space left on device' ERROR is logged at 11:59:29Z, and similar errors recur through 12:30Z. `L0189, L0195, L0331`
- The first payment-service ERROR is at 12:00:21Z ('INSERT INTO payments failed: could not extend file: No space left on device (SQLSTATE 53100)'), and such ERRORs recur through 12:30Z. `L0193, L0330`
- payment-service error_rate was 0.16-0.25% from 11:00 to 11:45, then 28.19% in the 12:00 bucket, peaking at 32.03% at 12:25Z. `M33`
- checkout-service error_rate was about 0.3% until 11:45, then 12.47% in the 12:00 bucket, peaking at 13.57% at 12:05Z; checkout has no ERROR-level lines in the window. `M12, L0192`
- checkout-service logged a retry WARN at 12:00:08Z, about 13 seconds before the first payment-service ERROR, with no failure reason given. `L0192, L0193`
- payments-db connections (116-125), CPU (33.7-36.0%), p99 query latency (11.6-12.4 ms) and replication lag (0.39-0.42 s) stayed flat across 11:00-12:30Z. `M37, M38, M40, M41`
- payment-service v3.1.4 was deployed at 09:55:00Z, described as 'more detailed request logging'; no other payment-service, payments-db or payment-provider changes appear in the window. `C09`
- Health checks at 12:28Z reported payments-db, payment-service and payment-provider healthy, but these checks are shallow (SELECT 1, /health, status page). `H10, H11, H12`
- No SQLSTATE 53100 lines were found in payments-db logs; the database errors are 'No space left on device' messages, and the SQLSTATE in payment-service logs is masked in tool output. `L0189, L0193`

## Assumptions
- The ENOSPC errors originate in payments-db as the log text states.
- disk_used_pct values above 100% indicate near-full storage and are a metric artifact to be verified.
- The SQLSTATE 53100 code is correct as inferred from message text, since it is masked in tool output.
- The shallow SELECT 1 and /health checks do not exercise storage growth or insert paths.
- The v3.1.4 change description is accurate and its contents beyond logging were not verified.

## Inferred conclusions
- The payment write failures are most likely caused by exhaustion of the payments-db data volume, which caused INSERT failures from 11:59Z and surfaced as the payment-service error-rate jump at 12:00Z. (confidence 0.75) `M39, L0189, L0193, M33`
- Checkout-service errors are a downstream effect of payment-service failures, not an independent origin. (confidence 0.60) `L0192, M12, M33`
- Load, connection-pool exhaustion and query-latency causes are unlikely primary triggers in this window, given flat connection, CPU, latency and replication metrics. (confidence 0.55) `M37, M38, M40, M41`
- The v3.1.4 deploy is a plausible but unconfirmed contributor: if its request/payload logging writes to the payments-db volume, it could be the root cause of the storage growth. (confidence 0.20) `C09, M39`
- The storage problem began before the first ERROR, since disk was at 98% or higher from about 11:40Z, so the 11:59-12:00 timing reflects when writes began failing rather than when storage was exhausted. (confidence 0.50) `M39, L0189`
- Whether checkout or payment-service led onset cannot be settled at 5-minute resolution; the 13-second retry lead is too small to establish ordering. (confidence 0.45) `L0192, L0193, M12, M33`

## Remediation
- **immediate** - Free space on the payments-db data volume immediately (extend the volume or remove non-essential data or logs) and verify that INSERTs succeed. _(ENOSPC errors on the payments write path are ongoing and drive the 28-32% payment error rate.)_
- **immediate** - Pause or roll back payment-service v3.1.4 logging if it writes to the database volume, after confirming its destination. _(v3.1.4 is the only change near onset and is unverified as a disk consumer; rollback is low-risk to contain growth.)_
- **immediate** - Identify the growth source for payments-db (free bytes, largest relations, WAL and log directory sizes) for 10:00-12:30Z. _(The source determines whether this is a logging regression or independent data growth, and is not yet known.)_
- **short_term** - Add disk-usage alerting with headroom thresholds on payments-db and verify the disk_used_pct metric definition for values above 100%. _(The disk crossed 98% about 20 minutes before errors and the metric's above-100% readings are unexplained.)_
- **short_term** - Add a write-path health check (test insert or storage check) to payments-db and payment-service monitoring. _(Current SELECT 1 and /health checks reported healthy during an outage in writes.)_
- **short_term** - Review the v3.1.4 diff for log destinations and insert-path changes, and cap log volume written to the database volume. _(Confirms or excludes the deployment regression hypothesis and prevents recurrence from verbose logging.)_
- **long_term** - Implement retention and capacity planning for payments-db storage with automated growth tracking. _(Step-like growth to full capacity shows storage capacity was not being managed proactively.)_
- **long_term** - Add deploy-time checks for disk and log-volume impact in the payment-service release process. _(Prevents a logging change from consuming database storage without review.)_

## Open questions
- Does payment-service v3.1.4 request or payload logging write to the payments-db volume, and what is the v3.1.4 diff?
- What is the source of the 10:00-12:30Z growth on payments-db (largest relations, WAL, bulk writes), and was there a baseline before 11:00Z?
- What is the unmasked SQLSTATE, and does the database server log confirm 53100 on the failing volume?
- Why do disk_used_pct values exceed 100%, and what are the absolute free-space bytes?
- What do sub-minute payment and checkout logs show between 11:59:50 and 12:00:25Z, and did checkout errors precede payment errors?

## Data gaps and tool failures (10 shown, 40 reported)
- checkout-service has no ERROR-level logs in the window, so its own failure signature cannot be seen; only WARN retries are visible.
- The SQLSTATE code is masked as '#' in the tool output, so the exact code is inferred from the text only.
- Metrics are at 5-minute resolution, so sub-bucket ordering between payment and checkout onset cannot be resolved.
- No disk or storage metrics were queried for the database behind payment-service, so the disk-full cause is not directly confirmed by metrics. This was outside the T1 focus list.
- Change history for payments-db and payment-provider was not queried separately. The unfiltered query returned all services and showed no changes for them, but the records are not confirmed as complete.
- Health checks are shallow (/health and SELECT 1) and do not exercise payment writes, so write-path health is unverified.
- No error-rate or telemetry data was queried, so the deploy-to-onset timing rests only on the alert text (~12:00 UTC).
- Feature flag state was not directly queried; no feature_flag records appeared in the change history.
- No error-rate, latency, or connection-pool telemetry for payments-db or payment-provider. The 30% error rate could not be attributed to a specific dependency.
- 31 further gap report(s) in 31 group(s) omitted here (mostly about: payments-db, payment-service, queried, metrics, checked, error); the full list is in the run record.
