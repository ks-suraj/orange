# Incident report S09

- **Status:** INCONCLUSIVE (contradicting evidence is 85% of the weighed evidence (max 35%))
- **System:** multi_agent · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** tool_budget_exhausted

## Summary
Inventory-service p99 latency rose from about 90 ms to about 2.3 s and its error rate from about 0.2% to about 9% at the 15:00 UTC sample, with CPU jumping from 29% to 98%. Repeated 'exceeded deadline 2000ms in StockRecalculator.recomputeAll (sku_count=48211)' warnings begin at 15:00:06Z. The only pre-onset change is feature flag C09 (realtime_stock_recalc raised from 5% to 100%) at 14:55:00Z, but the link from that flag to recomputeAll was never verified and the 5-minute telemetry cannot order it against the first warning. The system determination is inconclusive: the leading hypothesis H1 has confidence 0.50, its margin over H2 (0.30) is limited, and 85% of weighed evidence is contradicting, above the 35% limit. No root cause is asserted; the flag rollout and an internal recomputeAll trigger remain the leading candidates. Checkout's latency step matches inventory's, but checkout error rate and logs are unchanged, so the propagation path is unexplained.

## Conclusion decision
- contradicting evidence is 85% of the weighed evidence (max 35%)
- Criteria: top `inventory-service / deployment_regression` confidence 0.50, margin 0.20, 2 verified supporting / 11 contradicting items (85% contradicting); 3 evidence-backed material critic objection(s), 4 non-blocking
  - objection: unsupported_claim: H1 asserts that realtime_stock_recalc gates the recomputeAll path, but no ledger record or tool output shows this; T5 explicitly failed to confirm it. Supportin [C09, L0186]
  - objection: alternative_not_ruled_out: H2 (an internal or scheduled recomputeAll unrelated to the flag) explains the same 15:00 step, the same CPU saturation and the same deadline WARNs. No ledger ev [C09, L0186, M21, M23]
  - objection: ignored_contradiction: Checkout p99 rose from about 310 ms to 2.5 s with a step matching inventory, yet checkout error rate stayed at 0.3% and checkout logs show no inventory-related  [M13, M12, M22, L0039, L0112]

## Ranked hypotheses
1. **inventory-service** - deployment_regression (confidence 0.50)
   - Mechanism: Feature flag C09 raised realtime_stock_recalc from 5% to 100% of inventory traffic at 14:55:00Z, five minutes before the 15:00 step. The StockRecalculator.recomputeAll path over 48,211 SKUs then saturates inventory CPU (29% to 98%), pushing p99 past the 2s deadline and producing the roughly 9% error rate, with checkout slowing because it calls inventory synchronously.
   - Supporting evidence: `C09, M21, M23, M22, L0186, L0313, D05`
   - Contradicting evidence: `M24, M25`
   - Assumptions: The flag change took effect at 14:55 and not later within the 5-minute bucket; realtime_stock_recalc gates the recomputeAll path (not verified); No other inventory change exists outside the recorded change history
2. **inventory-service** - resource_exhaustion (confidence 0.30)
   - Mechanism: A recomputeAll job over 48,211 SKUs runs internally, independent of the flag, and begins near 15:00, saturating CPU and pushing latency and errors past the deadline. Checkout slows because it waits on inventory.
   - Supporting evidence: `M21, M23, L0186, L0313, M22, M25`
   - Contradicting evidence: `C09`
   - Assumptions: The recomputeAll trigger is internal (scheduled or batch) and not caused by C09; Dependency latency is clean, though it was not measured; The 14:50-14:55 absence of recomputeAll warnings reflects no prior runs rather than a logging gap
3. **inventory-db** - dependency_failure (confidence 0.10)
   - Mechanism: Degraded database work could slow inventory-service calls, raising its CPU through retries or waiting and producing the same deadline overruns. Database CPU rose from about 30% to 60% at 15:00.
   - Supporting evidence: `M17, C09`
   - Contradicting evidence: `M19, M20, M16, L0186`
   - Assumptions: Client-side outbound latency to inventory-db would show the cause if retrieved; The database CPU rise is a cause rather than a consequence of heavier load

## Observed facts
- Inventory-service p99 latency was about 87-93 ms from 14:00 to 14:55 and 2311 ms at 15:00, staying between about 2325 and 2478 ms through 15:30. `M23`
- Inventory-service CPU rose from 29.21% at 14:55 to 98.43% at 15:00, peaked at 99.94% at 15:05, and stayed at 95-100% through 15:30, while memory and request rate stayed flat. `M21, M24, M25`
- Inventory-service error rate was about 0.2% before 15:00, then 9.33% at 15:00 and 8.68-9.56% through 15:30. `M22`
- Checkout-service p99 latency rose from about 310-332 ms to 2513 ms at 15:00, peaking at 2699 ms at 15:05, while checkout error rate stayed at 0.26-0.35% and checkout has no WARN/ERROR lines in the window. `M13, M12, L0039, L0112`
- Feature flag C09 enabling realtime_stock_recalc for 100% of inventory-service traffic (previously 5%) was completed at 14:55:00Z by p.nguyen; it is the only change in the 14:00-15:30 window across services. `C09`
- The first recomputeAll deadline WARN is at 15:00:06Z, and 30 such WARNs recur roughly every 1-1.5 minutes through 15:30:00Z, all reporting sku_count=48211. `L0186, L0313`
- No recomputeAll INFO/DEBUG start lines, caller, trigger field, or flag-evaluation log lines were found, and no recomputeAll invocation counter was available. `L0186, L0225`
- Inventory-db query p99 latency and replication lag stayed flat across the window, and connections stayed between 88 and 93; inventory-db CPU rose from 29.6% to 60.6% at 15:00. `M19, M20, M16, M17`
- Earlier cache-miss storm warnings (14:09, 14:11, 14:19) and checkout slow-reservation warnings (1200 ms at 14:11, 1362 ms at 14:36) occurred while inventory latency was normal. `L0034, L0040, L0061, L0039, L0112`
- Shallow health checks at 15:28Z reported checkout, inventory-service, inventory-cache and inventory-db as healthy; no inventory-cache metrics were returned. `H03, H07, H05, H06`

## Assumptions
- The flag change C09 took effect at 14:55:00Z and not later within the 5-minute telemetry bucket.
- realtime_stock_recalc gates the StockRecalculator.recomputeAll path; this was not verified by any tool output.
- No inventory change exists outside the recorded change history, which was queried by service only for part of the window.
- Health checks are shallow and do not exercise the recalculation path or p99 latency.
- Checkout depends synchronously on inventory-service, as the dependency graph records, and the checkout latency step is a consequence of inventory latency.

## Inferred conclusions
- An internal recomputeAll workload on inventory-service beginning at about 15:00 UTC is the best-supported origin of the CPU saturation, latency and error rise, with the flag rollout as the leading candidate trigger but not established. (confidence 0.50) `L0186, M21, M23, C09`
- Whether the C09 flag rollout or an independent internal recomputeAll trigger caused the first run cannot be separated with current data, because telemetry resolution is 5 minutes and the flag-to-recomputeAll link is unverified. (confidence 0.60) `C09, L0186, M21`
- Database-side degradation is unlikely to be the primary cause, since query latency, replication lag and connections are flat, although its CPU rise is unexplained and client-side outbound latency was not measured. (confidence 0.25) `M19, M20, M16, M17`
- Checkout's latency step is probably downstream of inventory latency, but the mechanism by which inventory's 9% errors fail to appear as checkout errors is unexplained. (confidence 0.40) `M13, M12, M22`
- The 14:09-14:19 cache-miss storms and earlier slow reservations are a separate precursor and do not explain the 15:00 step. (confidence 0.35) `L0034, L0040, L0061, M23`

## Remediation
- **immediate** - Consider reverting or reducing feature flag realtime_stock_recalc to 5% on inventory-service as a safe mitigation, since C09 is the only pre-onset change, and observe whether CPU and p99 recover. _(C09 is a low-cost reversible action that tests the leading hypothesis without requiring the unverified gating link to be known.)_
- **immediate** - Add checkout-side protection such as a short timeout or fallback on inventory calls, so checkout latency is bounded while inventory is degraded. _(Checkout p99 rose to about 2.5 s from inventory's deadline overruns and the mitigation limits user-facing slowness.)_
- **short_term** - Verify whether realtime_stock_recalc gates StockRecalculator.recomputeAll and identify the trigger (scheduled, batch, or per request) for each run. _(This single fact would separate H1 from H2, which the current evidence cannot do.)_
- **short_term** - Obtain sub-5-minute resolution for inventory CPU and latency, and per-endpoint latency, around 14:55-15:00 to order the flag change against the first WARN. _(The 5-minute resolution cannot order the change against the first deadline WARN at 15:00:06Z.)_
- **short_term** - Collect outbound client-side latency from inventory-service to inventory-db and inventory-cache, and checkout's outbound call metrics and logs. _(These gaps prevent ruling the dependency path in or out and explain why inventory errors do not appear in checkout.)_
- **long_term** - Add invocation counters and start/end logging for StockRecalculator.recomputeAll with caller and trigger fields. _(Missing caller and trigger fields prevented attribution of each run and of the flag interaction.)_
- **long_term** - Add deep health checks and p50 latency metrics that exercise the recalculation path and report per-endpoint latency. _(Current shallow health checks report healthy during degradation, so they cannot detect this class of regression.)_
- **long_term** - Bound recomputeAll work per request or move it to an asynchronous or batched job, and gate rollouts of new recalculation paths behind staged increases with latency guardrails. _(A full 48,211-SKU recalculation on the request path would saturate CPU whichever trigger starts it.)_

## Open questions
- Does realtime_stock_recalc gate StockRecalculator.recomputeAll, and what triggers each run?
- Did recomputeAll run before 14:55 on 2026-09-09 or on prior days, and does its invocation history separate it from the flag change?
- What is the outbound latency and error rate from inventory-service to inventory-db and inventory-cache during 14:50-15:10?
- Why do inventory's 9% errors not appear as checkout errors, and do checkout calls use a fallback on inventory failure?
- What were the flag changes before C09 between 2026-09-01 and 2026-09-09, since that history query failed?
- What is checkout's state after 15:11, since no checkout logs after that time were returned?

## Data gaps and tool failures (10 shown, 36 reported)
- query_metrics(start=2026-09-09T14:00:00Z, end=2026-09-09T15:30:00Z, service=inventory-service) -> partial: PARTIAL RESULT: metrics shard unavailable; 2 of 5 records returned. 5 series
- p50 latency was not returned for either service. Only p99 latency_p99_ms exists in the telemetry, so the p50 onset time could not be established.
- Logs carry no endpoint or route field. The affected endpoints could not be identified, and the endpoint-level breakdown is only inferred from the StockRecalculator.recomputeAll message.
- No timeout counter or timeout-specific metric was returned for either service. Timeouts can only be inferred from the 'exceeded deadline' log text.
- Telemetry is at 5-minute resolution, so the exact onset is bounded to the 14:55–15:00 interval, with the first log evidence at 15:00:06Z.
- Checkout's WARN/ERROR log set returned only 6 lines, all from the 14:00–15:11 window. No checkout logs after 15:11 were returned, so checkout's state for 15:11–15:30 is not visible at the log level.
- Health checks are shallow (HTTP /health or SELECT 1) and only one timestamp (15:28Z) is available; no latency-period health data.
- Change history for inventory-db and inventory-cache was not queried by service; the window query covered all services, so their absence is inferred, not directly confirmed.
- Upstream callers of checkout-service were not mapped; the graph only showed inventory-service edges.
- 27 further gap report(s) in 27 group(s) omitted here (mostly about: metrics, returned, latency, logs, lines, inventory-service); the full list is in the run record.
