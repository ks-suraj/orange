# Incident report S03

- **Status:** CONCLUSIVE (confidence 0.60, margin 0.35, 9 verified supporting and 0 contradicting evidence items (0%))
- **System:** baseline · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** agent_finished
- **Root cause:** `notification-worker` - deployment_regression (confidence 0.60)

## Summary
notification-worker is crash-looping with OutOfMemoryError in TemplateCache.put (heap at its 2Gi container limit), so it is not consuming notification-queue and queue lag has grown from about 4s to 947s since 10:00 UTC. The likely origin is the v1.8.0 in-process template cache deployed 2026-08-31, possibly amplified by the batch size increase on 2026-09-02. Heap pressure rose from about 09:00 and the first GC and OOM symptoms appeared around 09:30 to 09:54. Email-provider latency is degraded but is a secondary factor. The 2-day gap between deploy and symptoms is not explained by the data.

## Conclusion decision
- confidence 0.60, margin 0.35, 9 verified supporting and 0 contradicting evidence items (0%)
- Criteria: top `notification-worker / deployment_regression` confidence 0.60, margin 0.35, 9 verified supporting / 0 contradicting items (0% contradicting); 0 evidence-backed material critic objection(s), 0 non-blocking

## Ranked hypotheses
1. **notification-worker** - deployment_regression (confidence 0.60)
   - Mechanism: The v1.8.0 in-process template cache grows without a bound, so the heap fills, GC thrashes, and the container is OOM-killed repeatedly. Each restart stops consumption, so queue lag accumulates.
   - Supporting evidence: `C04, L0095, L0182, L0185, L0282, M29, M30, M32, M31`
   - Contradicting evidence: none
   - Assumptions: Cache growth is not bounded.; No other memory-heavy change occurred on 09-03.
2. **notification-worker** - config_error (confidence 0.25)
   - Mechanism: Increasing the send batch size from 50 to 100 on 09-02 raises per-cycle memory, pushing the already-growing template cache over the 2Gi limit.
   - Supporting evidence: `C07, L0095, L0182`
   - Contradicting evidence: none
   - Assumptions: Heap use scales with batch size.
3. **email-provider** - dependency_failure (confidence 0.12)
   - Mechanism: Slow eu-west provider responses hold messages in flight and grow worker memory, leading to OOM and backlog.
   - Supporting evidence: `H04, L0065, L0112`
   - Contradicting evidence: none
   - Assumptions: In-flight requests are retained in heap while waiting.

## Observed facts
- queue_lag_s for notification-worker was about 3.9 to 4.2s from 09:00 to 09:55, then rose to 140.9s at 10:00 and 946.9s at 10:30. `M30`
- Memory_pct rose from 81% at 09:00 to 99.1% at 09:50, dropped to 54% at 09:55 (consistent with a restart), and was back at 90.3% by 10:30. `M29`
- Restarts counter increased from 0 to 1 at 09:55 and reached 3 by 10:25. `M32`
- request_rate fell from about 30 req/s to about 6 req/s at 09:55 and stayed near 6 req/s through 10:30. `M31`
- Logs show 'GC overhead high: 92% of time spent in GC' warnings starting 09:30:01 and repeating through 09:38. `L0095, L0105, L0115, L0123`
- Eight ERROR lines report java.lang.OutOfMemoryError: Java heap space at TemplateCache.put(TemplateCache.java:57) between 09:54:22 and 10:25:28. `L0182, L0197, L0212, L0226, L0243, L0255, L0269, L0282`
- Container notification-worker-7c9d was OOMKilled (limit 2Gi) at 09:55:02, 10:10:16 and 10:25:14. `L0185, L0235, L0281`
- Deploy v1.8.0 on 2026-08-31 10:00 introduced 'cache rendered email templates in-process'. `C04`
- A config change on 2026-09-02 08:00 raised send batch size from 50 to 100 (author m.chen). `C07`
- email-provider responded slowly (2400ms) and in 697 to 809ms in the 09:08 to 09:35 window; its health check reports degraded with elevated latency in eu-west. `L0030, L0046, L0065, L0112, H04`
- notification-queue and notification-worker /health checks both returned 200 at 10:28, while the worker was actively OOM-killing. `H08, H09`
- Memory and cpu_pct show no change at 10:00 relative to 09:55 beyond the restart pattern; cpu_pct stayed between 21 and 23%. `M26`

## Assumptions
- The worker's memory footprint grows with the in-process template cache and is not bounded by the cache size.
- The batch size change increases per-cycle template and message memory held in the worker.
- The /health endpoint does not exercise the template rendering or heap-heavy path.
- Container memory limit of 2Gi is unchanged during the window.

## Inferred conclusions
- The primary fault is memory exhaustion in notification-worker from the in-process TemplateCache introduced in v1.8.0, causing OOM crash-loops that stop queue consumption and drive the lag. (confidence 0.60) `C04, L0182, L0185, M29, M30, M32`
- The batch size increase to 100 on 2026-09-02 likely raised memory pressure and may explain why the failure appeared now rather than right after the deploy. (confidence 0.30) `C07, M29, L0095`
- Email-provider latency is a contributing slowdown but does not explain the lag growth or the crashes, since the lag only grew after the worker began OOM-restarting. (confidence 0.15) `H04, L0065, M30, M32`

## Remediation
- **immediate** - Roll notification-worker back to the pre-v1.8.0 build (or disable the template cache) and confirm restarts stop and queue lag falls. _(Removes the suspected memory growth path that causes the OOM loop.)_
- **immediate** - Revert the send batch size from 100 to 50 as a temporary measure while memory is watched. _(Reduces per-cycle memory footprint if batch size contributes.)_
- **short_term** - Drain the backlog after recovery and monitor queue_lag_s and email-provider latency. _(Lag is at about 947s and needs to return to the 5m threshold.)_
- **short_term** - Add a bounded size or eviction policy to TemplateCache and load-test with the batch size of 100. _(Fixes the unbounded in-process growth.)_
- **long_term** - Make health checks exercise rendering and heap usage, and alert on GC overhead and restart count. _(The current /health check passed while the worker was OOM-killing.)_

## Open questions
- Why did heap growth begin around 09:00 on 09-03 rather than immediately after the 08-31 deploy?
- Was there a change in template variety or traffic on 09-03 that filled the cache faster?
- Is the 2Gi limit changed since v1.8.0 was deployed?
- Did the email-provider degradation cause retries or larger in-flight batches that added memory?

## Data gaps and tool failures (0 shown, 0 reported)
_None._
