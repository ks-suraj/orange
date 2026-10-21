# Incident report S03

- **Status:** INCONCLUSIVE (contradicting evidence is 44% of the weighed evidence (max 35%))
- **System:** multi_agent · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** max_rounds_reached

## Summary
The incident S03 system determination is INCONCLUSIVE because the contradicting evidence share (44%) exceeds the 35% limit and the leading hypothesis confidence is only 0.50, so no root cause is asserted. The leading candidate is notification-worker memory exhaustion (H1), with OOM errors at TemplateCache.put, repeated OOMKills from 09:55, and throughput falling from about 30 to about 6 req/s at 09:55 while queue lag rose from about 4 s at 09:55 to about 947 s at 10:30. Contradicting evidence includes GC thrash from 09:30 to 09:50 with sustained throughput and normal lag, which the leading hypothesis does not explain. Email-provider latency (H2, confidence 0.25) and an unmeasured inbound rise or queue-side fault (H3, confidence 0.10) remain as alternatives but are weakly supported. Queue-side metrics, TemplateCache size data, and the orchestrator restart reason were unavailable, so the criteria for a conclusive determination were not met.

## Conclusion decision
- contradicting evidence is 44% of the weighed evidence (max 35%)
- Criteria: top `notification-worker / resource_exhaustion` confidence 0.50, margin 0.25, 9 verified supporting / 7 contradicting items (44% contradicting); 1 evidence-backed material critic objection(s), 3 non-blocking
  - objection: ignored_contradiction: During 09:30 to 09:50 the worker logged 92% GC overhead yet sustained about 30 req/s, processed batches normally and sent confirmations, with lag near 4 s. The  [L0095, L0162, L0170, M31, M30]

## Ranked hypotheses
1. **notification-worker** - resource_exhaustion (confidence 0.50)
   - Mechanism: Heap in notification-worker climbed from 81% at 09:00 to 99% at 09:50 with GC overhead warnings from 09:30, and OutOfMemoryError at TemplateCache.put led to OOMKills at 09:55, 10:10 and 10:25. Throughput fell from about 30 to about 6 req/s at 09:55 and stayed flat at that level through the restarts, so consumption stays capped while the queue backlog grows from 10:00.
   - Supporting evidence: `M29, M31, M30, M32, L0095, L0152, L0182, L0185, L0235, L0281, L0197, L0212`
   - Contradicting evidence: `M28, M27, L0162, L0170`
   - Assumptions: request_rate reflects consumption rather than a drop in incoming messages; TemplateCache growth is unbounded, which is inferred and not confirmed by a cache size metric; The sustained 6 req/s cap after 09:55 is caused by the OOM restart loop rather than something else
2. **email-provider** - dependency_failure (confidence 0.25)
   - Mechanism: Elevated latency at the email provider in eu-west slows each send, lengthening per-message hold time and reducing worker throughput, so queue lag grows without a local fault. The timing of this onset is not established.
   - Supporting evidence: `H04, P06, D13, L0065, L0218, L0265`
   - Contradicting evidence: `L0030, L0046, L0112, L0181, M31, M30`
   - Assumptions: Provider latency is the reason the send path is slow, not only a timing coincidence; The eu-west latency start time is unknown and may predate 10:00; Provider latency alone does not explain the abrupt drop at 09:55
3. **notification-queue** - other (confidence 0.10)
   - Mechanism: An unmeasured rise in incoming message rate or a queue-side fault would increase backlog faster than the worker can drain it, producing lag growth from 10:00 without a worker fault.
   - Supporting evidence: `M30`
   - Contradicting evidence: `H08, M31, M15`
   - Assumptions: Queue lag growth reflects backlog that a queue-side issue could create; Checkout request_rate is a reasonable but indirect proxy for publish volume

## Observed facts
- Queue lag was about 4 s through 09:55 and rose to 140.92 s at 10:00 and 946.91 s at 10:30. `M30`
- notification-worker request_rate fell from about 30.95 req/s at 09:50 to 6.16 req/s at 09:55 and stayed between 5.84 and 6.18 req/s through 10:30. `M31`
- memory_pct rose from 81.04% at 09:00 to 99.13% at 09:50, then dropped to 54.02% at 09:55 and rose again to 90.26% by 10:30. `M29`
- GC overhead warnings (92% of time in GC over 60s) recurred from 09:30:01 to 09:54:17. `L0095, L0152, L0164, L0180`
- The container notification-worker-7c9d was OOMKilled (2Gi limit) at 09:55:02, 10:10:16 and 10:25:14, and restarts went from 0 to 3. `L0185, L0235, L0281, M32`
- java.lang.OutOfMemoryError at TemplateCache.put(TemplateCache.java:57) was logged eight times from 09:54:22 to 10:25:28. `L0182, L0197, L0212, L0226, L0243, L0255, L0269, L0282`
- INFO logs show batches of 100 messages processed in 276 ms and 325 ms and order confirmations sent at 09:50:55 and 09:57:10 during the GC warning period. `L0150, L0162, L0170, L0193`
- Email-provider slow responses (1.3 to 2.4 s) appear at intervals across 09:08 to 10:20, not clustered at onset; email-provider health is degraded at 10:28 with elevated eu-west latency on the status page. `L0030, L0065, L0218, L0265, H04`
- notification-worker p99 latency, error rate and CPU stayed flat across the window with no step at 10:00 or 09:55. `M28, M27, M26`
- No change records exist for notification-worker, notification-queue or email-provider in the window; the only changes are a checkout-service deploy on 2026-09-02 and a node pool upgrade at 01:00 on 2026-09-03. `C08, C09`
- checkout-service request_rate stayed between 81.95 and 87.41 req/s from 09:30 to 10:30 with no step near 10:00. `M15`

## Assumptions
- request_rate reflects the worker's processed rate rather than the incoming message rate to the queue.
- TemplateCache growth is unbounded; this is inferred from heap growth and OOMs at TemplateCache.put and is not confirmed by a cache size metric.
- The sustained throughput cap after 09:55 is caused by the OOM restart loop rather than by another factor.
- Health checks for notification-queue and notification-worker are shallow and do not exercise message processing or the send path.
- The eu-west email-provider latency start time is unknown and may predate 10:00.
- (unverified - no valid evidence cited) No notification-queue metrics or logs were available, and no TemplateCache size or entry-count metric was returned.

## Inferred conclusions
- Notification-worker memory exhaustion is the leading candidate for the lag, since the worker's first OOMKill at 09:55 precedes the lag growth and consumption fell at the same time, but this is not a conclusive root cause. (confidence 0.50) `M29, M31, M30, L0185, M32`
- A trigger or send-path change at 09:55 is still possible, because the GC thrash from 09:30 to 09:50 occurred with steady throughput and normal lag. (confidence 0.40) `L0095, L0162, L0170, M31, M30`
- Email-provider latency is probably not the primary cause, since its slow responses are spread evenly and the lag only rose once the worker began OOMing, though it may add per-message time. (confidence 0.25) `L0065, L0181, H04`
- No recent internal change explains the incident, which argues against a bad deploy or config change, although change tracking may be incomplete. (confidence 0.50) `C08, C09`
- Checkout request volume shows no surge near 10:00 UTC, which weakly argues against a producer-driven rise in incoming messages, though the proxy is indirect. (confidence 0.30) `M15`
- The incident is inconclusive: the leading hypothesis confidence is 0.50, the margin over the runner-up is limited, and contradicting evidence is 44%, above the 35% threshold. (confidence 0.90)

## Remediation
- **immediate** - Mitigate the OOM loop by increasing the notification-worker memory limit or scaling out consumers, and monitor queue lag until it drains. _(Restarts cut consumption to about 6 req/s while the backlog grows, so restoring throughput limits further delay regardless of the root cause.)_
- **immediate** - Pause or throttle non-critical notifications if the backlog risks dropping order confirmations, and communicate delay status to affected customers. _(Order confirmation emails are delayed by more than 15 minutes and the backlog is still growing.)_
- **short_term** - Capture a heap dump from notification-worker and retrieve TemplateCache entry count and size metrics to confirm or refute unbounded growth. _(Cache growth is the leading explanation for the OOMs but is not confirmed by data.)_
- **short_term** - Pull the orchestrator restart reason and any memory limit or config change at 09:55 to explain the post-09:55 throughput cap and the trigger. _(The 09:55 timing is unexplained because GC thrash from 09:30 did not cut throughput until then.)_
- **short_term** - Add queue depth, consumer count and incoming publish rate metrics for notification-queue to separate incoming volume from consumption. _(Queue-side metrics are missing, so the inflow versus consumption question cannot be settled.)_
- **long_term** - Fix the unbounded TemplateCache growth, for example by adding a size bound or eviction policy, once confirmed. _(Preventing heap growth addresses the most likely recurring failure if the cache is confirmed as the source.)_
- **long_term** - Add deep health checks and send-latency and heap alerts for notification-worker and the email-provider integration. _(Current /health checks are shallow and did not show the worker's memory or send-path degradation.)_
- **long_term** - Add provider failover and send-timeout handling for email-provider, as identified in past incident P06. _(Provider latency is a recurring contributor and could extend per-message hold time.)_

## Open questions
- What is the notification-queue incoming message rate and depth for 09:00 to 10:30 UTC, and did the publish volume rise near 10:00?
- What is the TemplateCache entry count or size over time, and does a heap dump show the cache as the dominant consumer?
- Why was the worker restarted at 09:55 (orchestrator reason, memory limit or config change), and what changed to cut throughput at that point?
- When did the eu-west email-provider latency actually begin, and does send-latency or error-rate time series from 09:00 to 10:30 UTC show a correlation with the lag?
- What do DEBUG or INFO logs from 09:50 to 10:00 UTC show about batch sizes, message types and send-call durations?
- Do other producers (beyond checkout-service) publish into notification-queue, and did any of them increase volume near 10:00 UTC?

## Data gaps and tool failures (10 shown, 32 reported)
- No metrics exist for a 'notification-queue' service, so consumer count, queue depth and incoming message rate are unavailable. The queue_lag_s series is the only queue-side signal.
- request_rate is the worker's processed rate, not the incoming rate, so the 'consumption dropped vs. incoming rate' comparison cannot be made directly.
- Logs were capped at the 30 WARN/ERROR lines returned; INFO/DEBUG context around 09:50–10:00 was not retrieved.
- No database edge was returned for notification-worker, and no database health or change records were found. The database dependency named in the task could not be verified.
- The change history covers only changes recorded in the feed. Changes that were not logged, such as manual config or external provider changes, would not appear.
- Health checks are shallow (HTTP /health), and the email-provider status page detail is a single snapshot at 10:28, so the latency start time is not established.
- No past-incident search was run for this task, so no comparable precedent was checked.
- No event-rate or traffic telemetry for order producers (checkout-service, D07) near 10:00 UTC. The query for 'order-service' returned unknown, and the only producer found in the graph is checkout-service.
- No datastore dependencies appear in the graph for notification-worker, so datastore health (09:30–10:30) could not be checked.
- 23 further gap report(s) in 23 group(s) omitted here (mostly about: metrics, health, email-provider, query, logs, send-latency); the full list is in the run record.
