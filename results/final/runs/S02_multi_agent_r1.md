# Incident report S02

- **Status:** CONCLUSIVE (confidence 0.50, margin 0.38, 9 verified supporting and 4 contradicting evidence items (31%))
- **System:** multi_agent · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** max_rounds_reached
- **Root cause:** `payment-service` - config_error (confidence 0.50)

## Summary
Checkout payment-step failures began abruptly at 10:00:00Z with payment-service error rate rising from about 0.25% to about 28% and checkout error rate from about 0.3% to about 12%. The system determination is conclusive at confidence 0.50, with the leading hypothesis H1 being the payment-service connection timeout change C09 (db.pool.connection_timeout_ms 5000 to 50 ms) applied at 09:58:00Z. The dominant error is 'Timeout acquiring connection from pool payments-db after 50ms (active=12, idle=0, waiting=31)', surfacing as 503s at checkout. The change precedes onset by about two minutes and is the only in-window change, but the mechanism that produced pool saturation is not established: a shorter timeout converts waits into fast failures and does not by itself explain saturation. Pool metrics, effective pod config, provider telemetry and error-rate definitions were not retrieved, so the conclusion carries moderate confidence and explicit caveats.

## Conclusion decision
- confidence 0.50, margin 0.38, 9 verified supporting and 4 contradicting evidence items (31%)
- Criteria: top `payment-service / config_error` confidence 0.50, margin 0.38, 9 verified supporting / 4 contradicting items (31% contradicting); 1 evidence-backed material critic objection(s), 6 non-blocking
  - objection: alternative_not_ruled_out: A demand or hold-time increase in payment-service or a provider slowdown holding connections could produce the same pool-exhaustion signature with an unchanged  [L0038, L0108, M34, M36]

## Ranked hypotheses
1. **payment-service** - config_error (confidence 0.50)
   - Mechanism: Config change C09 at 09:58:00Z cut payment-service db.pool.connection_timeout_ms from 5000 to 50 ms, about two minutes before onset. Pool acquisitions on payments-db (active=12, idle=0, waiting=31) now fail after 50 ms, and payment-service returns 503s that checkout surfaces on the payment step. The mechanism that raised waiting demand or hold time at 10:00 is not established.
   - Supporting evidence: `C09, L0193, L0197, L0353, L0194, M33, M12, M34, M32, M36, M37`
   - Contradicting evidence: `M34`
   - Assumptions: The 50 ms in the log is the effective pod setting from C09; Normal acquisition latency under current load is above 50 ms, which is unmeasured; Shallow health checks at 10:28 do not exercise the pool under load
2. **payments-db** - resource_exhaustion (confidence 0.12)
   - Mechanism: A DB-side slowdown or client-side connection hold-time increase, as in past P06, could hold pool connections longer and starve payment-service acquisitions, producing timeouts and 503s. Flat connection count and query latency weigh against this, though session and lock metrics were not retrieved.
   - Supporting evidence: `L0193, P06, M40`
   - Contradicting evidence: `M37, M40, M38, M41`
   - Assumptions: A hold-time increase began at onset with no recorded change; Session or lock metrics, not retrieved, would show it
3. **payment-provider** - dependency_failure (confidence 0.10)
   - Mechanism: A provider-side slowdown starting near 10:00 would hold payment-service pool connections longer, exhausting the pool and producing 503s upstream. Pre-onset provider latencies of 943-1363 ms show the provider is sometimes slow, but no provider telemetry exists to confirm an onset.
   - Supporting evidence: `L0038, L0108, D09`
   - Contradicting evidence: `H10, L0193`
   - Assumptions: Provider degradation began near 10:00; Provider latency would appear as pool hold time

## Observed facts
- checkout-service error_rate was flat at about 0.25-0.34% from 09:00 to 09:55 and jumped to 12.45% at 10:00, staying around 11.5-12.6% through 10:30. `M12`
- payment-service error_rate was about 0.19-0.25% before 10:00 and jumped to 28.43% at 10:00, ranging 25-29% through 10:30. `M33`
- payment-service latency_p99_ms fell from about 433-461 ms before 10:00 to about 135-145 ms from 10:00 onward while errors rose. `M34`
- payment-service CPU, memory and request rate (58-62 req/s) showed no step change at 10:00. `M32, M35, M36`
- Config change C09 on payment-service at 09:58:00Z set db.pool.connection_timeout_ms from 5000 to 50 (ticket OPS-2291, completed, author j.alvarez); it is the only change in the 09:30-10:30 window across all services. `C09`
- The first payment-service pool-timeout error is at 10:00:17Z, and the same signature (after 50ms, active=12, idle=0, waiting=31) repeats through 10:30 at roughly 30-60 second intervals. `L0193, L0353`
- The first checkout-service 503 from payment-service is logged at 10:00:19Z, about 2 seconds after the first pool timeout; about 25 such 503 warnings occur through 10:30. `L0194, L0352`
- payments-db connections stayed in a band of 116-124 and payments-db cpu, query latency p99 and replication lag were flat across 09:50-10:30, with no step at 10:00. `M37, M38, M40, M41`
- Before 10:00, payment-service WARN/ERROR lines were limited to slow provider responses (943-1363 ms) and insufficient-funds declines; no pool-timeout lines appear before 10:00. `L0038, L0108, L0131, L0164`
- Health checks at 10:28 (checkout /health, payment-service /health, payments-db SELECT 1, provider status page) all reported healthy; these checks are shallow and ran after C09. `H03, H10, H11, H12`

## Assumptions
- The 50 ms value in the pool-timeout log reflects the effective pod setting from C09; this was inferred from the change record and not read from pods.
- Normal pool acquisition latency under current load is above 50 ms; this is unmeasured.
- Health checks at 10:28 do not exercise the connection pool under load.
- The payment-service log set returned (50 lines at limit) is representative of the 10:00-10:30 errors, although it may be truncated.
- The 12% checkout and 28% payment-service error rates use different denominators, which is not documented.
- (unverified - no valid evidence cited) No payment-service pool wait-time, active/idle/waiting, or pool max size metric exists in the telemetry returned.

## Inferred conclusions
- Config change C09 (pool acquire timeout reduced to 50 ms) is the leading candidate for the 10:00 payment-step failures; the causal chain from C09 to pool saturation is not closed. (confidence 0.50) `C09, L0193, L0197, M33`
- The payments-db connection pool in payment-service was exhausted from 10:00, and this exhaustion drives the 503s that checkout surfaces. (confidence 0.60) `L0193, L0353, L0194`
- Demand did not rise at onset (flat request rate), and no measured payments-db connection or load increase at 10:00 explains saturation, so the saturation trigger is unknown. (confidence 0.45) `M36, M37, M40`
- A payments-db-side cause (connection count, CPU, query latency) is unlikely, though lock contention or hold-time increases are not ruled out because those metrics were not retrieved. (confidence 0.30) `M37, M38, M40, M41`
- A payment-provider slowdown holding connections longer is not ruled out, because provider latency and 5xx metrics were not retrieved; the provider has only a status-page health claim. (confidence 0.15) `H10, L0038, L0108`
- The checkout deploy v2.13.4 on 2026-09-01 is an unlikely cause given the 20-hour gap and its cart-focused scope. (confidence 0.20) `C07`

## Remediation
- **immediate** - Verify the effective db.pool.connection_timeout_ms and pool max size on running payment-service pods, and check whether OPS-2291 can be reverted to the prior 5000 ms value. _(The leading hypothesis depends on the effective pod value, which is unverified, and reverting the only in-window change is a low-risk test of the lead.)_
- **immediate** - Revert OPS-2291 (restore 5000 ms) if the effective value is confirmed as 50 ms, and monitor payment-service error rate and pool-timeout log lines for recovery. _(Restoring the prior timeout is a reversible mitigation supported by the timing and log signature, though the saturation trigger remains unexplained.)_
- **short_term** - Collect pool acquisition wait-time distribution, active/idle/waiting time series and pool max size for payment-service before and after 09:58. _(These metrics would show whether waits exceeded 50 ms before 10:00 and whether demand or hold time rose, which is needed to close the causal chain.)_
- **short_term** - Retrieve payment-provider call duration and 5xx rate, and payments-db session and lock-wait metrics for 09:50-10:30. _(These would test the H2 and H3 alternatives that remain open.)_
- **short_term** - Reconcile the checkout 12% and payment-service 28% error-rate definitions and retrieve untruncated payment-service ERROR/WARN logs. _(The gap and the possibly truncated log set limit confidence in the error-count picture.)_
- **long_term** - Add deep health checks that exercise pool acquisition under concurrency, and add pool-level alerting for acquisition wait and timeout counts. _(Current shallow checks passed during the outage, so they did not detect it; pool alerting would catch similar saturation earlier.)_
- **long_term** - Change-review rule: require load or canary validation for pool timeout changes and record the rationale and expected effect. _(OPS-2291 was a 100x timeout reduction that was applied without a validated effect on failure behaviour.)_

## Open questions
- Is the effective running pod value of db.pool.connection_timeout_ms 50 ms, and was OPS-2291 rolled back at any point?
- What drove pool saturation at 10:00 (demand, hold time, or DB-side slowdown), given flat request rate and DB connection count?
- Did acquisition waits exceed 50 ms before 10:00, and what is the pool max size?
- Did payment-provider latency or 5xx rise at 10:00, and does the provider show any telemetry?
- Why do the checkout 12% and payment-service 28% error rates differ, and what are their denominators?

## Data gaps and tool failures (10 shown, 35 reported)
- No breakdown of errors by HTTP status code from payment-service itself. The 5xx status is only seen indirectly, as 503s logged by checkout-service.
- Endpoint, payment method, region and pod dimensions are not available through these tools. The concentration question could not be answered.
- payment-service log query reported 50 matching lines with 50 returned at limit 50, so the set may be truncated. The ERROR count is likely understated for 10:00-10:30.
- No metric for the payments-db connection pool (active/idle/waiting) or for payments-db itself was queried. The pool saturation is known only from log text.
- The checkout-service error_rate denominator and the payment-service error_rate definition are not documented in the tool output, so the 12% vs 28% gap cannot be reconciled directly.
- Telemetry for pool wait, connection error and payment-provider error rates was not queried, so the mechanism is not confirmed.
- Change history for infra and feature flags was filtered by service and may miss shared-infra changes to payments-db or the payment provider.
- No check for whether OPS-2291 was rolled back or whether the value is still 50 in effect.
- Health checks are shallow (/health 200, SELECT 1, status page) and all ran at 10:28, after C09. None exercises the payment path or real pool behaviour during the 10:00-10:30 window.
- 26 further gap report(s) in 26 group(s) omitted here (mostly about: payment-service, returned, pool, checked, query, metrics); the full list is in the run record.
