# Incident report S02

- **Status:** CONCLUSIVE (confidence 0.85, margin 0.77, 8 verified supporting and 4 contradicting evidence items (33%))
- **System:** baseline · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** agent_finished
- **Root cause:** `payment-service` - config_error (confidence 0.85)

## Summary
Payment-service started failing at 10:00:00Z, when its error rate jumped from about 0.2% to about 28% and checkout began receiving 503s from payment-service. The change at 09:58:00Z (OPS-2291, by j.alvarez) cut db.pool.connection_timeout_ms from 5000 to 50, and the logs show pool-acquisition timeouts at exactly the 50ms value. The payments-db metrics are flat, so the database does not appear saturated. The most likely cause is that the timeout change made the pool fail requests that would have waited normally. The timeout change is the leading hypothesis, and rollback is the fastest mitigation.

## Conclusion decision
- confidence 0.85, margin 0.77, 8 verified supporting and 4 contradicting evidence items (33%)
- Criteria: top `payment-service / config_error` confidence 0.85, margin 0.77, 8 verified supporting / 4 contradicting items (33% contradicting); 0 evidence-backed material critic objection(s), 0 non-blocking

## Ranked hypotheses
1. **payment-service** - config_error (confidence 0.85)
   - Mechanism: The db.pool.connection_timeout_ms reduction from 5000 to 50ms at 09:58Z makes requests that wait for one of 12 pool connections fail after 50ms. Under normal concurrency, waiters queue (waiting=31) and fail with 503s to checkout.
   - Supporting evidence: `C09, L0193, L0197, L0211, M33, M34, L0194, L0201`
   - Contradicting evidence: `M37, M38, M40, H12`
   - Assumptions: The pool size is 12 and was unchanged.; Health checks do not exercise pool acquisition.
2. **payments-db** - resource_exhaustion (confidence 0.08)
   - Mechanism: Database-side saturation or slow queries hold pool connections, so acquire waits build up and time out.
   - Supporting evidence: `L0193, L0211`
   - Contradicting evidence: `M37, M38, M40, M41, H12`
   - Assumptions: The DB metrics reflect the right pool and the DB is the bottleneck.
3. **payment-provider** - dependency_failure (confidence 0.05)
   - Mechanism: External provider slowness or declines cause payment-service to hold connections or return errors.
   - Supporting evidence: `L0131, L0164, L0207, L0300`
   - Contradicting evidence: `H10, M34`
   - Assumptions: The status page reflects actual provider health.

## Observed facts
- payment-service error_rate was 0.18–0.25% from 09:00 to 09:55Z and jumped to 28.43% at 10:00Z (peak 28.75% at 10:30Z). `M33`
- payment-service latency_p99_ms fell from about 433–461ms (09:00–09:55Z) to about 137ms from 10:00Z onward. `M34`
- A config change at 09:58:00Z set payment-service db.pool.connection_timeout_ms from 5000 to 50 (ticket OPS-2291, reduce tail latency), by j.alvarez. `C09`
- From 10:00:17Z, payment-service logged 45 'Timeout acquiring connection from pool payments-db after 50ms' errors, each with active=12, idle=0, waiting=31. `L0193, L0197, L0199, L0205, L0211`
- checkout-service logged 25 WARNs 'payment-service call failed: 503 Service Unavailable' starting at 10:00:19Z. `L0194, L0201, L0209`
- payments-db connections stayed at 116–125 and cpu_pct at 33.8–36.4% across 09:30–10:30Z; query_latency_p99 stayed at about 11.5–12.5ms; replication lag stayed about 0.4s. `M37, M38, M40, M41`
- payment-service cpu, memory and request_rate were unchanged across the onset (request_rate about 58–62 req/s). `M32, M35, M36`
- Three 'insufficient funds (declined)' errors appeared at 09:40:56Z, 09:51:18Z and 10:02:52Z, before and during the incident. `L0131, L0164, L0207`
- Health checks at 10:28Z reported payment-service, payments-db and payment-provider as healthy; the payments-db check is 'SELECT 1 ok'. `H11, H12, H10`

## Assumptions
- The health checks are shallow (HTTP /health and SELECT 1) and do not exercise pooled connection acquisition or payment-provider calls.
- The payment-provider status page reflects real provider health.
- The connection pool size is 12 (active=12 is the ceiling in the log), and 'waiting=31' reflects queued requests at the time of each error.
- No other config or deploy change affected payment-service or payments-db between 09:58Z and 10:30Z; the change history shows none.

## Inferred conclusions
- The 50ms connection-acquire timeout introduced at 09:58Z is the primary cause: the pool (12 connections, all busy) cannot serve queued requests within 50ms, so requests fail fast with 503s. The 5000ms value had been masking the same queueing as slow requests. (confidence 0.85) `C09, L0193, M33, M34`
- The database is not the origin: its connections, CPU, latency and replication lag are flat through the window, so the failure is client-side pool configuration rather than DB exhaustion. The past P06 pattern (connection leak) does not match these metrics. (confidence 0.75) `M37, M38, M40, M41`
- The 'insufficient funds' declines are background noise (issuer-side, low volume) and do not explain the 28% error rate. (confidence 0.80) `L0131, L0164, L0207, L0300`
- The latency drop to about 137ms is consistent with fast failure: requests that time out at 50ms return errors quickly, which lowers p99 while the error rate rises. (confidence 0.60) `M34, M33`

## Remediation
- **immediate** - Roll back db.pool.connection_timeout_ms from 50 to 5000 on payment-service (revert OPS-2291) and confirm the error rate returns to about 0.2%. _(The change at 09:58Z precedes the onset at 10:00Z and the errors quote the 50ms timeout.)_
- **immediate** - Notify checkout and payments owners of the failed checkouts since 10:00Z and check for orders needing reconciliation. _(About 28% of payment calls failed during the window.)_
- **short_term** - Re-test OPS-2291 in staging with a timeout value that fits the pool's queueing behaviour, and/or increase pool size, rather than lowering the timeout alone. _(A 50ms acquire timeout is far below the observed normal wait.)_
- **long_term** - Add a config-change review gate for pool and timeout parameters in payment-service. _(A single config value change caused a P1 outage without a canary.)_
- **long_term** - Add pool-saturation and acquire-wait alerts and make health checks exercise pool acquisition. _(Current health checks reported healthy during 28% failures.)_

## Open questions
- Why was the pool at active=12 with waiting=31 at 10:00Z, and was that load present before the change? Pool metrics are not in the telemetry.
- Was the change tested in staging, and who approved OPS-2291?
- Did the 50ms timeout have any effect on the latency numbers the ticket was targeting?
- What is the count of failed payments and whether any were charged but not recorded?

## Data gaps and tool failures (0 shown, 0 reported)
_None._
