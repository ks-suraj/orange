# Incident report S07

- **Status:** CONCLUSIVE (confidence 0.60, margin 0.25, 11 verified supporting and 4 contradicting evidence items (27%))
- **System:** multi_agent · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** tool_budget_exhausted
- **Root cause:** `checkout-service` - traffic_surge (confidence 0.60)

## Summary
Checkout-service p99 latency and 503s began at 18:00:00Z, coincident with a simultaneous roughly 4x request-rate step at checkout and api-gateway, and the system determination is CONCLUSIVE for H1 (traffic surge saturating checkout CPU and worker pool) at confidence 0.60. Checkout's 503s are its own 'worker pool saturated (queue 500/500)' rejections starting 18:03:25Z, after onset. Payment-service is flat throughout and inventory's step matches checkout's traffic rather than leading it. The HPA warning 'desired replicas 34 exceeds maxReplicas 20' supports H2 as a contributing capacity-ceiling factor, but replica counts and HPA history were not verified. The origin of the surge remains unresolved between the 17:55 marketing banner and 18:00 email blast (C10) and bot or retry traffic, because no client-level breakdown was obtained. Confidence is moderate, with missing pool metrics, database-tier data and sub-5-minute resolution as caveats.

## Conclusion decision
- confidence 0.60, margin 0.25, 11 verified supporting and 4 contradicting evidence items (27%)
- Criteria: top `checkout-service / traffic_surge` confidence 0.60, margin 0.25, 11 verified supporting / 4 contradicting items (27% contradicting); 0 evidence-backed material critic objection(s), 7 non-blocking

## Ranked hypotheses
1. **checkout-service** - traffic_surge (confidence 0.60)
   - Mechanism: A simultaneous ~4x request-rate step at 18:00:00 (checkout 85 to 353 req/s, gateway 417 to 1625 req/s) drove checkout CPU from ~40% to ~94-100%, so requests held workers longer and the worker queue filled (500/500), producing 503 rejections and p99 near 2.9s. Api-gateway and payment-service stayed flat, and inventory's step matches the traffic rather than leading it.
   - Supporting evidence: `M15, M05, M11, M13, M12, L0199, L0205, L0213, L0193, M25, M23`
   - Contradicting evidence: `M03, M02, M32, M34`
   - Assumptions: The 4x step is extra demand rather than a measurement artifact; Checkout capacity at the 20-replica cap cannot absorb ~330 req/s; Pool saturation is inferred from the log text only
2. **checkout-service** - config_error (confidence 0.35)
   - Mechanism: The HPA's maxReplicas of 20 (desired 34) capped scale-out, so checkout could not add capacity for the traffic step. The fault is the capacity ceiling, which turns a surge into sustained saturation and 503s rather than transient load.
   - Supporting evidence: `L0193, L0222, M11, M15, L0199`
   - Contradicting evidence: `L0192, L0195`
   - Assumptions: The cap of 20 was not sized for campaign-level traffic; Replica count and pool size were not verified
3. **api-gateway** - traffic_surge (confidence 0.25)
   - Mechanism: A bot or retry-driven surge originating at the gateway, concentrated in a few clients, produced the same 18:00 step in gateway and checkout request rates and saturated checkout in the same way as H1.
   - Supporting evidence: `M05, L0176, L0211, L0238, L0243`
   - Contradicting evidence: `C10`
   - Assumptions: Four rate-limited client IDs account for a large share of volume; No client-level breakdown was retrieved

## Observed facts
- checkout-service cpu_pct rose from about 40% to 93.7% at 18:00:00Z and stayed 94-100% through 18:30. `M11`
- checkout-service request_rate rose from about 85 to 352.97 req/s at 18:00:00Z and held about 328-345 req/s. `M15`
- checkout-service latency_p99_ms rose from about 320 ms to 2931 ms at 18:00:00Z, against an 800 ms SLO, and stayed near 2.8-3.0 s through 18:30. `M13`
- checkout-service error_rate rose from about 0.3% to 5.65% at 18:00:00Z and stayed 5.1-5.8%. `M12`
- api-gateway request_rate stepped from about 417 to 1625 req/s at 18:00:00Z, while its own p99, error rate, CPU and memory stayed flat. `M05, M03, M02, M01, M04`
- Checkout 503s are logged as 'rejecting request: worker pool saturated (queue 500/500) -> 503', first at 18:03:25Z, with recurrences through 18:28:35Z. `L0199, L0205, L0213, L0379`
- checkout-service logged 'HPA desired replicas 34 exceeds maxReplicas 20' at 18:02:34Z and 18:06:10Z. `L0193, L0222`
- payment-service latency, error rate, CPU and request rate stayed flat across 17:00-18:30 with no step at 18:00. `M32, M33, M34, M35, M36`
- inventory-service request_rate rose about 3.7x at 18:00:00Z and its p99 rose from about 91 to about 142-145 ms, with CPU and error rate unchanged. `M25, M23, M21, M22`
- Change C10 (api-gateway 'fall-sale' banner feature flag by marketing-ops) was enabled at 17:55:00Z ahead of a 2.1M-customer email blast at 18:00; change C09 (inventory-service v4.2.0) deployed at 17:25:00Z; no checkout-service change appears in the 7-day window except v2.13.4 on 2026-09-06T22:00Z. `C10, C09, C07`
- api-gateway rate limiter logged 'client near burst limit' for four client IDs between 17:57 and 18:09; no client-level volume breakdown was retrieved. `L0176, L0211, L0238, L0243`
- checkout-db metrics were unavailable and inventory-db and payments-db metrics show no latency or error rise at 18:00. `M19, M17, M40, M38`

## Assumptions
- The 4x request-rate step is additional demand rather than a measurement artifact.
- Checkout capacity at the 20-replica cap cannot absorb roughly 330 req/s; replica count and pool size were not verified.
- Worker pool saturation is inferred from log text only; no thread or connection pool metrics were available.
- Shallow /health checks reflect service liveness and do not exercise payment, inventory or database paths.
- Telemetry at 5-minute resolution places onset at 18:00:00Z, and sub-bucket ordering is unknown.

## Inferred conclusions
- Checkout-service became CPU-saturated and its worker pool filled after a sudden roughly 4x traffic increase starting at 18:00Z, and this saturation produced the latency and 503s (H1). (confidence 0.60) `M15, M11, M13, L0199`
- The HPA ceiling of 20 replicas (desired 34) likely prevented capacity from following the traffic step, turning the surge into sustained saturation; this is a contributing factor, not verified as the binding constraint. (confidence 0.35) `L0193, L0222, M11`
- Payment-service is not the leading dependency and does not explain the onset. (confidence 0.80) `M32, M33, M34, M36`
- The inventory step is a downstream effect of checkout's extra traffic rather than a leading cause. (confidence 0.60) `M25, M23, M21`
- Whether the surge is broad campaign traffic (C10 plus email blast) or concentrated bot or retry traffic (H3) is unresolved; H3 is weakly supported at about 0.25. (confidence 0.25) `C10, L0176, L0211, L0238, L0243`
- The api-gateway is not the failure origin: its own latency and error rate were unchanged while it passed a 4x volume step through. (confidence 0.70) `M03, M02, L0199`

## Remediation
- **immediate** - Scale checkout-service beyond the 20-replica HPA cap or raise maxReplicas, and verify current replica count and pod CPU throttling. _(The HPA warning shows desired demand above the configured ceiling while checkout CPU is saturated.)_
- **immediate** - Apply load shedding or rate limiting at api-gateway for the campaign traffic, prioritising checkout routes, and identify the top client IDs. _(Reduces the 4x step reaching checkout while the origin of the surge is unresolved.)_
- **immediate** - Retrieve the gateway request breakdown by client ID, route, referrer and user-agent for 17:55-18:10Z. _(This is the check that would separate campaign traffic from bot or retry traffic.)_
- **short_term** - Confirm checkout worker pool size, queue depth and connection pool metrics, and per-downstream call latency. _(Needed to confirm the CPU-bound worker-hold mechanism directly rather than from log text.)_
- **short_term** - Collect checkout-db, inventory-db and payments-db metrics at sub-5-minute resolution. _(The database tier is unverified and resolution limits ordering against onset.)_
- **short_term** - Review and re-size the checkout HPA maxReplicas and the worker queue limit against campaign-level traffic forecasts. _(The current cap appears to be a sizing decision that did not account for the campaign peak.)_
- **long_term** - Coordinate marketing campaign launches with capacity and load-test sign-off for checkout and api-gateway. _(The step coincided with a planned banner launch and email blast, so future campaigns need capacity preparation.)_
- **long_term** - Replace shallow /health checks with synthetic transaction checks on checkout, payment and inventory paths, and alert on saturation signals such as queue depth. _(Current health checks stayed green during the incident, so they did not detect the saturation.)_

## Open questions
- What was the source mix of the 18:00 traffic step: campaign referrers, bot user agents or retry headers?
- What were checkout's replica count, HPA maxReplicas history and pod CPU throttling during 18:00-18:30?
- What were checkout worker pool size, queue depth and connection pool utilisation over time?
- Did the 1-2 slow downstream calls (inventory reservation 679ms, payment retries) contribute measurably to worker hold time?
- What do the inventory-db and payments-db metrics show at sub-5-minute resolution around 18:00:00Z?
- Was the HPA cap of 20 set recently or long-standing, and was it reached before the 503s began?

## Data gaps and tool failures (10 shown, 32 reported)
- No checkout-service metrics or logs were queried for time-to-first-byte or per-downstream call latency, so checkout's own downstream-call timing is unverified. (reported 2x)
- Only 6 tool calls were available. I did not query dependency metrics for payment-service or inventory-service, the database, or the search backend behind api-gateway's /api/v1/search route.
- No per-endpoint, per-host or per-region breakdown was retrieved, so the concentration question is unanswered. The logs' route fields appear only on api-gateway warnings, not on checkout 503s.
- No checkout-service thread or connection pool metrics were returned. Only cpu, memory, error, latency and request rate are available, so pool saturation is inferred from the log message only.
- Telemetry ends at 18:30:00Z, so the state after that is unknown. Change history was not queried.
- No health check or telemetry for a database; it does not appear in the dependency graph, so the database part of the request could not be evaluated.
- Health checks are shallow (/health 200 only) and do not exercise payment or inventory transactions, TLS or database writes.
- No per-service latency or error telemetry was queried, so the health results cannot be linked to the p99 or 503 symptoms.
- Past incidents were not searched; I did not use them as evidence.
- 22 further gap report(s) in 22 group(s) omitted here (mostly about: budget, metrics, checkout, api-gateway, checked, log); the full list is in the run record.
