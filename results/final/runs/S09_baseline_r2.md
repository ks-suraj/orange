# Incident report S09

- **Status:** CONCLUSIVE (confidence 0.80, margin 0.65, 6 verified supporting and 3 contradicting evidence items (33%))
- **System:** baseline · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** agent_finished
- **Root cause:** `inventory-service` - config_error (confidence 0.80)

## Summary
Inventory-service p99 latency jumped from about 90ms to about 2.3-2.5s and its error rate from about 0.2% to about 9% starting in the 15:00 UTC window. This coincides with the 14:55 UTC feature-flag change that enabled realtime_stock_recalc for 100% of traffic, up from 5%. The logs show StockRecalculator.recomputeAll exceeding its 2000ms deadline on a 48,211-SKU recompute, and inventory CPU rose from about 30% to about 95-100%. Checkout p99 rose in step, so the slowdown propagates through the sync call from checkout to inventory. The leading explanation is the flag ramp; the cache and database data are incomplete, and the health checks are shallow.

## Conclusion decision
- confidence 0.80, margin 0.65, 6 verified supporting and 3 contradicting evidence items (33%)
- Criteria: top `inventory-service / config_error` confidence 0.80, margin 0.65, 6 verified supporting / 3 contradicting items (33% contradicting); 0 evidence-backed material critic objection(s), 0 non-blocking

## Ranked hypotheses
1. **inventory-service** - config_error (confidence 0.80)
   - Mechanism: Enabling realtime_stock_recalc for all traffic runs StockRecalculator.recomputeAll on the full 48,211-SKU catalogue on the request path. This saturates inventory CPU, pushes requests past the 2s deadline, and raises p99 latency and errors, which checkout then inherits through its sync call.
   - Supporting evidence: `C09, M21, L0186, M23, M22, M13`
   - Contradicting evidence: `L0034, L0040, L0061`
   - Assumptions: The recompute is triggered by the flag on the request path.; The onset timing is accurate to the 5-minute resolution.
2. **inventory-cache** - resource_exhaustion (confidence 0.15)
   - Mechanism: A cache problem (eviction or miss storm) forces inventory-service to hit the database or recompute more often, creating CPU and latency pressure. The cache miss storms began at 14:09, earlier than the onset.
   - Supporting evidence: `L0034, L0040, L0061, P03`
   - Contradicting evidence: `M21, M23, C09`
   - Assumptions: Cache metrics are unavailable, so the cache state during the incident is unknown.
3. **inventory-db** - resource_exhaustion (confidence 0.05)
   - Mechanism: Database load rose and drove inventory-service slowness.
   - Supporting evidence: `M17`
   - Contradicting evidence: `M19, M20, M16`
   - Assumptions: The database CPU rise is the cause rather than a symptom.

## Observed facts
- The feature flag change C09 (realtime_stock_recalc enabled for 100% of traffic, previously 5%, by p.nguyen, completed) was recorded at 2026-09-09T14:55:00Z on inventory-service. `C09`
- inventory-service cpu_pct was about 29-31% from 14:00 to 14:55 and jumped to 98.43% at 15:00:00, peaking at 99.94% at 15:05:00 and at 95.08% at 15:30:00. `M21`
- inventory-service p99 latency was about 87-93ms until 14:55 and was 2311.39ms at 15:00:00, reaching 2478.31ms at 15:15:00 and 2436.03ms at 15:30:00. `M23`
- inventory-service error_rate was 0.16-0.25% until 14:55 and was 9.33% at 15:00:00, ending at 9.56% at 15:30:00. `M22`
- From 15:00:06 onward, inventory-service logged 'request exceeded deadline 2000ms in StockRecalculator.recomputeAll (sku_count=48211)' repeatedly, about every 1-2 minutes; 30 such warnings appear in the 14:00-15:30 window. `L0186, L0190, L0192, L0198, L0254`
- Three 'cache miss storm' warnings (57, 62 and 80 misses/s) were logged between 14:09:47 and 14:19:19, before the flag change. `L0034, L0040, L0061`
- inventory-db query_latency_p99_ms stayed about 8.7-9.3ms and replication_lag_s about 0.3s throughout; inventory-db cpu_pct rose from about 30% to about 60-64% starting 15:00, and connections stayed 86-93. `M19, M20, M17, M16`
- checkout-service latency_p99_ms was about 309-332ms until 14:55 and was 2512.95ms at 15:00:00, reaching 2699.31ms at 15:05:00. `M13`
- The only checkout-service WARN in 14:50-15:30 is one retry of an idempotent call to payment-service at 15:11:00. `L0230`
- Health checks at 15:28 reported inventory-service, inventory-db, inventory-cache and checkout-service as healthy; the inventory-db check is 'SELECT 1 ok'. `H07, H06, H05, H03`

## Assumptions
- The health checks are shallow (HTTP /health 200 or SELECT 1) and do not exercise the recompute path, so 'healthy' does not contradict the outage.
- Metrics are 5-minute resolution, so the onset falls between 14:55 and 15:00 and cannot be ordered more finely than that.
- The 48,211-SKU recompute is triggered by the enabled flag for all traffic, not by a separate job.
- No inventory-cache metrics are available, so cache health during the incident is unknown.

## Inferred conclusions
- The realtime_stock_recalc flag ramp from 5% to 100% most likely caused the CPU saturation and the StockRecalculator deadline failures, which in turn produced the inventory latency and error spike. (confidence 0.80) `C09, M21, L0186, M23, M22`
- Checkout latency is a downstream effect: checkout's sync HTTP dependency on inventory-service is slow, and checkout's own logs show no fault of its own. (confidence 0.70) `M13, M23, L0230`
- The inventory-db is not the bottleneck: its query latency and replication lag are flat, and its CPU rise is consistent with the extra recompute load. (confidence 0.60) `M19, M20, M17`
- The earlier cache miss storms at 14:09-14:19 are a separate, pre-existing issue. They resolved without a visible latency impact and do not explain the 15:00 onset, though a cache problem is a weaker alternative. (confidence 0.35) `L0034, L0040, L0061`

## Remediation
- **immediate** - Roll back realtime_stock_recalc to 5% (or 0%) for inventory-service now. _(The flag change at 14:55 precedes the onset at 15:00 and matches the CPU saturation and recompute deadlines; reverting it is the fastest mitigation.)_
- **immediate** - Confirm recovery of inventory p99, error rate and checkout p99 after the rollback. _(Verifies the hypothesis and tells whether checkout is recovering.)_
- **short_term** - Make recomputeAll incremental or bounded (batch, cap sku_count per request) before re-enabling the flag. _(A full 48k-SKU recompute per request exceeds the 2s deadline and saturates CPU.)_
- **short_term** - Ramp the flag gradually with a canary and CPU/latency guardrails, and add an automatic rollback on error rate. _(The jump from 5% to 100% in one change removed any safe margin.)_
- **long_term** - Add deep health checks that exercise the recompute path and the cache. _(The current checks reported healthy during a 9% error rate.)_
- **long_term** - Add inventory-cache metrics and a cache-miss-storm alert, and review the 14:09-14:19 miss storms. _(Cache telemetry is missing, and the earlier storms were not investigated (see P03 for a past cache eviction incident).)_

## Open questions
- Why did the cache miss storms occur at 14:09-14:19, and is there a pending cache issue that could recur?
- Does the incident clear once the flag is rolled back, and how quickly?
- Was the flag change intended to ramp traffic in a single step, and was a load test done for the 48k-SKU recompute?
- Why are inventory-cache metrics absent from the metrics store?
- Did the inventory-service metrics shard outage (partial result: 2 of 5 series returned, retry not performed) hide any other series such as memory or other latency signals?

## Data gaps and tool failures (1 shown, 1 reported)
- query_metrics(start=2026-09-09T14:00:00Z, end=2026-09-09T15:30:00Z, service=inventory-service) -> partial: PARTIAL RESULT: metrics shard unavailable; 2 of 5 records returned. 5 series
