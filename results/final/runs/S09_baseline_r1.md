# Incident report S09

- **Status:** CONCLUSIVE (confidence 0.80, margin 0.55, 6 verified supporting and 2 contradicting evidence items (25%))
- **System:** baseline · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** agent_finished
- **Root cause:** `inventory-service` - config_error (confidence 0.80)

## Summary
Inventory-service p99 latency and errors jumped at 15:00 UTC, one minute after the realtime_stock_recalc feature flag was raised from 5% to 100% at 14:55 UTC. Inventory CPU went from about 30% to about 98%, and StockRecalculator.recomputeAll repeatedly exceeded its 2000ms deadline on a 48,211-SKU batch. Checkout p99 rose from about 320ms to about 2.5s as its calls to inventory slowed. Database metrics show only a moderate CPU rise and stable query latency, so the database does not appear to be the origin. The leading explanation is the flag change driving a full recalculation on every request, but I did not verify the flag's effect directly, and the inventory latency series was not returned.

## Conclusion decision
- confidence 0.80, margin 0.55, 6 verified supporting and 2 contradicting evidence items (25%)
- Criteria: top `inventory-service / config_error` confidence 0.80, margin 0.55, 6 verified supporting / 2 contradicting items (25% contradicting); 0 evidence-backed material critic objection(s), 0 non-blocking

## Ranked hypotheses
1. **inventory-service** - config_error (confidence 0.80)
   - Mechanism: Enabling realtime_stock_recalc for 100% of traffic at 14:55 made each request run StockRecalculator.recomputeAll over 48,211 SKUs. This saturated inventory CPU, pushed requests past their 2000ms deadline, and raised errors. Checkout, which calls inventory synchronously, then slowed.
   - Supporting evidence: `C09, M21, M22, L0186, L0254, M13`
   - Contradicting evidence: `M17, M19`
   - Assumptions: The flag controls the recompute path, based on the log message and the flag name.; Health checks are shallow and do not exercise this path.
2. **inventory-cache** - resource_exhaustion (confidence 0.25)
   - Mechanism: A cache capacity or eviction problem, as in the April incident, pushed reads to the database and raised inventory load. The cache miss storms from 14:09 may have worsened the CPU and latency once they combined with the recompute load.
   - Supporting evidence: `L0034, L0040, L0061, M17`
   - Contradicting evidence: `C09, M21`
   - Assumptions: The cache miss storms are related to the 15:00 step.; No inventory-cache metrics were returned.
3. **inventory-db** - dependency_failure (confidence 0.08)
   - Mechanism: A database slowdown in inventory-db would increase inventory latency and push checkout latency up.
   - Supporting evidence: `M17`
   - Contradicting evidence: `M19, M20, M16, H06`
   - Assumptions: The database metrics are complete for the incident window.

## Observed facts
- A feature_flag change on inventory-service at 14:55:00Z enabled realtime_stock_recalc for 100% of traffic, previously 5%, by p.nguyen (status completed). `C09`
- inventory-service cpu_pct was about 29-31% from 14:00 to 14:55, then 98.43% at 15:00, peaking at 99.94% at 15:05 and at 95.08% at 15:30. `M21`
- inventory-service error_rate was 0.16-0.25% until 14:55, then 9.33% at 15:00 and 9.56% at 15:30. `M22`
- Inventory-service logs show 30 WARN 'request exceeded deadline 2000ms in StockRecalculator.recomputeAll (sku_count=48211)' lines, first at 15:00:06Z and last at 15:17:11Z. `L0186, L0254`
- Checkout-service p99 latency was 309-332ms until 14:55, then 2513ms at 15:00 and 2666ms at 15:30. `M13`
- inventory-db cpu_pct rose from about 30% to about 60-64% at 15:00, while query_latency_p99_ms stayed at 8.7-9.3ms and replication_lag_s stayed at about 0.3s. `M17, M19, M20`
- inventory-db connections stayed at 86-93 throughout the window, with no step change at 15:00. `M16`
- Before the incident, inventory logs show cache miss storm warnings at 14:09:47, 14:11:57 and 14:19:19 (57-80 misses/s). `L0034, L0040, L0061`
- Health checks at 15:28 were all 'healthy' (HTTP 200 for inventory-service, checkout-service and inventory-cache; SELECT 1 ok for inventory-db), and checkout logged one payment-service retry at 15:11. `H03, H05, H06, H07, L0230`
- Inventory-service has 33 WARN lines in the window and no ERROR lines were returned. `L0186`

## Assumptions
- The realtime_stock_recalc flag is the mechanism that runs StockRecalculator.recomputeAll per request or per traffic unit; this is inferred from the log message and flag name, not from code.
- The health checks are shallow and do not exercise the recalculation path or latency under load.
- The alert figure of 2.4s for inventory-service p99 is accurate; no inventory-service latency_p99_ms series was returned.
- The 5-series metrics query for inventory-service was partial (2 of 5 series returned), so inventory-cache and request-rate data are missing.

## Inferred conclusions
- The realtime_stock_recalc flag raised to 100% at 14:55 is the most likely origin: the CPU and error step at 15:00, the recomputeAll deadline warnings, and the timing all fit. Checkout latency follows from its synchronous dependency on inventory. (confidence 0.80) `C09, M21, M22, L0186, M13`
- The database is probably not the origin: its query latency and replication lag are flat, and its CPU rise is moderate and consistent with extra read load from the recalculation. (confidence 0.60) `M17, M19, M20, M16`
- The pre-incident cache miss storms at 14:09-14:19 are a separate, earlier issue. They do not explain the 15:00 step, but they may have added load or cache pressure. (confidence 0.30) `L0034, L0040, L0061`

## Remediation
- **immediate** - Roll back realtime_stock_recalc to 5% or off (flag revert) for inventory-service. _(The step change started at the flag change and recomputeAll deadlines began right after it.)_
- **immediate** - Confirm recovery: inventory CPU back to about 30%, error rate under 0.3%, checkout p99 back under 320ms. _(Verifies the mitigation worked and that checkout recovered.)_
- **short_term** - Make the recalculation batch bounded or incremental (for example per SKU prefix), and load-test it at 48k SKUs before any ramp. _(A full-catalogue recompute per request is not viable at the current scale.)_
- **short_term** - Ramp future flags gradually (5% → 25% → 100%) with an automatic rollback on CPU, error rate or latency thresholds. _(The 5% to 100% jump removed any chance to catch the regression early.)_
- **long_term** - Make health checks exercise the recalculation path and report latency, not just HTTP 200. _(All health checks were green during a P2 latency incident.)_
- **long_term** - Investigate the 14:09-14:19 cache miss storms and add a cache eviction alert, as in the April incident. _(A similar past incident (cache eviction storm) suggests the cache sizing risk is still present.)_

## Open questions
- Does the realtime_stock_recalc code path actually call StockRecalculator.recomputeAll per request? This needs code or trace confirmation.
- What is the inventory-service p99 latency series itself, and did it reach 2.4s? The metrics query was partial.
- Why did the cache miss storms occur at 14:09-14:19, before the flag change, and do they still affect the current incident?
- Is the 15:00 checkout slowdown entirely due to inventory latency, or did payment retries also contribute?

## Data gaps and tool failures (1 shown, 1 reported)
- query_metrics(start=2026-09-09T14:00:00Z, end=2026-09-09T15:30:00Z, service=inventory-service) -> partial: PARTIAL RESULT: metrics shard unavailable; 2 of 5 records returned. 5 series
