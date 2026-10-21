# Incident report S02

- **Status:** CONCLUSIVE (confidence 0.85, margin 0.77, 7 verified supporting and 3 contradicting evidence items (30%))
- **System:** baseline · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** agent_finished
- **Root cause:** `payment-service` - config_error (confidence 0.85)

## Summary
Payment failures began at 10:00 UTC, right after payment-service's connection-acquire timeout was cut from 5000 ms to 50 ms at 09:58 UTC (config change C09). Payment-service logs show its payments-db pool saturated (active=12, idle=0, waiting=31) and timing out at 50 ms, which returns 503s to checkout. The database itself looks healthy (connections flat, query latency normal), so the fault appears to be the client-side timeout change rather than database capacity. Confidence is high but not fully verified: no direct test of the timeout value was run, and checkout's full error volume is only partly visible.

## Conclusion decision
- confidence 0.85, margin 0.77, 7 verified supporting and 3 contradicting evidence items (30%)
- Criteria: top `payment-service / config_error` confidence 0.85, margin 0.77, 7 verified supporting / 3 contradicting items (30% contradicting); 0 evidence-backed material critic objection(s), 0 non-blocking

## Ranked hypotheses
1. **payment-service** - config_error (confidence 0.85)
   - Mechanism: Reducing db.pool.connection_timeout_ms from 5000 to 50 ms at 09:58 causes requests waiting for a payments-db pool connection (active=12, waiting=31) to time out, returning 503s to checkout, while the DB itself stays healthy.
   - Supporting evidence: `C09, L0193, L0197, M33, M34, M12, L0194`
   - Contradicting evidence: `L0131, L0164, L0207`
   - Assumptions: The config key controls the acquire timeout for the payments-db pool.; Waits normally fall under 50 ms.
2. **payments-db** - resource_exhaustion (confidence 0.08)
   - Mechanism: Connection or capacity exhaustion on payments-db slows connection grants so the pool times out.
   - Supporting evidence: `L0193, L0212`
   - Contradicting evidence: `M37, M40, M41, H12`
   - Assumptions: The DB-side pool limit is not visible in the metrics.
3. **payment-provider** - dependency_failure (confidence 0.05)
   - Mechanism: External provider slowness or errors cause payment-service 5xx and checkout failures.
   - Supporting evidence: `L0194`
   - Contradicting evidence: `M34, H10`
   - Assumptions: Provider-side errors would show as provider response timeouts; only 2 such log lines were seen.

## Observed facts
- A config change set payment-service db.pool.connection_timeout_ms from 5000 to 50 (ticket OPS-2291, by j.alvarez) at 09:58:00Z. `C09`
- payment-service error_rate jumped from ~0.2% (09:55 point 0.25%) to 28.43% at 10:00:00Z and stayed 25-29% through 10:30. `M33`
- payment-service latency_p99 dropped from ~433-461 ms to ~135-145 ms starting 10:00:00Z. `M34`
- payment-service logs show 45 'Timeout acquiring connection from pool payments-db after 50ms (active=12, idle=0, waiting=31)' errors, first at 10:00:17Z. `L0193, L0197, L0199, L0205, L0253`
- checkout-service error_rate rose from ~0.3% to 12.45% at 10:00:00Z, and its logs show 'payment-service call failed: 503 Service Unavailable' starting 10:00:19Z. `M12, L0194, L0201`
- payments-db connections stayed at 116-125 throughout 09:00-10:30, with query_latency_p99 about 11.5-12.5 ms and replication lag about 0.4 s. `M37, M40, M41`
- payment-service CPU (~32-34%) and memory (~53-57%) were flat across the window. `M32, M35`
- payments-db health check reports 'accepting connections; SELECT 1 ok' at 10:28Z; payment-service /health returned 200. `H12, H11`
- Only 3 'insufficient funds' declines appear in payment-service logs in the window, spread across 09:40-10:02. `L0131, L0164, L0207`
- Other changes in the prior 3 days (inventory v4.1.9, search v5.3.1, payment v3.1.3 on 09-01 04:00, checkout v2.13.4 on 09-01 14:00, node pool upgrade 09-02 01:00) all predate the 10:00 onset by many hours. `C03, C04, C05, C07, C08`

## Assumptions
- The 50 ms value is applied to the payments-db pool acquire timeout in payment-service (the config key name implies this), and the change took effect at 09:58 with no other concurrent changes.
- Connection acquisition waits are normally well below 50 ms under the ~60 req/s load, so the reduced timeout causes failures even without database slowness.
- payments-db health checks are shallow and do not measure pool-level or write-path behaviour.
- Checkout's 12% error rate reflects payment 503s propagating without a retry that masks them, so checkout's error count is not fully visible in the sampled logs.

## Inferred conclusions
- The root cause is the 09:58 config change reducing payment-service's payments-db connection acquire timeout from 5000 ms to 50 ms, which makes normal pool waits exceed the timeout and produces 503s that propagate to checkout. (confidence 0.85) `C09, L0193, M33, M12, L0194`
- A genuine payments-db capacity or connection exhaustion problem is unlikely, since DB connections, CPU and query latency stayed flat while errors spiked. (confidence 0.80) `M37, M38, M40`
- The 'insufficient funds' declines are background noise and not the cause of the 5xx spike. (confidence 0.85) `L0131, L0164, L0207`
- Reverting the timeout to 5000 ms should restore payment success, since latency was normal before the change. (confidence 0.75) `C09, M34, M33`

## Remediation
- **immediate** - Revert db.pool.connection_timeout_ms on payment-service from 50 back to 5000 ms (roll back OPS-2291 change). _(The change at 09:58 directly precedes the 10:00 onset; reverting is the fastest mitigation.)_
- **immediate** - Confirm recovery: payment-service error_rate returns below 1% and checkout 503 warnings stop. _(Verifies the hypothesis and the mitigation.)_
- **short_term** - Review OPS-2291 with the author before any further tail-latency tuning; the reduced timeout traded latency for hard failures. _(Changing a timeout that gates pool acquisition should be load-tested first.)_
- **short_term** - Add a config-change guard or canary requirement for payment-service DB pool settings. _(Prevents a single-value change from taking down the payment path.)_
- **long_term** - Add pool-wait and acquire-timeout alerts on payment-service, and a deep health check that exercises a pool acquire and write. _(Current /health and DB SELECT 1 checks stayed green during a full outage.)_

## Open questions
- Was the 50 ms value meant for a different pool or environment, and what was the intended effect on tail latency?
- Why does checkout's error rate (12%) sit well below payment-service's (28%); is there retry or fallback masking the failures?
- Did the change in fact take effect on all payment-service replicas, or only some?
- Is there any 09:58-10:00 DB-side event not visible in the sampled metrics?

## Data gaps and tool failures (0 shown, 0 reported)
_None._
