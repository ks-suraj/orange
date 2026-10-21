# Incident report S09

- **Status:** INCONCLUSIVE (top hypothesis confidence 0.45 is below 0.50; contradicting evidence is 73% of the weighed evidence (max 35%))
- **System:** multi_agent · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** max_rounds_reached

## Summary
Inventory-service p99 latency, error rate and CPU stepped sharply between the 14:55 and 15:00 UTC samples, and checkout-service latency mirrored the step while its own load and CPU stayed flat. The system determination is INCONCLUSIVE: the top hypothesis (H-A, flag C09 raising realtime_stock_recalc to 100% and driving StockRecalculator.recomputeAll load) has confidence 0.45, below the 0.50 threshold, and contradicting evidence is 73% against a 35% maximum. The flag-to-recomputeAll link is unverified because flag history and past-incident queries were budget-exhausted, and the log searches for the flag and recalculator terms returned nothing in 14:50-15:00. A non-flag-gated recompute job (H-B, confidence 0.25) fits the same signature and is not ruled out, so no root cause is asserted. Inventory-db is unlikely to be the origin given flat query latency, but its CPU rise is unexplained. Health checks at 15:28 were green but are shallow and do not exercise the slow path.

## Conclusion decision
- top hypothesis confidence 0.45 is below 0.50
- contradicting evidence is 73% of the weighed evidence (max 35%)
- Criteria: top `inventory-service / config_error` confidence 0.45, margin 0.20, 3 verified supporting / 8 contradicting items (73% contradicting); 2 evidence-backed material critic objection(s), 4 non-blocking
  - objection: unsupported_claim: The causal mechanism requires that realtime_stock_recalc gates StockRecalculator.recomputeAll. No ledger record confirms this: the flag-history and past-inciden [C09, L0186]
  - objection: alternative_not_ruled_out: H-B (a non-flag-gated recompute job starting near 15:00) fits the same CPU, error and latency step and the same WARN signature. The ledger has no evidence that  [C09, M21, M23, L0186, L0313]

## Ranked hypotheses
1. **inventory-service** - config_error (confidence 0.45)
   - Mechanism: Feature flag C09 raised realtime_stock_recalc from 5% to 100% of traffic at 14:55:00Z, which plausibly routes live requests through StockRecalculator.recomputeAll over 48211 SKUs. That work saturates inventory-service CPU (29% to 98%), pushes requests past the 2000 ms deadline (WARNs from 15:00:06Z), and raises p99 latency and errors, with checkout slowing through its synchronous calls.
   - Supporting evidence: `C09, L0186, L0313, M21, M22, M23, M13, D05`
   - Contradicting evidence: `L0168, L0175, L0184`
   - Assumptions: The flag gates the StockRecalculator.recomputeAll path, which is unverified because the flag history and past-incident checks were not returned; Onset lies between 14:55 and 15:00 at 5-minute resolution, so the flag change plausibly precedes it; Log and metric timestamps share one clock
2. **inventory-service** - resource_exhaustion (confidence 0.25)
   - Mechanism: A compute-heavy StockRecalculator.recomputeAll job over 48211 SKUs that is not flag-gated (scheduled or triggered by data change) starts near 15:00 and saturates CPU, producing the deadline WARNs, error step and latency step. The 14:55 flag change would then be a coincident event rather than the cause.
   - Supporting evidence: `L0186, M21, M22, M23, M25`
   - Contradicting evidence: `C09`
   - Assumptions: A non-flag trigger exists that is absent from the change history; The recompute job and sku_count=48211 identify the saturating workload; The flag does not gate the recompute path
3. **inventory-db** - dependency_failure (confidence 0.08)
   - Mechanism: Database CPU roughly doubled at 15:00 (about 30% to 60-64%), plausibly from recompute queries, which could slow inventory-service calls. Query p99 stayed flat, so the database is at most a secondary effect of the same workload rather than an independent origin.
   - Supporting evidence: `M17`
   - Contradicting evidence: `M19, M16, M20, M18`
   - Assumptions: The CPU rise reflects the same recompute workload; Shallow health checks say nothing about latency

## Observed facts
- inventory-service latency_p99_ms was about 87-93 ms through 14:55, then 2311 ms at 15:00 and 2436 ms at 15:30. `M23`
- inventory-service error_rate was about 0.17-0.22% through 14:55, then 9.33% at 15:00 and 9.56% at 15:30; cpu_pct was about 29-31% through 14:55, then 98.43% at 15:00 and 95.08% at 15:30. `M22, M21`
- Feature flag change C09 by p.nguyen at 14:55:00Z set realtime_stock_recalc to 100% of inventory-service traffic (previously 5%); no rollback is recorded and it is the only inventory-service change in 12:00-15:30. `C09`
- From 15:00:06Z to 15:30:00Z, 30 WARN lines report a request exceeding its 2000 ms deadline in StockRecalculator.recomputeAll (sku_count=48211); no recompute job-start or scheduler line was found. `L0186, L0313`
- Request rate and memory stayed flat across the 15:00 step (request rate about 135-145 req/s; memory about 48-50%). `M25, M24`
- checkout-service latency_p99_ms rose from about 310 ms to about 2513 ms at 15:00, while its request rate, error rate and CPU stayed flat. `M13, M15, M12, M11`
- inventory-db query_latency_p99_ms stayed about 9 ms throughout, while inventory-db cpu_pct rose from about 30% to about 60-64% at 15:00; connections, disk and replication lag were unchanged. `M19, M17, M16, M18, M20`
- Two INFO stock lookups were slow before the step: 306 ms at 14:55:06 and 170 ms at 14:57:44. `L0168, L0175`
- Health checks at 15:28 reported inventory-service, inventory-db, inventory-cache and checkout-service healthy; the database check is SELECT 1 only and the cache check is HTTP /health only. `H07, H06, H05, H03`

## Assumptions
- The realtime_stock_recalc flag gates the StockRecalculator.recomputeAll code path; this is unverified because flag history was not retrieved.
- Metric and log timestamps share one clock, and the 5-minute metric resolution places onset between 14:55 and 15:00.
- A non-flag trigger for recomputeAll (scheduled or data-change driven) may exist but is absent from the recorded change history.
- The inventory-db CPU rise reflects the same recompute workload rather than an independent cause.
- Shallow health checks say nothing about latency on the slow path.
- (unverified - no valid evidence cited) Searches for realtime_stock_recalc and StockRecalculator in inventory-service logs for 14:50-15:00 returned zero lines.

## Inferred conclusions
- The inventory-service latency step is most likely associated with the StockRecalculator.recomputeAll workload starting near 15:00, which saturates CPU and causes deadline overruns; this is the leading candidate but is not established as the cause. (confidence 0.45) `L0186, M21, M22, M23`
- Flag change C09 is the leading candidate trigger, but it cannot be preferred over a non-flag-gated recompute job (H-B, confidence 0.25) on current data. (confidence 0.45) `C09, L0186, M21`
- The latency originates inside inventory-service rather than upstream: checkout request rate was flat and checkout is best treated as a downstream victim. (confidence 0.70) `M15, M13, M23`
- inventory-db is unlikely to be the primary origin given flat query latency and normal connections and replication; its CPU rise is unexplained and may be a downstream effect. (confidence 0.60) `M19, M16, M20, M17`
- The cache-miss storms before 14:20 do not align with the 15:00 onset and are unlikely to be the trigger. (confidence 0.40) `L0034, L0040, L0061`

## Remediation
- **immediate** - Roll back realtime_stock_recalc to 5% (or 0%) for inventory-service as a controlled test and observe p99, error rate and CPU. _(C09 is the only recorded change in the window, and rollback is both a reversible mitigation and the discriminating test between H-A and H-B.)_
- **immediate** - Check whether a scheduled or data-triggered StockRecalculator.recomputeAll job runs independently of the flag, and pause it if it is found to be running. _(Under H-B, the job alone could account for CPU saturation and deadline overruns, so it needs a check even if the flag is rolled back.)_
- **short_term** - Confirm the flag-to-code linkage and whether recomputeAll runs per request or on a schedule by reading flag configuration and code paths. _(This is the unverified link that decides between H-A and H-B and is needed before any causal claim.)_
- **short_term** - Add deeper health checks that exercise the recalculation path and report latency, and extend dependency latency telemetry for inventory-db and inventory-cache. _(Current shallow checks cannot detect slow-path degradation or rule out dependency latency.)_
- **long_term** - Add per-call timing and CPU attribution for the recompute job, and a deadline-aware circuit or bulkhead for synchronous calls from checkout. _(Attribution would settle causation and limit the blast radius of similar compute-heavy work on checkout.)_
- **long_term** - Require gradual ramps with latency and CPU guardrails for feature flags that enable compute-heavy paths. _(The 5% to 100% jump was made in a single change with no guardrail, which would have limited impact if the flag is causal.)_

## Open questions
- Does realtime_stock_recalc gate StockRecalculator.recomputeAll, and does recomputeAll run per request or on a schedule?
- Did the 5% ramp earlier in the flag history cause any latency, and do past incidents show recompute-induced latency?
- Is there a scheduler, job-start or data-change trigger for recomputeAll at about 15:00 that is not in the change history?
- What were the 306 ms and 170 ms lookups at 14:55 and 14:57, and do they indicate degradation starting before the 15:00 step?
- Why did inventory-db CPU double at 15:00 while query latency stayed flat, and does it come from the recompute workload?
- What do 1-minute metrics for 14:50-15:05 show about onset relative to 14:55:00Z?

## Data gaps and tool failures (10 shown, 41 reported)
- query_metrics(start=2026-09-09T14:00:00Z, end=2026-09-09T15:30:00Z, service=inventory-service) -> partial: PARTIAL RESULT: metrics shard unavailable; 2 of 5 records returned. 5 series
- No past-incident search was run in this pass. (reported 2x)
- No metrics were gathered for checkout-service or for inventory-service's downstream dependencies, so the checkout alert and any dependency contribution are not checked. (reported 2x)
- The 'change history' tool does not return infra events or config changes beyond C09, so I cannot confirm whether none occurred. The tool's results are only as complete as its source.
- Health checks are shallow (SELECT 1 and /health only). They do not exercise realtime recalc paths or measure latency, so they cannot rule out dependency latency.
- No latency or telemetry data was retrieved, so I have not confirmed that the p99 onset matches 14:55 rather than ~15:00.
- No p50 or p95 latency series was returned; only p99 is available, so the requested p50/p95 values could not be determined.
- No per-endpoint or per-route latency or error breakdown was available, so it is unknown whether the slowdown is uniform across endpoints.
- No GC metrics (pause time, frequency) and no thread-pool or connection-pool saturation metrics were returned for inventory-service. Those signals could not be checked.
- 30 further gap report(s) in 30 group(s) omitted here (mostly about: inventory-service, returned, latency, retrieved, metrics, error); the full list is in the run record.
