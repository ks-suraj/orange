# Incident report S09

- **Status:** CONCLUSIVE (confidence 0.85, margin 0.75, 6 verified supporting and 1 contradicting evidence items (14%))
- **System:** baseline · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** agent_finished
- **Root cause:** `inventory-service` - config_error (confidence 0.85)

## Summary
Inventory-service p99 latency and errors jumped at 15:00 UTC, and checkout p99 followed (about 310ms to about 2.5s). The only change in the window is feature flag C09 at 14:55 UTC, which enabled realtime_stock_recalc for 100% of traffic (previously 5%). From 15:00 onward, inventory CPU went from about 30% to about 98% and the StockRecalculator.recomputeAll path ran over its 2000ms deadline on 48,211-SKU batches. The most likely cause is that the flag rollout saturated inventory-service CPU with full-catalogue recalculation. Health checks report green, which hides the problem. Request rate is flat, so this is not a traffic surge. Inventory-db shows only a modest CPU rise and no latency change, so the database is not the origin.

## Conclusion decision
- confidence 0.85, margin 0.75, 6 verified supporting and 1 contradicting evidence items (14%)
- Criteria: top `inventory-service / config_error` confidence 0.85, margin 0.75, 6 verified supporting / 1 contradicting items (14% contradicting); 0 evidence-backed material critic objection(s), 0 non-blocking

## Ranked hypotheses
1. **inventory-service** - config_error (confidence 0.85)
   - Mechanism: Feature flag realtime_stock_recalc was raised from 5% to 100% at 14:55Z. The full-catalogue StockRecalculator.recomputeAll (48,211 SKUs) then saturates inventory-service CPU, pushing requests past the 2000ms deadline, producing 9% errors, and driving checkout p99 to about 2.5s through sync HTTP calls.
   - Supporting evidence: `C09, M21, M22, L0186, L0254, M13`
   - Contradicting evidence: `H07`
   - Assumptions: The flag is the only change in the window.; Health checks are shallow and don't exercise recalc.
2. **inventory-db** - resource_exhaustion (confidence 0.10)
   - Mechanism: Increased query load from recalculation pushes inventory-db CPU up to about 60%, slowing inventory-service calls to the database.
   - Supporting evidence: `M17`
   - Contradicting evidence: `M19, M20`
   - Assumptions: DB CPU rise is caused by recalc queries, which were not directly observed.
3. **inventory-cache** - resource_exhaustion (confidence 0.05)
   - Mechanism: Cache miss storms (57–80 misses/s) reduce cache hit rate, forcing recomputation on the database and CPU.
   - Supporting evidence: `L0034, L0040, L0061`
   - Contradicting evidence: `M13`
   - Assumptions: The 14:09–14:19 storms are related to the 15:00 onset.

## Observed facts
- Inventory-service cpu_pct rose from about 29.2–30.6% (14:00–14:55) to 98.43% at 15:00 and stayed 95–100% through 15:30. `M21`
- Inventory-service error_rate rose from about 0.2% (14:00–14:55) to 9.33% at 15:00 and was 9.56% at 15:30. `M22`
- A feature_flag change by p.nguyen at 14:55:00Z enabled realtime_stock_recalc for 100% of traffic, previously 5%. `C09`
- From 15:00:06Z to 15:17:11Z, inventory-service logged repeated WARNs 'request exceeded deadline 2000ms in StockRecalculator.recomputeAll (sku_count=48211)', about one every 1–1.5 minutes. `L0186, L0190, L0254`
- Checkout-service latency_p99_ms rose from about 310–332ms (14:00–14:55) to 2512.95ms at 15:00 and 2666.13ms at 15:30; checkout error_rate and request_rate stayed flat. `M13, M12, M15`
- Inventory-db query_latency_p99_ms stayed about 9ms and replication_lag_s about 0.3s throughout; db cpu_pct rose from about 30% to about 60–64% starting at 15:00. `M19, M20, M17`
- Before onset, inventory-service logged cache miss storm warnings at 14:09:47, 14:11:57 and 14:19:19 (57–80 misses/s); no latency change followed in checkout. `L0034, L0040, L0061, M13`
- Health checks at 15:28Z report inventory-service, inventory-cache, inventory-db and checkout-service healthy (HTTP 200 or SELECT 1). `H07, H05, H06, H03`
- Checkout-service logs show only one WARN in 14:50–15:30 (payment-service retry at 15:11:00). `L0230`
- The inventory-service metrics query returned partial data (2 of 5 series; memory, request_rate and latency_p99 missing). `M21, M22`

## Assumptions
- The realtime_stock_recalc flag is the only change affecting inventory-service in the window; change history covers 12:00–15:30 and shows only C09.
- The 5-minute metric resolution means the flag change (14:55) and CPU onset (15:00) may differ by up to about 5 minutes; the exact onset is not resolved.
- Health checks are shallow and do not exercise the recalculation path, so their green status does not rule out this fault.
- Request rate for inventory-service is assumed flat because checkout request_rate is flat (inventory request_rate was not returned).

## Inferred conclusions
- Enabling realtime_stock_recalc for 100% of traffic caused full-catalogue StockRecalculator work (48,211 SKUs per request) to saturate inventory-service CPU, causing deadline overruns, 9% errors and about 2.5s p99 latency. (confidence 0.85) `C09, M21, L0186, M22`
- Checkout latency is a downstream effect of the slow sync_http calls to inventory-service, not an independent fault; checkout itself shows normal CPU, memory and error rate. (confidence 0.80) `M13, M11, M14, M12`
- Inventory-db is not the origin; its latency and replication stayed normal, and its CPU rise is consistent with the increased recalc query load. (confidence 0.60) `M19, M20, M17`

## Remediation
- **immediate** - Roll back or disable the realtime_stock_recalc feature flag, or set it back to 5% of traffic, to stop the recalculation load. _(The flag change at 14:55 precedes the CPU and latency onset at 15:00, and the recalc deadline overruns follow it.)_
- **immediate** - Verify that inventory-service CPU and p99 return to baseline (about 30% and under 300ms) and that checkout p99 recovers. _(Confirms the mitigation and clears the P2 alert.)_
- **short_term** - Make recalculation incremental or bounded by batch size instead of recomputing all 48k SKUs per request. _(The sku_count=48211 full recompute is the expensive path.)_
- **short_term** - Roll out feature flags progressively (5%→25%→100%) with CPU and latency guard checks. _(A 5% to 100% jump in one step removed the safety margin.)_
- **long_term** - Add a deep health check or SLO-based canary that exercises StockRecalculator. _(Current health checks stayed green during the outage.)_
- **long_term** - Review the cache miss storm alerting from 14:09–14:19 to see whether it is a separate issue. _(It preceded onset but had no visible impact, so it is probably unrelated.)_

## Open questions
- Did the onset happen exactly at 14:55 (flag) or at 15:00? The 5-minute resolution cannot resolve this.
- Why is inventory request_rate and latency_p99 not returned by the metrics shard (partial result)?
- Does the cache miss storm at 14:09–14:19 share a cause with the recalc feature?
- Was the 14:55 flag change applied to all inventory pods at once, or in a staged way?

## Data gaps and tool failures (1 shown, 1 reported)
- query_metrics(start=2026-09-09T14:00:00Z, end=2026-09-09T15:30:00Z, service=inventory-service) -> partial: PARTIAL RESULT: metrics shard unavailable; 2 of 5 records returned. 5 series
