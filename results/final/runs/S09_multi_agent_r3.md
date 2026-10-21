# Incident report S09

- **Status:** CONCLUSIVE (confidence 0.55, margin 0.25, 7 verified supporting and 1 contradicting evidence items (12%))
- **System:** multi_agent · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** max_rounds_reached
- **Root cause:** `inventory-service` - config_error (confidence 0.55)

## Summary
System determination is CONCLUSIVE at confidence 0.55 with margin 0.25 over the runner-up, 7 verified supporting and 1 contradicting evidence item (12%). The leading hypothesis is that the realtime_stock_recalc flag raised to 100% at 14:55Z drove StockRecalculator.recomputeAll saturation of inventory-service, producing the 15:00Z p99 step, CPU jump and error rate rise. Inventory p99 rose from about 90 ms to about 2.3-2.5 s, CPU from about 30% to about 98%, and error rate from about 0.2% to about 9%, with flat request rate. Checkout-service latency tracked inventory while its own resources and traffic stayed flat, so it appears to be a downstream victim. A co-cause candidate remains open: inventory-db CPU stepped at 15:00Z with 1900 ms stock_levels queries logged from 15:00:05Z, one second before the first recomputeAll breach, and the db p99 metric conflicts with those logs. The flag-to-code-path link is assumed rather than evidenced, and the 5-minute resolution limits ordering, so the cause should be treated as a leading lead with an unresolved db co-cause question.

## Conclusion decision
- confidence 0.55, margin 0.25, 7 verified supporting and 1 contradicting evidence items (12%)
- Criteria: top `inventory-service / config_error` confidence 0.55, margin 0.25, 7 verified supporting / 1 contradicting items (12% contradicting); 1 evidence-backed material critic objection(s), 5 non-blocking
  - objection: unsupported_claim: The claim that the flag gates the recomputeAll request-path code is not evidenced in the ledger; C09 only records a percentage change. Without this link, the fl [C09, L0186]

## Ranked hypotheses
1. **inventory-service** - config_error (confidence 0.55)
   - Mechanism: Feature flag realtime_stock_recalc was raised from 5% to 100% at 14:55Z, which plausibly routes all requests through StockRecalculator.recomputeAll over 48211 SKUs. This saturates inventory-service CPU (98-99%) and pushes requests past the 2000ms deadline, producing the p99 step to about 2.3-2.5s and the error rate near 9%.
   - Supporting evidence: `C09, M23, M21, M22, L0186, L0190, L0313, M25, M15`
   - Contradicting evidence: `M19`
   - Assumptions: The flag gates the recomputeAll code path in the request path; this is not shown in the ledger; No other relevant change occurred in the window; Five-minute sampling leaves the flag-to-onset gap uncertain
2. **inventory-db** - dependency_failure (confidence 0.30)
   - Mechanism: An unfiltered SELECT sku, qty FROM stock_levels workload from about 15:00Z raises inventory-db CPU from about 30% to 60%+ and produces 1900ms queries. Inventory-service requests waiting on the database combine with other work to exceed deadlines, which raises p99 and errors. It may be a co-trigger with H1 rather than an alternative to it.
   - Supporting evidence: `M17, L0185, L0204, L0205, L0312, L0030, L0101`
   - Contradicting evidence: `M19, M16, M20, H06`
   - Assumptions: The 1900ms slow-query logs reflect real query latency and query_latency_p99_ms measures a different path; The database load is independent of recomputeAll rather than a consequence of it; The 15:00:05Z slow query precedes the 15:00:06Z deadline breach at sampling resolution
3. **inventory-service** - other (confidence 0.08)
   - Mechanism: An unidentified scheduled job or trigger outside the change history starts recomputeAll at about 15:00Z. The resulting full-catalogue recomputation saturates inventory-service CPU and causes deadline breaches, independent of the flag change.
   - Supporting evidence: `L0186, M21`
   - Contradicting evidence: `C09, M22`
   - Assumptions: A non-recorded trigger explains recomputeAll starting at 15:00Z; The scheduled-job check was not run, so this reflects absence of data

## Observed facts
- inventory-service latency_p99_ms was about 87-93 ms through 14:55Z, then stepped to 2311 ms at 15:00:00Z and stayed about 2.3-2.5 s through 15:30Z. `M23`
- inventory-service cpu_pct was about 29-31% before 15:00Z, reached 98.43% at 15:00Z, peaked at 99.94% at 15:05Z and was 95.08% at 15:30Z; error_rate rose from about 0.2% to 9.33% at 15:00Z. `M21, M22`
- inventory-service and checkout-service request rates stayed flat across the window (about 135-145 and 82-88 req/s), with no spike at 15:00Z. `M25, M15`
- checkout-service latency_p99_ms stepped from about 310 ms to 2513 ms at 15:00:00Z, while its cpu_pct, memory_pct and error_rate showed no step. `M13, M11, M14, M12`
- Change C09 at 14:55:00Z raised feature flag realtime_stock_recalc from 5% to 100% of inventory-service traffic; no other change was recorded for inventory-service, inventory-db or checkout-service between 14:00 and 15:30Z. `C09`
- Thirty inventory-service WARNs 'request exceeded deadline 2000ms in StockRecalculator.recomputeAll (sku_count=48211)' appear from 15:00:06Z, recurring roughly every 1-2 minutes through 15:30Z; no inventory ERROR logs were returned. `L0186, L0190, L0313`
- inventory-db cpu_pct stepped from about 30% to 60.56% at 15:00Z and stayed about 62-64% through 15:30Z. `M17`
- inventory-db logged 'slow query 1900ms: SELECT sku, qty FROM stock_levels' from 15:00:05Z, about every 4 minutes, versus two earlier slow queries of 1010 ms and 1180 ms that had a WHERE warehouse_id clause. `L0185, L0204, L0312, L0030, L0101`
- inventory-db query_latency_p99_ms stayed flat at about 8.7-9.3 ms across the window, conflicting with the 1900 ms slow-query logs; connections, replication lag and disk were flat. `M19, M16, M20, M18`
- Dependency health checks at 15:28Z all returned healthy; these checks are shallow (HTTP /health or SELECT 1) and do not measure latency. `H03, H05, H06, H07`

## Assumptions
- The realtime_stock_recalc flag gates the recomputeAll code path in the request path; the ledger records only the percentage change.
- No other relevant change or scheduled job occurred in the window; scheduler and job data were not retrieved.
- The 1900 ms slow-query log entries reflect real query latency, and query_latency_p99_ms measures a different query path.
- Five-minute metric sampling is adequate to order onset, so the db slow query and the service breach are treated as simultaneous at this resolution.
- Shallow health checks at 15:28Z (after onset) are taken as indicating no hard outage, not as evidence about latency.

## Inferred conclusions
- The flag change realtime_stock_recalc to 100% at 14:55Z is the leading candidate cause of the inventory-service latency and CPU step via StockRecalculator.recomputeAll; the mechanism is not verified. (confidence 0.55) `C09, L0186, M23, M21`
- Inventory-db stock_levels scans may be a co-cause rather than only a consequence, because they begin one second before the first service deadline breach; this cannot be settled at current resolution. (confidence 0.30) `L0185, L0186, M17`
- Checkout-service latency is most likely a downstream effect of its synchronous calls to inventory-service, not an independent origin. (confidence 0.70) `D05, M13, M11, M15`
- Traffic volume does not explain the event; the change is a compute or CPU change rather than a load surge. (confidence 0.80) `M25, M15, M24`
- A non-flag scheduled trigger starting recomputeAll at about 15:00Z is possible but unsupported, because no job data was retrieved. (confidence 0.08) `L0186`
- The pre-onset cache-miss storms and checkout card-decline errors are probably unrelated background noise, since they predate the step and do not coincide with it. (confidence 0.40) `L0034, L0040, L0061, L0005`

## Remediation
- **immediate** - Roll back realtime_stock_recalc from 100% to the previous 5% (or 0%) to test whether recomputeAll latency and inventory CPU recover. _(C09 is the only change near onset and is reversible; rollback is a low-risk test of the leading hypothesis and a mitigation if it holds.)_
- **immediate** - Monitor inventory-db CPU and stock_levels slow-query rate after rollback to see whether the unfiltered SELECT load also falls. _(The db co-cause question can be partly answered by whether db load clears with the flag change.)_
- **immediate** - Shed or throttle checkout traffic to inventory-service if rollback does not restore latency, to protect checkout while the cause is confirmed. _(Inventory is saturated at 98-99% CPU with 9% errors and checkout is alerting; this is a containment measure, not a fix.)_
- **short_term** - Confirm whether realtime_stock_recalc gates the recomputeAll request-path code, using the flag configuration and code review. _(The flag-to-code-path link is the main unverified assumption behind the leading hypothesis.)_
- **short_term** - Reconcile the inventory-db query_latency_p99_ms metric with the 1900 ms slow-query logs and pull db-client latency for inventory-service. _(The metric conflict must be resolved before the db co-cause can be ruled in or out.)_
- **short_term** - Retrieve 1-minute resolution metrics and logs for 14:50-15:10Z to determine which side moved first. _(The current 5-minute samples cannot order the db slow query against the service deadline breach.)_
- **long_term** - Add query-level or stock_levels-scan guards and make recomputeAll run off the request path or in batch, with deadline-aware fallback. _(Prevents a full-catalogue recompute of 48211 SKUs from saturating CPU and database in the request path.)_
- **long_term** - Add pre-release load testing and alerting for flag changes affecting recompute paths, with per-instance and cache metrics. _(The incident would have been caught by a staged rollout and latency guardrails; current data lacked per-instance and cache visibility.)_

## Open questions
- Does realtime_stock_recalc gate the recomputeAll path, and does latency fall when it is rolled back to 5%?
- Did the inventory-db stock_levels slow queries start before, at, or after the first service deadline breach at 1-minute or finer resolution?
- Why does inventory-db query_latency_p99_ms stay flat while 1900 ms slow queries are logged?
- Was any scheduled job or trigger independent of the flag starting recomputeAll or full stock_levels scans near 15:00Z?
- What are inventory-service p50, per-instance p99 and inventory-cache metrics for 14:55-15:05Z, and are they uniform across instances?

## Data gaps and tool failures (10 shown, 44 reported)
- query_metrics(start=2026-09-09T14:00:00Z, end=2026-09-09T15:30:00Z, service=inventory-service) -> partial: PARTIAL RESULT: metrics shard unavailable; 2 of 5 records returned. 5 series
- inventory-service WARN/ERROR logs for 14:50-15:10Z, including any deadline-breach or recomputeAll messages: not retrieved (tool call rejected). (reported 2x)
- Only 2 of 5 inventory-service metrics came back on the first query (metrics shard unavailable). cpu_pct and error_rate were obtained; latency_p99_ms and request_rate came from separate retries.
- Inventory p50 latency was not retrieved, and checkout p50 was not retrieved at all, so the p50 crossing time is unknown.
- No per-endpoint, per-instance or per-region breakdown was obtained. The uniformity question is unanswered.
- Inventory memory, disk and downstream dependency metrics were not queried.
- Checkout's p99 is inferred to track inventory, but checkout's own downstream calls were not checked directly.
- No change-history or deploy data was queried, so the trigger for recomputeAll starting at 15:00Z is unknown.
- The first-crossing time is judged from 5-minute samples: the first breached sample is 15:00:00Z, and the true crossing could be up to 5 minutes earlier.
- 34 further gap report(s) in 34 group(s) omitted here (mostly about: inventory-service, latency, inventory-db, checked, queried, query); the full list is in the run record.
