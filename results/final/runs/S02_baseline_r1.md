# Incident report S02

- **Status:** CONCLUSIVE (confidence 0.85, margin 0.77, 8 verified supporting and 2 contradicting evidence items (20%))
- **System:** baseline · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** agent_finished
- **Root cause:** `payment-service` - config_error (confidence 0.85)

## Summary
Checkout's payment step is failing because payment-service's database connection-pool acquire timeout was cut from 5000 ms to 50 ms at 09:58 UTC (OPS-2291, j.alvarez). Starting at 10:00 UTC, payment-service logged pool-acquire timeouts (active=12, idle=0, waiting=31), returned 5xx, and checkout received 503s from it. The database itself looks healthy: connection count, CPU, query latency and replication lag stayed flat through the incident. The 2-minute gap between the change and the first errors is consistent with the change being the trigger, but the link is inferred from timing and log messages, not confirmed by a direct test. Payment-provider and background card declines do not explain the spike.

## Conclusion decision
- confidence 0.85, margin 0.77, 8 verified supporting and 2 contradicting evidence items (20%)
- Criteria: top `payment-service / config_error` confidence 0.85, margin 0.77, 8 verified supporting / 2 contradicting items (20% contradicting); 0 evidence-backed material critic objection(s), 0 non-blocking

## Ranked hypotheses
1. **payment-service** - config_error (confidence 0.85)
   - Mechanism: At 09:58Z the db.pool.connection_timeout_ms setting was cut from 5000 ms to 50 ms. Normal pool waits exceed 50 ms, so payment-service fails to acquire a connection (active=12, idle=0, waiting=31) and returns 503s. Checkout's sync calls to payment-service fail, which drives its 12% error rate.
   - Supporting evidence: `C09, L0193, L0197, L0253, M33, M34, L0194, M12`
   - Contradicting evidence: `L0131, L0164`
   - Assumptions: The 50 ms value is applied at runtime and not only on restart-free paths.; The connection pool was not otherwise degraded.
2. **payments-db** - resource_exhaustion (confidence 0.08)
   - Mechanism: Connection or query saturation on payments-db starves payment-service's pool, as in the 2026-08-08 incident.
   - Supporting evidence: `L0193`
   - Contradicting evidence: `M37, M40, H12, M38`
   - Assumptions: The database-side saturation is not visible in the reported metrics.
3. **payment-provider** - dependency_failure (confidence 0.05)
   - Mechanism: Slow or failing charges at the external provider cause payment-service to hold connections longer, exhausting its pool.
   - Supporting evidence: `L0131, L0164`
   - Contradicting evidence: `H10, M34`
   - Assumptions: The provider status page reflects real provider health.

## Observed facts
- A config change set payment-service db.pool.connection_timeout_ms from 5000 to 50 at 09:58:00Z (ticket OPS-2291, 'reduce tail latency'), the only payment-service change in the window. `C09, C05`
- payment-service error_rate rose from about 0.2% (09:55 bucket 0.25%) to 28.43% in the 10:00 bucket and stayed between 25% and 29% through 10:30. `M33`
- payment-service logged 45 'Timeout acquiring connection from pool payments-db after 50ms (active=12, idle=0, waiting=31)' errors between 10:00:17Z and 10:10:58Z, the first at 10:00:17Z. `L0193, L0197, L0253`
- checkout-service logged 25 'payment-service call failed: 503 Service Unavailable' warnings starting at 10:00:19Z, and its error_rate rose from about 0.28% to 12.45% at 10:00. `L0194, M12`
- payment-service p99 latency fell from about 450 ms (09:55 bucket 433 ms) to about 137 ms at 10:00, consistent with requests failing fast on the 50 ms timeout. `M34`
- payments-db connections stayed in 116-125 and query_latency_p99 stayed about 11.5-12.5 ms across 09:00-10:30; replication lag was about 0.4 s. `M37, M40, M41`
- payments-db health check reports healthy (accepting connections, SELECT 1 ok) at 10:28Z; payment-service health check (/health 200) also reports healthy. `H12, H11`
- payment-provider status page reports all systems operational, and only 2 slow-response warnings appear in payment-service logs. `H10`
- Only 3 'insufficient funds (declined)' errors appear in payment-service logs, the first at 09:40:56Z, before the incident onset. `L0131, L0164, L0207`
- Other recent changes (inventory v4.1.9 on 08-30, search v5.3.1 on 08-31, payment v3.1.3 on 09-01 04:00, checkout v2.13.4 on 09-01 14:00, node pool upgrade on 09-02 01:00) all predate the 09:58 change by many hours. `C03, C04, C05, C07, C08`
- Past incident P06 (2026-08-08) had payment timeouts from payments-db connection exhaustion caused by a batch-job connection leak, a different mechanism. `P06`

## Assumptions
- The payment-service pool of 12 connections and its acquire timeout are the values in the config change and logs; the pool's connection-hold time was not observed directly.
- Health checks are shallow (they do not exercise the payment-service to payments-db pool path or a real charge), so 'healthy' does not rule out this failure.
- Telemetry at 5-minute resolution means the exact onset is at most a few minutes after 09:58.

## Inferred conclusions
- The 09:58 config change lowering db.pool.connection_timeout_ms to 50 ms is the most likely trigger: it makes normal pool waits (about 12 busy connections under about 60 rps) exceed the timeout, so requests fail with 503s that propagate to checkout. (confidence 0.85) `C09, L0193, M33, L0194, M34`
- Pool exhaustion on payments-db itself (the 2026-08-08 pattern) is unlikely, because database connection count, CPU, latency and health were all flat during the incident. (confidence 0.80) `M37, M38, M40, H12`
- The payment provider is unlikely to be the cause: its status is healthy and the only provider-side signals are two slow responses. (confidence 0.70) `H10`

## Remediation
- **immediate** - Revert db.pool.connection_timeout_ms to 5000 on payment-service now (or roll back OPS-2291) and confirm that pool timeouts stop and checkout error_rate returns to about 0.3%. _(The change is the only recent change aligned with onset, and the errors began within about 2 minutes of it.)_
- **immediate** - Watch payment-service 5xx, pool-timeout logs and checkout error_rate for 10-15 minutes after the rollback. _(Confirms recovery and rules out a residual cause.)_
- **short_term** - Require change review for pool and timeout settings; add a validation guard that rejects timeouts below a sane floor (for example 500 ms). _(A 50 ms timeout is an unrealistic value for a pool wait that is normally a few milliseconds to seconds.)_
- **long_term** - Add alerts on payment-service pool wait time and acquire-timeout count, and make health checks exercise a real pool acquire. _(Current health checks stayed green during a 28% error rate.)_
- **long_term** - Replace the latency-tuning rationale in OPS-2291 with a measured fix (for example query tuning or pool sizing) and test it in staging first. _(The ticket's goal of tail latency was not met and the change caused an outage.)_

## Open questions
- Did the connection hold time or pool size change in v3.1.3 (09-01 04:00) that would make the 5000 ms timeout insufficient? This was not checked.
- Is the exact per-request pool wait available in payment-service metrics? The data returned only logs.
- Why do two earlier-than-onset 'insufficient funds' declines appear, and are they related? They look like background noise.
- Is there a payment-service error_rate or 5xx series that breaks down the 503s by endpoint?
- Would an isolated test of the 50 ms setting in staging reproduce the timeouts? Not checked.

## Data gaps and tool failures (0 shown, 0 reported)
_None._
