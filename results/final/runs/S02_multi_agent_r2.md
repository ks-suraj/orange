# Incident report S02

- **Status:** CONCLUSIVE (confidence 0.60, margin 0.40, 10 verified supporting and 2 contradicting evidence items (17%))
- **System:** multi_agent · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** critic_accepted
- **Root cause:** `payment-service` - config_error (confidence 0.60)

## Summary
Checkout payment failures began at about 10:00 UTC, with checkout-service error rate rising from about 0.26% to 12.45% and payment-service error rate from about 0.25% to 28.43%. The system determination is conclusive at confidence 0.60, with the leading hypothesis H1 being a config change C09 at 09:58:00Z that lowered db.pool.connection_timeout_ms on payment-service from 5000 to 50. Payment-service pool timeouts ('Timeout acquiring connection from pool payments-db after 50ms, active=12, idle=0, waiting=31') begin at 10:00:17Z, about two seconds before the first checkout 503 at 10:00:19Z, so checkout appears to be a downstream victim. payments-db connections, latency and CPU stayed flat, which argues against database saturation. The live config value, its unit and its binding to the emitting pool were not verified, so the mechanism is strongly supported but not directly confirmed.

## Conclusion decision
- confidence 0.60, margin 0.40, 10 verified supporting and 2 contradicting evidence items (17%)
- Criteria: top `payment-service / config_error` confidence 0.60, margin 0.40, 10 verified supporting / 2 contradicting items (17% contradicting); 0 evidence-backed material critic objection(s), 6 non-blocking

## Ranked hypotheses
1. **payment-service** - config_error (confidence 0.60)
   - Mechanism: Config change C09 at 09:58:00Z cut db.pool.connection_timeout_ms from 5000 to 50 on payment-service, so connection acquisitions from the payments-db pool time out under normal contention. The logged 'Timeout acquiring connection from pool payments-db after 50ms' errors begin at 10:00:17Z, producing payment-service 5xx that checkout-service surfaces as 503s from 10:00:19Z.
   - Supporting evidence: `C09, L0193, L0197, L0353, L0194, M33, M12, M34, M37, M40`
   - Contradicting evidence: `H11, H12`
   - Assumptions: C09 value applies to the pool emitting the timeout logs; Normal acquisition under current load exceeds 50 ms, which is not directly measured; Shallow health checks at 10:28Z do not exercise pool acquisition
2. **payment-service** - resource_exhaustion (confidence 0.20)
   - Mechanism: A connection leak in payment-service holds payments-db pool connections until the pool is saturated (active=12, idle=0, waiting=31), so acquisitions time out, as in past incident P06. Per-client connection data was not retrieved, so an aggregate-flat database count does not rule this out.
   - Supporting evidence: `P06, L0193, L0353`
   - Contradicting evidence: `M37`
   - Assumptions: A leak would show an abrupt onset without a visible aggregate connection rise; A leak source such as a batch job ran near 10:00Z, which is unverified
3. **payment-provider** - dependency_failure (confidence 0.08)
   - Mechanism: Provider-side slowness holds payment-service pool connections longer, starving the pool and causing acquisition timeouts. Evidence is limited to isolated pre-onset latency warnings and a green status page.
   - Supporting evidence: `L0038, L0108`
   - Contradicting evidence: `H10, M36`
   - Assumptions: Provider latency would hold connections long enough to exhaust the pool; The status page reflects provider state

## Observed facts
- Config change C09 on payment-service at 2026-09-02T09:58:00Z set db.pool.connection_timeout_ms from 5000 to 50 (ticket OPS-2291), status completed, by j.alvarez; it is the only payment-service change in the 08:00-10:30Z window. `C09`
- checkout-service error_rate was 0.25-0.29% from 09:00 to 09:45 and 12.45% at 10:00:00Z, peaking at 12.62% at 10:05. `M12`
- payment-service error_rate was 0.19-0.25% before 10:00 and 28.43% at 10:00:00Z, peaking at 28.75% at 10:30. `M33`
- The first payment-service pool timeout error is at 10:00:17Z, with 45 of 50 returned ERROR/WARN lines being pool timeouts through 10:30:00Z; none appear before 10:00. `L0193, L0197, L0353`
- The first checkout-service 503 'payment-service call failed' warning is at 10:00:19Z and recurs through 10:30:00Z. `L0194, L0352`
- payments-db total connections stayed between 116 and 125 across 09:30-10:30Z with no step change at 10:00; query latency p99 and replication lag were also flat. `M37, M40, M41`
- payment-service cpu, memory and request rate stayed in normal ranges across the onset; request rate was 58-62 req/s. `M32, M35, M36`
- Health checks at 10:28Z reported checkout-service, payment-service and payments-db healthy; payment-provider healthy per status page only. These checks are shallow and ran after onset. `H03, H11, H12, H10`
- Insufficient-funds declines appeared three times at low background rate (09:40:56, 09:51:18, 10:02:52) and were not part of the pool-timeout pattern. `L0131, L0164, L0207`
- Past incident P06 (2026-08-08) had payment timeouts from payments-db connection exhaustion, caused by a connection leak in a nightly batch job. `P06`

## Assumptions
- C09 value applies to the payment-service pool that emits the 'Timeout acquiring connection' logs; the key was not verified against the live config.
- Normal connection acquisition under current load exceeds 50 ms; this is not directly measured because pool wait-time metrics are unavailable.
- The shallow /health and SELECT 1 checks at 10:28Z do not exercise pool acquisition, so they neither confirm nor rule out pool exhaustion.
- The 12% checkout error rate is partial because checkout retries and only part of traffic reaches payment-service; this has not been confirmed.
- The status page reflects payment-provider state; provider-side pool hold times were not measured.

## Inferred conclusions
- The C09 reduction of the payment-service payments-db pool connection timeout from 5000 ms to 50 ms is the most likely cause of the payment-service 5xx and checkout payment-step failures starting at about 10:00 UTC. (confidence 0.60) `C09, L0193, L0194, L0353, M12, M33`
- The failures are driven by payment-service's pool being saturated (active=12, idle=0, waiting=31) rather than by database load, since payments-db metrics are flat. (confidence 0.60) `L0193, M37, M40`
- Checkout-service is a downstream victim of payment-service failures rather than the origin, given the 2-second lead and synchronous call path. (confidence 0.60) `L0193, L0194, D04`
- A payment-service connection leak (H2) is a less likely alternative, weakened by flat aggregate connections and the absence of a trigger, but not excluded because per-client attribution is missing. (confidence 0.20) `M37, P06`
- Payment-provider slowness (H3) is unlikely to be the primary cause given isolated pre-onset latency warnings and no provider-side pool-hold evidence. (confidence 0.08) `L0038, L0108, H10`
- Insufficient-funds declines are background activity and do not explain the spike in errors. (confidence 0.60) `L0131, L0164, L0207`

## Remediation
- **immediate** - Restore db.pool.connection_timeout_ms on payment-service to its prior value of 5000 ms (rollback of C09) and confirm the live value. _(C09 is the leading cause and rollback is the fastest mitigation; the effect on error rate should then be checked.)_
- **immediate** - Monitor payment-service and checkout-service error rates and pool timeout log lines after the rollback to confirm recovery. _(Confirming recovery tests the H1 mechanism directly and would validate the change as causal.)_
- **short_term** - Review the OPS-2291 change for unit and key correctness and the intended value before any reapplication. _(The change record does not state a unit, and the 50 ms value was not verified against the consumer.)_
- **short_term** - Add pool acquisition wait-time and timeout-rate metrics for payment-service's payments-db pool, plus per-client connection attribution on payments-db. _(These metrics are missing and are needed to separate config from leak and to test the saturation mechanism.)_
- **long_term** - Require a staged rollout and canary validation for config changes to connection pool and timeout settings. _(A single config change reduced a timeout 100-fold without an effect check, causing a P1 incident.)_
- **long_term** - Deepen health checks to exercise pool acquisition under load, not only /health and SELECT 1. _(Current checks reported healthy during a failure and cannot detect pool exhaustion.)_
- **long_term** - Alert on payment-service pool saturation (waiting count above zero, idle at zero). _(Pool saturation was visible in logs for 30 minutes before detection through the error rate alone.)_

## Open questions
- What is the live value of db.pool.connection_timeout_ms on payment-service, and is the key read in milliseconds by the consumer?
- Does the 50 ms timeout apply to the same pool that emits the timeout logs, and what is the normal acquisition time under current load?
- Does restoring the timeout to 5000 ms reduce the payment-service error rate?
- What are the per-client payments-db connection counts for 09:50-10:05Z, to separate a config cause from a leak (H2)?
- Why is the checkout error rate about 12% when payment-service is at about 28%; what are the endpoint, payment-method and instance breakdowns?

## Data gaps and tool failures (10 shown, 37 reported)
- Telemetry for error rates, latency and pool metrics was not in scope of this query, so onset timing relative to C09 was not verified against the 12% error rate.
- Health checks are shallow and only sampled at 10:28Z, after onset; no pre-change health data was retrieved.
- Past-incident search returned only two loosely matching records; no confirmed precedent for this config change.
- Config diff for C09 (whether 50 applies to the right pool or a unit error occurred) was not retrieved.
- No breakdown by endpoint, payment method, or instance was obtained; the logs returned did not include those fields, and the tool-call budget was exhausted.
- Only the top 50 payment-service and 28 checkout-service WARN/ERROR lines were returned, so the full error counts for each status code are not known. Only 1 ERROR in checkout and 48 in payment-service were visible in the returned sets.
- No INFO/DEBUG logs were queried, so the exact pool-acquisition path and any preceding connection-pool changes were not examined.
- No per-instance metrics (CPU/error rate per pod) were queried; the instance concentration question is unanswered.
- No change-history or deployment records were checked, so no trigger for the 10:00 onset is confirmed.
- 28 further gap report(s) in 28 group(s) omitted here (mostly about: payment-service, pool, change, retrieved, config, payments-db); the full list is in the run record.
