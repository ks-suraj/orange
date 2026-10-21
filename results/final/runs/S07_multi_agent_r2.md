# Incident report S07

- **Status:** CONCLUSIVE (confidence 0.55, margin 0.40, 10 verified supporting and 1 contradicting evidence items (9%))
- **System:** multi_agent · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** critic_accepted
- **Root cause:** `checkout-service` - traffic_surge (confidence 0.55)

## Summary
Incident S07 is determined conclusive by the system criteria, with leading hypothesis H1 at confidence 0.55 and a margin of 0.40 over the runner-up. Checkout-service p99 latency rose from about 320 ms to about 2.9 s and its error rate from about 0.3% to about 5.6% in the 18:00 UTC bucket. Checkout's worker pool hit its 500-slot cap (queue 500/500), and its 503 rejections began at 18:03:25Z, about 50 seconds after the HPA warning that desired replicas (34) exceeded maxReplicas (20). Request rates at checkout and api-gateway both rose roughly 4x at 18:00, so an incoming traffic step is the leading trigger, but its origin (legitimate campaign demand, retries, or a client storm) is unverified. Gateway latency, error rate, CPU and memory stayed flat, and gateway logs show no 503s forwarded from checkout, so the gateway is not the origin of the fault. The inventory v4.2.0 deploy at 17:25Z (H2, confidence 0.15) is weakened by flat inventory metrics through 17:50Z and a modest p99 step coinciding with its own traffic tripling. Residual gaps include per-pod, per-endpoint and gateway 503 data, and the tool budget was exhausted before these could be obtained.

## Conclusion decision
- confidence 0.55, margin 0.40, 10 verified supporting and 1 contradicting evidence items (9%)
- Criteria: top `checkout-service / traffic_surge` confidence 0.55, margin 0.40, 10 verified supporting / 1 contradicting items (9% contradicting); 0 evidence-backed material critic objection(s), 3 non-blocking

## Ranked hypotheses
1. **checkout-service** - traffic_surge (confidence 0.55)
   - Mechanism: A roughly 4x request-rate step at 18:00 (checkout 85 to 353 req/s, mirrored at api-gateway 417 to 1625 req/s) exceeded checkout's fixed 500-slot worker pool and HPA ceiling of 20 replicas (desired 34), so checkout rejected requests with 503 and p99 rose to about 2.9 s. The HPA warning at 18:02:34Z precedes the first pool-saturation 503 at 18:03:25Z, consistent with a capacity ceiling. The surge origin (campaign demand, retries, or client storm) is unverified.
   - Supporting evidence: `M15, M11, M13, M12, L0199, L0193, M05, C10, L0205, L0222`
   - Contradicting evidence: `M14`
   - Assumptions: The gateway request increase passes through to checkout one-for-one; Checkout capacity at 20 replicas is insufficient for about 340 req/s; Flat gateway error rate is compatible with checkout 503s being generated locally
2. **inventory-service** - deployment_regression (confidence 0.15)
   - Mechanism: The v4.2.0 HTTP client library bump at 17:25Z could have altered inventory's server-side behaviour and lengthened checkout's worker hold time, driving pool saturation. Slow inventory reservations (679 to 1236 ms) appear in checkout logs after onset. Inventory metrics show no step at 17:25 (tested for 17:00-17:50) and only a small p99 step at 18:00 that coincides with its own traffic tripling, which weakens this hypothesis.
   - Supporting evidence: `C09, D05, L0241, L0302, L0318`
   - Contradicting evidence: `M23, M22, M21, M25`
   - Assumptions: The library change affects inventory's server-side latency as seen by checkout; Inventory latency drives checkout worker hold time; Inventory 17:50-18:00 is not tested and could hide a step
3. **api-gateway** - other (confidence 0.15)
   - Mechanism: Gateway-side behaviour (rate limiting or request retries forwarded to checkout after the fall-sale flag at 17:55Z and the 18:00 email blast) could be the source of the extra checkout load. Rate-limiter warnings name four distinct clients each once, which makes a single retry storm unlikely but not excluded. Gateway metrics are flat, so this is weakly supported.
   - Supporting evidence: `C10, L0176, L0211, L0238, L0243`
   - Contradicting evidence: `M01, M02, M03, M04`
   - Assumptions: The gateway traffic step is caused by the campaign or retries rather than by checkout itself; Flat gateway metrics do not hide a forwarding fault

## Observed facts
- Checkout-service request_rate stepped from 85.48 req/s at 17:55Z to 352.97 req/s at 18:00Z, then stayed about 328-345 req/s through 18:30Z. `M15`
- Api-gateway request_rate rose from 417.09 req/s at 17:55Z to 1625.13 req/s at 18:00Z and peaked at 1696.43 req/s at 18:05Z. `M05`
- Checkout-service cpu_pct stepped from about 40% to 93.7% at 18:00Z and was 94-98% through 18:30Z, reaching 99.77% at 18:30Z. `M11`
- Checkout-service p99 latency rose from 321 ms at 17:55Z to 2931 ms at 18:00Z, peaking at 3005 ms at 18:15Z, against an 800 ms SLO; error rate rose from 0.32% to 5.65%. `M13, M12`
- Checkout logs show 'worker pool saturated (queue 500/500) -> 503' rejections from 18:03:25Z through 18:30:00Z, the dominant WARN/ERROR signature in the sample. `L0199, L0379, L0391`
- HPA warnings 'desired replicas 34 exceeds maxReplicas 20' first appear at 18:02:34Z and recur through 18:30:00Z. `L0193, L0390`
- Api-gateway cpu, memory, p99 latency and error rate stayed flat across 17:00-18:30Z, and no gateway WARN/ERROR line containing 503 was found for 17:55-18:10Z. `M01, M02, M03, M04, L0196, L0207`
- Inventory-service v4.2.0 (HTTP client library bump) deployed at 17:25Z; api-gateway 'fall-sale' feature flag enabled at 17:55Z; no change records for checkout-service in the window. `C09, C10`
- Inventory-service latency, error rate and request rate show no step at 17:25Z across 17:00-17:50Z; inventory p99 rose modestly from 91 ms to about 142 ms at 18:00Z alongside a 3.7x traffic step. `M23, M22, M25`
- Payment-service metrics are flat across 17:50-18:30Z, and all direct dependencies returned HTTP /health 200 at 18:28Z. `M33, M34, M36, H11, H07, H03`

## Assumptions
- The gateway request increase passes through to checkout one-for-one.
- Checkout capacity at 20 replicas is insufficient for roughly 340 req/s of traffic.
- Shallow /health checks do not exercise latency, timeouts or TLS, so they do not clear dependencies.
- Checkout 503s are generated locally by the worker-pool admission control, not forwarded from the gateway.
- The logged 503 lines are a sample; their count is lower than the ~5.5% error rate implies.

## Inferred conclusions
- The checkout-service latency and 503 incident is primarily caused by checkout's fixed worker-pool capacity being exceeded under a roughly 4x request step, with HPA capped at 20 replicas and unable to add capacity. (confidence 0.55) `M15, M11, M13, M12, L0199, L0193`
- The 18:00 traffic step is the trigger, but whether it reflects legitimate campaign demand, retries or a client storm cannot be determined from these data. (confidence 0.45) `M05, M15, L0176, L0211, L0238, L0243`
- Sustained saturation after 18:00 is better described as a capacity ceiling at 20 replicas with flat request rate than as an ongoing surge. (confidence 0.45) `M15, M11, L0193`
- Inventory-service is a weak candidate: the v4.2.0 deploy shows no metric step through 17:50Z, and its 18:00Z p99 step is small and coincides with its own traffic tripling. (confidence 0.15) `C09, M23, M25`
- Downstream latency (slow inventory reservations, slow search upstream) is more likely a secondary effect of saturation than the origin. (confidence 0.40) `L0241, L0302, L0318, L0194, M03`
- Card declines are unrelated baseline noise and do not explain the latency or 503 rise. (confidence 0.60) `L0027, L0195`

## Remediation
- **immediate** - Raise checkout-service HPA maxReplicas above 20 (desired 34) and verify new pods are scheduled and serving, as an immediate capacity mitigation. _(HPA warnings show computed demand exceeds the cap, and 503s are worker-pool rejections at a full 500-slot queue.)_
- **immediate** - Apply temporary load shedding or rate limiting at api-gateway for checkout traffic, or pause the 18:00 campaign traffic if feasible, to bring checkout request rate back toward baseline. _(The request step at 18:00 is the leading trigger, and reducing inbound volume relieves saturation while the origin is unverified.)_
- **immediate** - Pull api-gateway access logs by client ID for 17:55-18:10Z to separate legitimate campaign traffic from retries or a client storm. _(The surge origin is the main unresolved question and determines whether mitigation should target clients or capacity.)_
- **short_term** - Review checkout worker-pool sizing and queue limits against the per-request work and expected peak traffic, and set HPA maxReplicas to cover observed peak demand. _(The fixed 500-slot pool and 20-replica cap caused the capacity ceiling.)_
- **short_term** - Obtain per-pod checkout CPU, worker-pool and 503 counts, plus gateway 503 and status-code counts by minute, to confirm fleet-wide versus instance-skewed saturation. _(These data were not obtained, so instance skew and gateway-side 503 reconciliation remain untested.)_
- **long_term** - Add load-based or deep health checks and latency-aware monitoring for inventory and payment calls, and check checkout's inventory call timeouts and retries. _(Shallow health checks did not reveal dependency latency, and the inventory client-library change was not characterised.)_
- **long_term** - Establish campaign launch capacity planning and load-testing for marketing email blasts that drive checkout traffic. _(The 18:00 email blast and fall-sale flag coincided with a 4x traffic step that exceeded provisioned capacity.)_
- **long_term** - Document the inventory v4.2.0 library change details and test its effect on latency under load before further rollout. _(The change is a weak, untested lead and its settings are not recorded.)_

## Open questions
- What is the origin of the 4x traffic step at 18:00Z: legitimate campaign demand, client retries, or a client storm?
- Are the 503s and saturation concentrated on particular checkout pods or endpoints, which the available data could not show?
- Does the gateway forward or generate any 503s that account for the alert's gateway 503 increase, given the 0 WARN/ERROR 503 lines found?
- Does inventory-service show a step during 17:50-18:00Z, which was not queried?
- Did per-request work in checkout increase (for example from slower inventory calls) in addition to the traffic step?
- What were checkout's timeout, retry and connection settings for inventory calls, and did the v4.2.0 library change alter them?

## Data gaps and tool failures (10 shown, 41 reported)
- Tool-call budget (6) was exhausted, so no further queries were possible.
- No per-endpoint breakdown of checkout 503s or latency. The endpoint and instance concentration question is unanswered.
- No gateway-side 503 count or status-code metric was queried. The gateway 503 increase claimed in the alert is not confirmed or refuted directly, beyond flat gateway error_rate.
- No metrics or logs were pulled for inventory-service, payment-service, or the search upstream. Their state is unknown.
- Only 30 of 46 checkout WARN/ERROR lines were returned, so the counts above are from a sample.
- The 3 'retrying idempotent call to payment-service' warnings were seen only as a signature count, with no record ids, so they are not cited.
- No checkout thread-pool or connection-pool metrics exist in the metric set. Worker pool saturation comes from log text only.
- Per-pod or per-instance data was not queried, so instance concentration is untested.
- Change history and deployment events were not checked. Whether a deploy or config change coincided with the 18:00 step is unknown.
- 32 further gap report(s) in 32 group(s) omitted here (mostly about: returned, unknown, latency, queried, checked, log); the full list is in the run record.
