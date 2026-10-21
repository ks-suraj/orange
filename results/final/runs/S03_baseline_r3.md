# Incident report S03

- **Status:** CONCLUSIVE (confidence 0.70, margin 0.50, 10 verified supporting and 2 contradicting evidence items (17%))
- **System:** baseline · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** agent_finished
- **Root cause:** `notification-worker` - deployment_regression (confidence 0.70)

## Summary
notification-worker is repeatedly running out of heap and being OOMKilled, which cut its consumption rate from about 30 req/s to about 6 req/s starting around 09:55 UTC and let queue lag climb from 4 s to about 947 s by 10:30. The most likely origin is the v1.8.0 in-process template cache (deployed 2026-08-31), with the 2026-09-02 batch-size increase as a possible amplifier. The email-provider slowdown is a real but secondary factor, since it does not explain the crash-and-restart pattern. Memory telemetry before 09:00 is missing, so the leak's onset cannot be confirmed directly.

## Conclusion decision
- confidence 0.70, margin 0.50, 10 verified supporting and 2 contradicting evidence items (17%)
- Criteria: top `notification-worker / deployment_regression` confidence 0.70, margin 0.50, 10 verified supporting / 2 contradicting items (17% contradicting); 0 evidence-backed material critic objection(s), 0 non-blocking

## Ranked hypotheses
1. **notification-worker** - deployment_regression (confidence 0.70)
   - Mechanism: v1.8.0 caches rendered templates in-process without a bound. Heap grows until GC thrashes (from 09:30), then TemplateCache.put throws OOM and the 2Gi container is killed. Each restart drops consumption to about 6 req/s, so queue lag grows.
   - Supporting evidence: `C04, M29, L0095, L0182, L0185, L0235, L0281, M31, M30, M32`
   - Contradicting evidence: `M26, H09`
   - Assumptions: Cache is unbounded.; Pre-09:00 memory data is missing, so the timing gap between the 08-31 deploy and the 09:00 ramp is unexplained.
2. **email-provider** - dependency_failure (confidence 0.20)
   - Mechanism: Slow provider responses hold worker threads and in-flight batches, increasing heap use and slowing drain, which leads to backlog growth.
   - Supporting evidence: `L0065, L0112, H04`
   - Contradicting evidence: `M31, L0095, L0182`
   - Assumptions: Slow sends increase per-message memory retention.
3. **notification-worker** - config_error (confidence 0.15)
   - Mechanism: Batch size increase from 50 to 100 on 2026-09-02 raised per-batch heap use and tipped the worker into OOM.
   - Supporting evidence: `C07, L0095`
   - Contradicting evidence: `C04, M29`
   - Assumptions: Memory per batch scales linearly with batch size.

## Observed facts
- queue_lag_s was stable at about 3.9–4.2 s from 09:00 to 09:55, then rose to 140.92 s at 10:00 and reached 946.91 s at 10:30. `M30`
- request_rate fell from about 29–31 req/s (09:50 at 30.95) to 6.16 req/s at 09:55 and stayed near 6 req/s through 10:30. `M31`
- memory_pct climbed from 81.04% at 09:00 to 98.48% at 09:45 and 99.13% at 09:50, then dropped to 54.02% at 09:55; it was back at 90.26% by 10:30. `M29`
- Restarts counter rose from 0 at 09:50 to 1 at 09:55 and to 3 by 10:25. `M32`
- GC overhead warnings ('92% of time spent in GC over last 60s') appear repeatedly from 09:30:01 onward. `L0095, L0105, L0115, L0123`
- java.lang.OutOfMemoryError: Java heap space at TemplateCache.put(TemplateCache.java:57) is logged at 09:54:22 and repeatedly afterward, with 8 occurrences in the window. `L0182, L0197, L0212, L0226, L0243, L0255, L0269, L0282`
- Container notification-worker-7c9d was OOMKilled (limit 2Gi) at 09:55:02, 10:10:16 and 10:25:14. `L0185, L0235, L0281`
- cpu_pct stayed between 21.18% and 22.82% for the whole window, so the worker was not CPU-bound. `M26`
- Deploy v1.8.0 on 2026-08-31 10:00 UTC added in-process caching of rendered email templates; config change on 2026-09-02 08:00 raised the send batch size from 50 to 100. `C04, C07`
- email-provider logged slow responses (2400 ms) at 09:20 and 09:35, and the dependency health check reports 'degraded: elevated latency in eu-west' at 10:28. `L0065, L0112, H04`
- No change events were recorded in the 2026-09-03 window (06:00–10:30); the only changes in the past week are the 08-31 deploy and the 09-02 config change. `C04, C07`
- notification-queue and notification-worker report HTTP /health 200 at 10:28, while the worker was restarting repeatedly. `H08, H09`
- The only past incident with similar symptoms is P06 (2026-06-20), an email-provider outage that caused queue lag and send timeouts. `P06`

## Assumptions
- The TemplateCache growth is unbounded (no eviction or size limit), so memory rises with the number of distinct templates or rendered payloads processed.
- Memory telemetry before 09:00 is unavailable in the tool (the query for 08-31 returned only 09:00+ points), so the onset of growth is not directly confirmed.
- The worker's 2Gi limit and heap sizing have not changed since v1.8.0.
- The notification-worker /health check does not exercise template rendering or heap pressure, so it stays green during OOM loops.
- email-provider has no metrics in the telemetry, so its own error rate and latency are known only from worker logs and one status-page-style health check.

## Inferred conclusions
- The primary fault is memory exhaustion in notification-worker from the unbounded in-process TemplateCache introduced in v1.8.0; the OOM restart loop throttles consumption and produces the queue lag. (confidence 0.72) `M29, M32, L0182, L0185, M31, M30, C04`
- The 2026-09-02 batch size increase (50→100) may have increased per-batch heap pressure and accelerated the OOM cycle, but this is not directly shown by the data. (confidence 0.30) `C07, L0095`
- The email-provider slowdown is a contributing factor that lengthens sends but cannot alone explain repeated worker OOM kills or the 09:55 drop in throughput. (confidence 0.20) `L0065, L0112, H04, M31`

## Remediation
- **immediate** - Roll back notification-worker to the pre-v1.8.0 build (or disable the in-process template cache via flag) to stop the OOM loop. _(Targets the only change that introduces in-process heap growth; restores consumption rate.)_
- **immediate** - Revert the batch size from 100 to 50 while the rollback is in progress. _(Reduces per-batch memory pressure in case it contributes.)_
- **immediate** - Monitor queue_lag_s and drain the backlog once the worker is stable; consider scaling replicas for the backlog. _(Backlog of about 16 minutes must be drained to clear delayed order emails.)_
- **short_term** - Add a size bound and eviction to TemplateCache and add a heap-usage alert on notification-worker. _(Prevents unbounded growth recurring.)_
- **short_term** - Make the health check exercise template rendering or report OOM/restart state. _(Health check stayed green during the crash loop.)_
- **long_term** - Add a canary and memory-regression test for template caching before deploys; add email-provider metrics and a fallback provider. _(Catches leaks pre-release and reduces dependence on one provider (P06 follow-up).)_

## Open questions
- Why did memory growth begin around 09:00 when v1.8.0 deployed 2026-08-31 10:00? Need pre-09:00 memory data to confirm the onset.
- Is the TemplateCache growing per template, per recipient, or per rendered payload?
- Did the 2026-09-02 batch-size change shift the memory growth rate?
- Is the email-provider slowdown causing sends to hold memory longer (in-flight batches)?
- Why did request_rate drop by 80% at 09:55 while CPU stayed flat?

## Data gaps and tool failures (0 shown, 0 reported)
_None._
