# Incident report S03

- **Status:** INCONCLUSIVE (contradicting evidence is 36% of the weighed evidence (max 35%))
- **System:** multi_agent · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** max_rounds_reached

## Summary
Incident S03 is INCONCLUSIVE per the system determination: contradicting evidence was 36% of weighed evidence against a 35% maximum, so no root cause is asserted. The leading candidate (H1, confidence 0.60) is a consumer-side failure in notification-worker: heap exhaustion with GC thrash from 09:30, TemplateCache.put OutOfMemoryErrors from 09:54, and OOMKills at 09:55, 10:10 and 10:25. Queue lag onset falls between 09:55 and 10:00 and grew to 946.91 s by 10:30, coinciding with a drop in worker request_rate from about 30 to about 6 req/s. Producer rate and queue metrics were unavailable, so the lag growth cannot be reconciled with intake and the drop may be a consequence of the crashes. H2 (v1.8.0 in-process template cache as leak source, confidence 0.40) and H3 (email-provider eu-west latency, confidence 0.12) remain unresolved, with H3 not fully ruled out.

## Conclusion decision
- contradicting evidence is 36% of the weighed evidence (max 35%)
- Criteria: top `notification-worker / resource_exhaustion` confidence 0.60, margin 0.20, 7 verified supporting / 4 contradicting items (36% contradicting); 1 evidence-backed material critic objection(s), 6 non-blocking
  - objection: unsupported_claim: The lag growth of about 0.45 s per s is asserted to be consistent with consumption below arrival, but neither arrival nor consumed rate was measured. Intake of  [M30, M31, M05, M15]

## Ranked hypotheses
1. **notification-worker** - resource_exhaustion (confidence 0.60)
   - Mechanism: Heap pressure built from about 09:00 (81% to 99%), with GC thrash from 09:30 and a TemplateCache.put OutOfMemoryError at 09:54:22 followed by OOMKill at 09:55:02. The restart cut consumption from about 30 to about 6 req/s, and the queue lag then grew from about 4 s to 947 s by 10:30 as the restart loop repeated.
   - Supporting evidence: `M29, M31, M32, M30, L0095, L0182, L0185, L0235, L0281, M15, M05`
   - Contradicting evidence: `M26, M27, M28, L0052`
   - Assumptions: The producer rate stayed near its prior level, since order-service and notification-queue have no metrics; The heap climb is a real leak or unbounded growth rather than a transient load effect
2. **notification-worker** - deployment_regression (confidence 0.40)
   - Mechanism: The v1.8.0 in-process template cache, deployed 2026-08-31, grows without bound, possibly keyed per recipient, and drives the heap climb that ends in repeated OOM in TemplateCache.put. The 2026-09-02 batch-size increase from 50 to 100 may accelerate this growth, so the lag would recur until the cache is bounded or the change is rolled back.
   - Supporting evidence: `C04, L0182, L0197, L0282, M29`
   - Contradicting evidence: `L0052`
   - Assumptions: TemplateCache is the dominant allocator, which the stack trace only shows as the failure point; The v1.8.0 cache change is the source of the growth, which is supported by timing only
3. **email-provider** - dependency_failure (confidence 0.12)
   - Mechanism: Elevated eu-west latency at the email provider would slow sends and back up consumption, producing lag. Its warnings began at 09:08 and do not cluster at the 10:00 onset, and the intake drop coincides with the OOM kill, so this is at most a secondary factor.
   - Supporting evidence: `H04, L0065, L0218, L0265, D13`
   - Contradicting evidence: `L0030, L0046, M31, L0185`
   - Assumptions: The status page reflects the path used by notification-worker; Send slowness would reduce consumption rather than only increase per-message time

## Observed facts
- queue_lag_s was about 3.9 to 4.2 s at every sample through 09:55, then 140.92 s at 10:00 and 946.91 s at 10:30. `M30`
- notification-worker request_rate fell from 30.95 req/s at 09:50 to 6.16 req/s at 09:55 and stayed between 5.84 and 6.18 req/s through 10:30. `M31`
- notification-worker memory_pct rose from 81.04% at 09:00 to 99.13% at 09:50, dropped to 54.02% at 09:55, and rose again to 90.26% by 10:30. `M29`
- Ten 'GC overhead high: 92%' warnings were logged between 09:30:01 and 09:54:17. `L0095, L0180`
- Eight java.lang.OutOfMemoryError errors in TemplateCache.put were logged, first at 09:54:22 and last at 10:25:28. `L0182, L0282`
- The notification-worker container was OOMKilled (limit 2Gi) at 09:55:02, 10:10:16 and 10:25:14, and restarts rose from 0 to 3. `L0185, L0235, L0281, M32`
- checkout-service and api-gateway request rates showed no step change between 09:00 and 10:30. `M15, M05`
- notification-worker error_rate, latency_p99_ms and cpu_pct stayed within narrow bands across the whole window. `M26, M27, M28`
- email-provider slow-response warnings were intermittent, first logged at 09:08, and continued to 10:20. `L0030, L0065, L0265`
- notification-worker deployed v1.8.0 (in-process template caching) on 2026-08-31 and a batch-size config change from 50 to 100 on 2026-09-02 at 08:00. `C04, C07`
- email-provider was reported degraded with elevated eu-west latency at 10:28, while the HTTP health checks for notification-worker and notification-queue returned healthy. `H04, H09, H08`

## Assumptions
- The producer rate into notification-queue stayed near its prior level, since order-service and notification-queue have no metrics.
- The heap climb is unbounded growth or a leak rather than a transient load effect.
- TemplateCache is the dominant allocator; the stack trace shows only the failure point.
- The v1.8.0 cache change is the source of growth; this is supported only by timing.
- The HTTP /health checks do not exercise queue consumption or email sends.
- The status page reflects the email-provider path used by notification-worker.

## Inferred conclusions
- The lag is most likely driven by a consumer-side failure in notification-worker: GC thrash, TemplateCache OOMs and OOMKill restart loops stalled consumption while the queue continued to fill. (confidence 0.60) `M29, M32, L0182, L0185, M30`
- The 09:55 drop in request_rate is most likely a consequence of the worker crash and restart rather than a cause of the lag, since M31 measures worker processing rather than queue arrival. (confidence 0.50) `M31, M32`
- Upstream volume growth is unlikely to explain the lag, since checkout-service and api-gateway traffic was flat; this is indirect because no order-arrival metric exists. (confidence 0.55) `M15, M05`
- A v1.8.0 template cache leak is a candidate source of heap growth, but the cache mechanism is unobserved and the 50-to-100 batch-size change is untested. (confidence 0.40) `C04, C07, L0182`
- Email-provider latency is at most a secondary or background contributor, since its warnings began before the lag and do not cluster at the 10:00 onset. (confidence 0.12) `L0030, L0265, H04`

## Remediation
- **immediate** - Mitigate the crash loop by rolling back notification-worker to the pre-v1.8.0 release or disabling the in-process template cache, while watching heap and restart counts. _(The OOM restart loop is the only sustained anomaly that coincides with the lag onset, and rollback is reversible.)_
- **immediate** - Drain or replay the notification-queue backlog once the worker is stable, and confirm order confirmation emails are delivered. _(Lag reached about 947 s and continues to grow while the worker restarts.)_
- **short_term** - Revert the 2026-09-02 batch-size change from 100 to 50 as a low-risk test. _(The batch-size change is an untested accelerant of heap growth and reverting is cheap.)_
- **short_term** - Collect heap used, heap max, GC pause and TemplateCache entry count at fine resolution for 09:00 to 10:30 to confirm monotonic growth. _(This would confirm or refute the leak hypothesis, which is currently inferred from timing.)_
- **short_term** - Obtain order-service or producer rate into notification-queue and per-partition lag for 09:45 to 10:30. _(This is needed to reconcile the lag slope with consumption and to test whether the drop is a cause or effect.)_
- **long_term** - Add a bounded size and eviction policy to the template cache, with a test for per-recipient keying. _(A bounded cache removes the unbounded-growth failure mode if the leak is confirmed.)_
- **long_term** - Extend health checks to exercise queue consumption and send-path latency, and add metrics for notification-queue and email-provider. _(The current HTTP-only checks reported healthy during a consumer failure and the queue has no metrics.)_
- **long_term** - Add alerting on GC overhead and heap percentage before OOM, and on consumer throughput versus queue arrival. _(The heap climb preceded the failure by about 25 minutes and was not alerted on.)_

## Open questions
- Is the lag growth consistent with consumption below arrival once producer rate and consumed rate are measured?
- Is lag uniform across partitions or concentrated in one partition?
- Does heap grow monotonically and is TemplateCache the dominant allocator?
- Does the 2026-09-02 batch-size change from 50 to 100 correlate with a shift in heap growth or per-batch memory?
- Does the email-provider eu-west latency contribute to per-message time, and what are its error rates over 09:30 to 10:30?
- Does notification-queue hold a backlog depth that matches the lag, and what are its consumer offsets?

## Data gaps and tool failures (10 shown, 32 reported)
- notification-queue has no metrics, so producer rate, queue depth and consumer offsets could not be checked directly; the producer-rate comparison relies on indirect evidence.
- No per-partition lag data exists. Uniformity across partitions cannot be determined from the telemetry available, and the 'partition' log search returned nothing.
- The error_rate and latency metrics do not reflect the OOM failures, so they should not be read as evidence that the worker is healthy.
- Metric resolution is 5 minutes, so the exact onset is bounded to the 09:55–10:00 interval.
- Template and user services are not in the dependency graph returned for notification-worker, so their health could not be checked.
- Dependency results show no edges from notification-worker to any template or user service, which may be incomplete rather than absent.
- Feature-flag and config-change history for notification-worker and email-provider was included in the queries but returned no records. The window was not checked for changes to email-provider itself.
- No telemetry on consumer lag, email-provider latency or error rates was retrieved; findings rely only on the status-page note and health checks.
- order-service has no metrics; the upstream producer's order volume could not be checked directly. checkout-service and api-gateway were used as proxies.
- 23 further gap report(s) in 23 group(s) omitted here (mostly about: notification-worker, log, metrics, rate, budget, checked); the full list is in the run record.
