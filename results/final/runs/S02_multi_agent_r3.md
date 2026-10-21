# Incident report S02

- **Status:** INCONCLUSIVE (top hypothesis confidence 0.45 is below 0.50; contradicting evidence is 43% of the weighed evidence (max 35%))
- **System:** multi_agent · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** max_rounds_reached

## Summary
Checkout payment-step errors and payment-service error rates stepped up together at 10:00:00Z, with payment-service payments-db pool acquire timeouts (50 ms, active=12, idle=0, waiting=31) first logged at 10:00:17Z and checkout 503s at 10:00:19Z. The only change in the window, config change C09 at 09:58:00Z lowering db.pool.connection_timeout_ms from 5000 to 50, is the leading candidate, but the system determination is INCONCLUSIVE because the top hypothesis confidence (0.45) is below 0.50 and contradicting evidence is 43% of weighed evidence (max 35%). The alternative that a connection leak or client-side pool shrink in payment-service began near 10:00 (H2, 0.35) fits the same signature and was not separated, because pool occupancy before 09:58 is unreported and the batch schedule was not retrieved. Database metrics stayed flat, pointing to a client-side constraint rather than database load. No root cause is asserted; mitigation and the checks listed below are needed to settle it.

## Conclusion decision
- top hypothesis confidence 0.45 is below 0.50
- contradicting evidence is 43% of the weighed evidence (max 35%)
- Criteria: top `payment-service / config_error` confidence 0.45, margin 0.10, 8 verified supporting / 6 contradicting items (43% contradicting); 2 evidence-backed material critic objection(s), 6 non-blocking
  - objection: unsupported_claim: The mechanism requires the pool to be near saturation under normal load before 09:58 so that a 50 ms wait is reachable. No pool active/idle/waiting data exists  [L0193, L0289]
  - objection: alternative_not_ruled_out: H2 (connection leak or client-side pool shrink in payment-service starting near 10:00) fits the same constant pool state and step change. Flat DB metrics are co [M37, M38, M40, L0193]

## Ranked hypotheses
1. **payment-service** - config_error (confidence 0.45)
   - Mechanism: Config change C09 at 09:58:00Z cut db.pool.connection_timeout_ms from 5000 to 50 ms, so payments-db pool acquires that wait longer than 50 ms fail fast. This matches the pool-timeout ERRORs from 10:00:17Z (active=12, idle=0, waiting=31), the checkout 503s from 10:00:19Z, and the p99 latency drop. The mechanism requires the pool to already be near saturation, which is not verified.
   - Supporting evidence: `C09, L0193, L0194, M33, M12, M34, L0197, L0352, P06`
   - Contradicting evidence: `M36, M32`
   - Assumptions: Pool was already near saturation under normal load so a 50 ms acquire wait is reachable; No other pool-affecting change such as a leak is active; Logs are representative despite the 50-line cap
2. **payment-service** - resource_exhaustion (confidence 0.35)
   - Mechanism: A connection leak or pool shrink in payment-service begins near 10:00 and exhausts the payments-db pool, so waiting requests hit the 50 ms acquire timeout. This produces the same constant pool state and step change, while database metrics stay flat because the constraint is client-side. C09 is only coincident in timing and is not a contradiction.
   - Supporting evidence: `L0193, L0353, P06, M37, M38`
   - Contradicting evidence: none
   - Assumptions: A leak or shrink began at about 10:00 and is not in the change history; The timing overlap with C09 is coincidental; Pool max size was not changed outside logged changes

## Observed facts
- checkout-service error_rate rose from 0.25-0.34% (09:00-09:55) to 12.45% at 10:00:00Z and stayed between 11.5% and 12.6% through 10:30. `M12`
- payment-service error_rate rose from about 0.2% to 28.43% at 10:00:00Z and stayed between 25% and 28.75% through 10:30. `M33`
- The dominant payment-service error is 'Timeout acquiring connection from pool payments-db after 50ms (active=12, idle=0, waiting=31)', first at 10:00:17Z, recurring through 10:30 (about 45 logged, a floor due to a 50-line cap). `L0193, L0197, L0353`
- Checkout logged 'payment-service call failed: 503 Service Unavailable' first at 10:00:19Z, with about 25 such lines through 10:30 (a floor; the count is far below 12% of about 85 req/s). `L0194, L0352`
- Config change C09 on payment-service at 09:58:00Z (j.alvarez, completed, OPS-2291) set db.pool.connection_timeout_ms from 5000 to 50; no other deploy, feature flag, or infra change appears in 08:00-10:30 for the incident services. `C09`
- payments-db connections, cpu_pct, query_latency_p99_ms, and replication_lag_s stayed flat across 09:30-10:30 with no step change at 10:00. `M37, M38, M40, M41`
- payment-service latency_p99_ms fell from about 433-461 ms to about 137 ms at 10:00:00Z while errors rose; payment-service cpu, memory and request rate showed no step change. `M34, M32, M35, M36`
- A DEBUG keyword search for 'pool' in payment-service from 09:00 to 09:59:59 returned zero lines; no pool-state values are reported before 10:00. `L0193`
- Health checks at 10:28Z for checkout, payment-service, payments-db, payment-provider and other dependencies were all healthy, but these checks are shallow (/health 200, SELECT 1, status page). `H03, H11, H12, H10`
- Past incident P06 (2026-08-08) had payment timeouts from payments-db pool exhaustion caused by a connection leak in a nightly batch job. `P06`

## Assumptions
- Payment-service pool was already near saturation under normal load, so a 50 ms acquire wait is reachable; this is not directly measured.
- Pool max size is 12, inferred from active=12 in log text and not reported as a metric.
- No pool-affecting change such as a connection leak or batch-job hold was active outside the change log.
- Logs are representative of the full error population despite the 50-line cap and apparent sampling.
- Health checks are shallow and do not exercise pool acquisition, so their green status does not exclude the failure.
- Timing order (payment-service first, checkout second) is inferred from log timestamps within the same 5-minute bucket.

## Inferred conclusions
- The failure is most likely in payment-service's payments-db connection pool (client-side acquire timeouts), not database capacity. (confidence 0.60) `L0193, M37, M38, M40`
- C09 (timeout reduced from 5000 ms to 50 ms, two minutes before onset) is the leading candidate trigger (H1, confidence 0.45), but it is not established as the cause because the saturation precondition is unverified. (confidence 0.45) `C09, L0193, L0194, M33`
- A connection leak or client-side pool shrink in payment-service starting near 10:00 (H2, confidence 0.35) remains a live alternative that fits the same signature and was not ruled out. (confidence 0.35) `L0193, P06, M37`
- Payment-service is the origin and checkout-service errors are propagated through the sync_http dependency; the direction rests on log timing alone. (confidence 0.50) `M33, M12, L0193, L0194, D04`
- Card declines and payment-provider latency are background noise and do not explain the step change at 10:00. (confidence 0.60) `L0131, L0164, L0207, L0038, L0108`
- A database-side origin is unlikely, but the shallow health checks do not exclude pool-level saturation on the database connection path. (confidence 0.40) `H12, M37, M40`

## Remediation
- **immediate** - Revert C09 by restoring db.pool.connection_timeout_ms from 50 ms to the prior 5000 ms, and monitor whether payment-service errors and checkout 503s recover. _(C09 is the only change near onset and the leading candidate; reverting is low-risk and is a reversible test that can separate H1 from H2 if errors recover.)_
- **immediate** - If errors persist after the revert, treat H2 as active: restart or recycle payment-service instances to clear any leaked connections, and check pool occupancy during that action. _(Persistence after reverting C09 would weaken H1 and point toward a leak or pool shrink, which a restart mitigates.)_
- **immediate** - Capture payment-service pool active, idle, waiting and max size at intervals before and after 09:58, and the acquire-wait distribution. _(These measurements test the unverified saturation precondition for H1 and would discriminate H1 from H2.)_
- **short_term** - Retrieve the nightly batch job schedule and payments-db connection usage grouped by client for 09:50-10:05 UTC, and check the untruncated logs by endpoint, region and instance. _(These are the checks that would test the H2 batch-leak alternative and the scope of the error concentration.)_
- **short_term** - Add a deep health check that exercises pool acquisition with a realistic timeout, and alert on pool wait and timeout counts. _(Current shallow health checks stayed green while payment-service failed, so they missed the fault.)_
- **long_term** - Require a documented load-tested rationale and peer review for timeout changes in shared pool config, with a rollback plan. _(C09 cut a timeout 100x without measured acquire-wait data, which made the change high-risk.)_
- **long_term** - Fix the batch-job connection leak identified in P06 and verify connections are released, if the batch schedule confirms overlap. _(P06 shows the same signature from a batch leak, so this is a recurrence risk even if H1 is the cause here.)_

## Open questions
- Was payment-service pool occupancy near saturation before 09:58, and what is the true max pool size?
- What is the acquire-wait distribution, and do normal waits exceed 50 ms?
- Did a nightly batch job or long-held connection overlap 09:50-10:05 on payments-db, as in P06?
- Does reverting C09 restore error rates to baseline, which would discriminate H1 from H2?
- Are the errors concentrated on specific endpoints, regions or instances, given the 50-line cap and missing dimensions?
- Does the checkout 12% error rate reconcile with about 25 logged 503s, and are logs sampled?

## Data gaps and tool failures (10 shown, 31 reported)
- The 'payment-service 5xx' is not separately logged as HTTP 5xx by payment-service in these results. The payment-service error_rate series is not split by status code, so the 5xx code breakdown cannot be confirmed from its side.
- Log output is capped at 50 lines per query. Payment-service showed 50 returned lines (48 ERROR, 2 WARN) and checkout showed 28 lines, so the counts are truncated and the timeout count (about 45) is a floor. The checkout 503 log count (~25 in 30 min) is far below 12% of ~85 req/s, which suggests the logs are sampled or incomplete.
- No endpoint, region or instance dimension was returned for any series or log line, so concentration by those dimensions could not be assessed.
- Telemetry only covers 09:00–10:30, so no pre-incident baseline for the pool or any recent change is available here.
- The change history returned no records for the other dependencies (payments-db, payment-provider, inventory, auth), so their changes are unverified beyond the 'no record' result.
- Health checks are a single snapshot at 10:28:00Z and do not show error rates or pool metrics; no telemetry on pool waits was queried.
- Only a single change was returned for the window, so it is unclear whether the change history is complete.
- No error-rate, latency or connection-pool metrics were available, so the 12% checkout error rate and the payment-service 5xx could not be verified against the timeline.
- Health checks were taken only at 10:28 UTC, not across the 09:00–10:30 window, so the timing of any dependency degradation is unknown.
- 22 further gap report(s) in 22 group(s) omitted here (mostly about: pool, payments-db, payment-service, retrieved, checked, window); the full list is in the run record.
