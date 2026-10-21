# Incident report S03

- **Status:** CONCLUSIVE (confidence 0.60, margin 0.50, 11 verified supporting and 1 contradicting evidence items (8%))
- **System:** multi_agent · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** orchestrator_stopped
- **Root cause:** `notification-worker` - resource_exhaustion (confidence 0.60)

## Summary
The system determination is CONCLUSIVE at confidence 0.60 with a margin of 0.50 over the runner-up, so the leading hypothesis is notification-worker resource exhaustion. Memory in notification-worker rose from 81% at 09:00 to 99% at 09:50 with GC overhead warnings from 09:30, followed by heap OOMs from 09:54 and OOMKilled restarts at 09:55, 10:10 and 10:25. Request intake fell from about 30 to about 6 req/s at 09:55 and queue lag grew from about 4 s to 947 s by 10:30. The TemplateCache is the failing allocation site, but the retained-heap owner is not confirmed because no heap dump or cache metric exists. The trigger of the memory growth before 09:30 is unknown, and checkout request rate stayed flat, which argues against an upstream volume drop but does not rule one out since order-service is unobserved. Email-provider latency was intermittent and predates onset, so it is judged a minor contributor at most.

## Conclusion decision
- confidence 0.60, margin 0.50, 11 verified supporting and 1 contradicting evidence items (8%)
- Criteria: top `notification-worker / resource_exhaustion` confidence 0.60, margin 0.50, 11 verified supporting / 1 contradicting items (8% contradicting); 0 evidence-backed material critic objection(s), 7 non-blocking

## Ranked hypotheses
1. **notification-worker** - resource_exhaustion (confidence 0.60)
   - Mechanism: Memory in notification-worker climbed from 81% at 09:00 to 99% by 09:50 with GC overhead warnings from 09:30, then heap OOMs in TemplateCache.put from 09:54 and OOMKilled restarts at 09:55, 10:10 and 10:25 degraded consumption (intake fell from about 30 to about 6 req/s) and the queue lag grew from 10:00 onward. The retained heap owner is inferred to be the template cache, since the OOM stack trace marks only the failing allocation site.
   - Supporting evidence: `L0095, L0180, L0182, L0185, M29, M31, M30, M32, L0235, L0281, M15, M26`
   - Contradicting evidence: `M31`
   - Assumptions: The TemplateCache is the dominant heap consumer; no heap dump or cache-size metric confirms this; The 09:55 request-rate drop is consumer-side, since checkout-service request_rate stayed flat (M15); Memory growth before 09:00 is a continuation of the same leak
2. **email-provider** - dependency_failure (confidence 0.10)
   - Mechanism: Elevated latency at the external email provider could slow sends and back up the worker, growing the queue lag. However, the observed warnings are small (1-2.4 s), sporadic and not aligned with onset, and provider degradation is only observed at 10:28, after onset.
   - Supporting evidence: `L0112, L0167, L0218, L0265, H04`
   - Contradicting evidence: `L0181, M27, M31`
   - Assumptions: Provider latency at onset was materially larger than the sporadic warnings show; The worker would not have OOMed without slow sends
3. **notification-queue** - infrastructure_failure (confidence 0.08)
   - Mechanism: An unobserved fault in the queue (no metrics available) could reduce delivery to the worker, lowering its request rate at 09:55 and growing lag. Queue health checks are healthy and the worker's OOM sequence precedes the drop, so this is weak.
   - Supporting evidence: `M31, H08`
   - Contradicting evidence: `L0182, L0185, M29`
   - Assumptions: Shallow /health probes do not reflect delivery health; Upstream order volume is unchanged

## Observed facts
- notification-worker memory_pct rose from 81.04% at 09:00 to 99.13% at 09:50, dropped to 54.02% at 09:55 and climbed to 90.26% by 10:30. `M29`
- Repeated GC overhead warnings (92% of time in GC over 60s) begin at 09:30:01 and recur through 09:54:17. `L0095, L0180`
- The first heap OutOfMemoryError at TemplateCache.put is logged at 09:54:22, with eight OOM errors in total through 10:25:28. `L0182, L0282`
- Container notification-worker-7c9d was OOMKilled (2Gi limit) at 09:55:02, 10:10:16 and 10:25:14, and the restarts metric rose from 0 to 3. `L0185, L0235, L0281, M32`
- notification-worker request_rate fell from 30.95 req/s at 09:50 to 6.16 req/s at 09:55 and stayed near 6 req/s through 10:30 without reaching zero. `M31`
- queue_lag_s was about 4 s at 09:55 and 140.92 s at 10:00, rising to 946.91 s at 10:30; it crossed 300 s between 10:05 and 10:10. `M30`
- checkout-service request_rate stayed within about 82 to 88 req/s across 09:00 to 10:30, with no drop at 09:55. `M15`
- Email-provider slow responses (1283 to 2400 ms) were sporadic from 09:08 onward, with no errors or timeouts and no clustering at onset. `L0030, L0112, L0167, L0181, L0218, L0265`
- notification-worker error_rate, latency_p99 and cpu_pct showed no step change at 09:55 or 10:00. `M26, M27, M28`
- No change to notification-worker, notification-queue or email-provider was recorded in the 24 hours before onset; the only changes in the window are a checkout-service deploy on 09-02 and a node pool upgrade on 09-03 01:00. `C08, C09`

## Assumptions
- The TemplateCache is the dominant heap consumer; no heap dump or cache-size metric confirms this.
- The 09:55 request-rate drop is consumer-side and not caused by a reduction in upstream delivery; order-service is unobserved and checkout request rate is only a proxy.
- Memory growth before 09:00 is a continuation of the same leak.
- Shallow /health probes do not reflect queue consumption or email send health.
- Metrics are service-level aggregates at 5-minute resolution and may mix several pods.

## Inferred conclusions
- The root cause is heap exhaustion in notification-worker with GC thrashing, OOMKills and restart loops, which degraded consumption and produced the queue lag. (confidence 0.60) `L0095, L0182, L0185, M29, M31, M30, M32`
- The specific retained-heap owner is most likely the TemplateCache, but this is a hypothesis: the OOM stack site marks the failing allocation, not what retains memory. (confidence 0.40) `L0182, L0197, L0282`
- Email-provider latency is unlikely to be the primary cause, since its slow responses were intermittent and predate the 09:55 change. (confidence 0.85) `L0065, L0112, M27, M30`
- The 09:55 intake drop is most likely consumer-side rather than an upstream volume drop, though this cannot be fully excluded because order-service and the queue have no metrics. (confidence 0.70) `M15, M31`
- No recent change explains the incident; the trigger of the memory growth before 09:30 is unknown. (confidence 0.50) `C08, C09, M29`

## Remediation
- **immediate** - Restart or scale notification-worker pods and temporarily raise the memory limit or reduce concurrency to restore consumption and drain the backlog. _(Consumption is at about 20% of baseline and lag is growing at roughly 130 to 160 s per 5 minutes, with repeated OOMKills.)_
- **immediate** - Capture a heap dump or JVM profile of notification-worker before the next restart to identify what retains memory. _(The TemplateCache attribution is unconfirmed and the heap owner is needed to choose a fix.)_
- **immediate** - Monitor queue depth and produce rate for notification-queue and order-service to confirm the upstream volume is unchanged. _(The queue and order-service are unobserved, so an upstream drop cannot be excluded.)_
- **short_term** - Investigate and bound the template cache size and eviction policy in notification-worker. _(An unbounded cache is the leading suspect for heap growth but is not yet proven.)_
- **short_term** - Identify what changed around 09:30 that caused GC pressure and memory growth in notification-worker, using INFO/DEBUG logs and pre-09:00 metrics. _(The trigger is unknown and no change record explains it.)_
- **long_term** - Add memory, cache-size and queue-depth alerting for notification-worker and notification-queue. _(Memory growth reached 99% before OOM, and current health checks are shallow and did not detect the degradation.)_
- **long_term** - Make health checks exercise queue consumption and email sends rather than relying only on HTTP /health. _(Shallow probes reported healthy during the lag, so they do not detect consumer degradation.)_
- **long_term** - Add a memory-leak regression test and load test for template caching before the next release. _(Prevents recurrence of heap exhaustion from template caching.)_

## Open questions
- Why does lag remain at 4 s until 09:55 when intake fell at 09:50 to 09:55, and is this a measurement or sampling artifact of the 5-minute resolution?
- Which data structure retains the heap, and is the TemplateCache size growing over time?
- What caused memory growth and GC pressure from before 09:00 and around 09:30?
- Did order-service publish volume fall at 09:55, given that it has no metrics and is absent from the dependency graph?
- Does the notification-queue hold a growing backlog, and what is its depth and produce rate?

## Data gaps and tool failures (10 shown, 27 reported)
- Metrics are at 5-minute resolution, so the exact onset minute between 09:55 and 10:00 cannot be resolved more precisely. (reported 3x)
- notification-queue returned no metrics, so queue depth, produce rate and consumer throughput are unavailable. Only proxies from notification-worker are available.
- No log queries were run in this step, so the cause of the restarts and the memory peak is unexplained.
- Only WARN/ERROR logs were queried. INFO/DEBUG logs (for example cache sizing, template fetches, consumer pause or rebalance events) were not checked.
- No logs or metrics were pulled from email-provider, the database or the template service, so their health is inferred from notification-worker's view only.
- No pre-09:30 data was checked, so the start of the GC/memory trend is not confirmed.
- Health checks are shallow HTTP /health checks and do not exercise queue consumption or email sends, so they cannot confirm or rule out the lag cause.
- The email-provider status page is the only signal for its degradation. No telemetry on send latency or error rate was retrieved.
- Change history covers only deploy, config, flag, and infra records; no feature-flag or config changes for notification-worker surfaced, but this was not independently verified beyond the tool output.
- 16 further gap report(s) in 16 group(s) omitted here (mostly about: queried, metrics, checked, logs, growth, notification-worker); the full list is in the run record.
