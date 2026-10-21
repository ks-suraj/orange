# Incident report S03

- **Status:** CONCLUSIVE (confidence 0.75, margin 0.55, 10 verified supporting and 1 contradicting evidence items (9%))
- **System:** baseline · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** agent_finished
- **Root cause:** `notification-worker` - deployment_regression (confidence 0.75)

## Summary
The notification-worker is in an OOM crash loop: its in-process TemplateCache.put exhausts the 2Gi heap, the container is OOMKilled and restarted repeatedly, and throughput collapsed from about 30 req/s to about 6 req/s at 09:55 UTC while queue lag grew from about 4s to 947s. The likely origin is the v1.8.0 deploy of 2026-08-31, which added an in-process template cache, with the 2026-09-02 batch-size increase as a possible amplifier. Slow email-provider responses (degraded per the status page) are a contributing factor but do not explain the memory exhaustion. The shallow /health check stayed green throughout, so the crash loop was not surfaced by health checks.

## Conclusion decision
- confidence 0.75, margin 0.55, 10 verified supporting and 1 contradicting evidence items (9%)
- Criteria: top `notification-worker / deployment_regression` confidence 0.75, margin 0.55, 10 verified supporting / 1 contradicting items (9% contradicting); 0 evidence-backed material critic objection(s), 0 non-blocking

## Ranked hypotheses
1. **notification-worker** - deployment_regression (confidence 0.75)
   - Mechanism: v1.8.0 caches rendered templates in-process without a bound; heap grows until GC thrashes and the JVM throws OOM in TemplateCache.put, the container is OOMKilled and restarted repeatedly, and consumption collapses so the queue lag grows.
   - Supporting evidence: `C04, L0182, L0185, L0235, L0281, M29, M32, M31, M30, L0095`
   - Contradicting evidence: `H09`
   - Assumptions: Telemetry before 09:00 is unavailable, so the pre-09:00 memory trend is unknown.; The health check is shallow.
2. **email-provider** - dependency_failure (confidence 0.20)
   - Mechanism: Degraded eu-west latency on the email provider slows each send, lengthening processing time and holding heap-resident messages longer, which adds memory pressure and reduces drain rate.
   - Supporting evidence: `H04, L0065, L0112, L0167, L0030`
   - Contradicting evidence: none
   - Assumptions: The status page reflects actual provider latency; no provider metrics were available.
3. **notification-worker** - config_error (confidence 0.15)
   - Mechanism: Send batch size raised 50 to 100 on 09-02 increases per-batch heap usage, pushing the already-leaking cache past the 2Gi limit sooner.
   - Supporting evidence: `C07, L0095`
   - Contradicting evidence: none
   - Assumptions: Heap use scales with batch size.

## Observed facts
- notification-worker queue_lag_s rose from about 4s (09:55) to 140.92s at 10:00 and 946.91s at 10:30. `M30`
- notification-worker request_rate fell from 30.95 req/s (09:50) to 6.16 req/s (09:55) and stayed near 6 req/s through 10:30. `M31`
- notification-worker memory_pct climbed from 81.04% at 09:00 to 99.13% at 09:50, dropped to 54.02% at 09:55, then rose again to 90.26% at 10:30. `M29`
- notification-worker restarts counter went from 0 to 3 between 09:55 and 10:25. `M32`
- Eight java.lang.OutOfMemoryError: Java heap space errors were logged at TemplateCache.put(TemplateCache.java:57) between 09:54:22 and 10:25:28. `L0182, L0197, L0212, L0226, L0243, L0255, L0269, L0282`
- Container notification-worker-7c9d was OOMKilled (limit 2Gi) at 09:55:02, 10:10:16 and 10:25:14. `L0185, L0235, L0281`
- GC overhead warnings (92% of time in GC over 60s) appeared from 09:30:01 onward, before the first OOM error. `L0095, L0105, L0115, L0123`
- email-provider slow-response warnings (809ms, 697ms, then 2400ms) appeared from 09:08:51 onward; email-provider is reported degraded in eu-west. `L0030, L0046, L0065, L0112, L0167, H04`
- Deploy v1.8.0 of notification-worker on 2026-08-31 10:00 introduced 'cache rendered email templates in-process'; a config change raised send batch size 50 -> 100 on 2026-09-02 08:00. `C04, C07`
- The notification-worker health check returned healthy (HTTP /health 200) at 10:28, and notification-queue was healthy too. `H08, H09`

## Assumptions
- Telemetry before 09:00 UTC is unavailable, so the memory trend since the 08-31 deploy cannot be confirmed directly.
- The /health check is shallow and does not reflect OOM restarts or consumer throughput.
- The OOMKilled container name (7c9d) belongs to the notification-worker deployment that processes the queue.
- The email-provider status page reflects the actual degradation; email-provider has no metrics in this system.

## Inferred conclusions
- The primary fault is unbounded in-process template caching in notification-worker v1.8.0, which leaks heap until OOM, causing restart loops, and the consumer stalls, producing the queue lag. (confidence 0.75) `C04, L0182, L0185, M29, M32, M31, M30`
- The email-provider slowdown is a contributing factor that slows per-message processing and raises memory pressure, but it is not the root cause of the OOM. (confidence 0.35) `H04, L0065, L0095`
- The 09-02 batch-size increase (50 to 100) likely raised per-batch heap use and may explain why the leak reached OOM now rather than earlier. (confidence 0.30) `C07, L0095`
- The platform node pool upgrade (09-03 01:00) is not implicated: the failure is confined to one service's heap and restarts, and no node-level signal was checked. (confidence 0.10)

## Remediation
- **immediate** - Roll notification-worker back to v1.7.x (pre-TemplateCache) or disable the in-process template cache, then confirm queue drain. _(Stops the OOM restart loop that collapsed consumer throughput.)_
- **immediate** - Temporarily revert send batch size from 100 to 50 while recovering. _(Reduces per-batch heap pressure if the leak persists before rollback completes.)_
- **short_term** - Watch the email-provider eu-west latency and consider failing over to the secondary provider if it persists. _(Slow sends reduce drain rate once the consumer is stable.)_
- **short_term** - Add a bounded (LRU/size-limited) template cache with a heap-usage test before redeploy. _(Fixes the unbounded growth at TemplateCache.put.)_
- **long_term** - Make the health check exercise consumer progress and restart count, not just HTTP 200. _(The shallow health check stayed green during the crash loop.)_
- **long_term** - Alert on OOMKilled restarts and GC overhead for notification-worker. _(GC warnings started at 09:30, about 25 minutes before the first OOM.)_

## Open questions
- Why did memory climb only after 09:00 when v1.8.0 deployed 2026-08-31? Telemetry before 09:00 is not available.
- Does the batch size change of 09-02 08:00 change the leak rate?
- Is email-provider latency alone enough to explain the drop in throughput, or is the consumer dead for most of the period?
- What is the email-provider status and its eu-west latency history? No metrics were returned for it.

## Data gaps and tool failures (0 shown, 0 reported)
_None._
