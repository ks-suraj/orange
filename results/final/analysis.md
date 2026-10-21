# Outcome analysis

| | baseline | multi_agent |
|---|---|---|
| accuracy | 0.8333 | 0.5556 |
| top_hypothesis_correct_determinable | 0.9667 | 0.9 |
| conclusive_rate | 0.8611 | 0.4167 |
| precision_when_conclusive | 0.9643 | 0.9333 |
| mean_rounds | None | 2.6389 |
| runs_hitting_tool_budget | 0 | 32 |

## Outcome categories (runs)

| Outcome | baseline | multi_agent |
|---|---|---|
| correct_diagnosis | 27 | 14 |
| abstained_correct_lead | 2 | 13 |
| abstained_wrong_lead | 0 | 2 |
| wrong_diagnosis | 1 | 1 |
| correct_abstention | 3 | 6 |
| unwarranted_conclusion | 3 | 0 |
| error | 0 | 0 |

## Failed criteria in inconclusive runs

- baseline: {'contradiction_share': 2, 'confidence': 3}
- multi_agent: {'confidence': 10, 'contradiction_share': 20, 'verified_support': 2}

## Per scenario (correct / top-correct / conclusive, out of runs)

| Scenario | baseline | multi_agent |
|---|---|---|
| S01 | 3/3/3 of 3 | 0/3/0 of 3 |
| S02 | 3/3/3 of 3 | 2/3/2 of 3 |
| S03 | 3/3/3 of 3 | 1/3/1 of 3 |
| S04 | 3/3/3 of 3 | 1/1/2 of 3 |
| S05 | 3/3/3 of 3 | 3/3/3 of 3 |
| S06 | 2/2/3 of 3 | 1/3/1 of 3 |
| S07 | 3/3/3 of 3 | 2/3/2 of 3 |
| S08 | 1/3/1 of 3 | 0/3/0 of 3 |
| S09 | 3/3/3 of 3 | 1/2/1 of 3 |
| S10 | 3/0/0 of 3 | 3/0/0 of 3 |
| S11 | 3/3/3 of 3 | 3/3/3 of 3 |
| S12 | 0/0/3 of 3 | 3/0/0 of 3 |

## Inconclusive runs

- **S08_baseline_r2** (expected inconclusive: False, top payment-service/deployment_regression, top correct: True): failed ['contradiction_share']
- **S08_baseline_r3** (expected inconclusive: False, top payment-service/deployment_regression, top correct: True): failed ['contradiction_share']
- **S10_baseline_r1** (expected inconclusive: True, top search-service/dependency_failure, top correct: False): failed ['confidence']
- **S10_baseline_r2** (expected inconclusive: True, top search-index/resource_exhaustion, top correct: False): failed ['confidence']
- **S10_baseline_r3** (expected inconclusive: True, top search-index/dependency_failure, top correct: False): failed ['confidence']
- **S01_multi_agent_r1** (expected inconclusive: False, top checkout-service/deployment_regression, top correct: True): failed ['confidence', 'contradiction_share']
  - objection: ignored_contradiction: The NPE mechanism is presented as the cause of the checkout 500s, but the ledger shows roughly 1 NPE per minute against roughly 900 failing requests per minute. [L0188, L0340, M12, M15]
- **S01_multi_agent_r2** (expected inconclusive: False, top checkout-service/deployment_regression, top correct: True): failed ['contradiction_share']
  - objection: alternative_not_ruled_out: Checkout's 500 count (about 18% of about 85 req/s, roughly 15/s) cannot account for the gateway's about 25/s 5xx on the checkout route. The roughly 10/s excess  [M02, M12, M05, M15, L0186, L0339]
- **S01_multi_agent_r3** (expected inconclusive: False, top checkout-service/deployment_regression, top correct: True): failed ['contradiction_share']
  - objection: ignored_contradiction: The gateway 500 at 14:00:08 (L0186) precedes the first DiscountEngine NPE at 14:00:27 (L0188), and no checkout-side error exists for that request. The NPE canno [L0186, L0188]
  - objection: alternative_not_ruled_out: H2 (unrecorded null pricing/discount input) fits the NPE signature and the 14:00 onset equally well for the checkout-side failure. The deploy-coincidence argume [C09, L0188, P04]
- **S02_multi_agent_r3** (expected inconclusive: False, top payment-service/config_error, top correct: True): failed ['confidence', 'contradiction_share']
  - objection: unsupported_claim: The mechanism requires the pool to be near saturation under normal load before 09:58 so that a 50 ms wait is reachable. No pool active/idle/waiting data exists  [L0193, L0289]
  - objection: alternative_not_ruled_out: H2 (connection leak or client-side pool shrink in payment-service starting near 10:00) fits the same constant pool state and step change. Flat DB metrics are co [M37, M38, M40, L0193]
- **S03_multi_agent_r1** (expected inconclusive: False, top notification-worker/resource_exhaustion, top correct: True): failed ['contradiction_share']
  - objection: ignored_contradiction: During 09:30 to 09:50 the worker logged 92% GC overhead yet sustained about 30 req/s, processed batches normally and sent confirmations, with lag near 4 s. The  [L0095, L0162, L0170, M31, M30]
- **S03_multi_agent_r3** (expected inconclusive: False, top notification-worker/resource_exhaustion, top correct: True): failed ['contradiction_share']
  - objection: unsupported_claim: The lag growth of about 0.45 s per s is asserted to be consistent with consumption below arrival, but neither arrival nor consumed rate was measured. Intake of  [M30, M31, M05, M15]
- **S04_multi_agent_r3** (expected inconclusive: False, top payment-service/dependency_failure, top correct: False): failed ['contradiction_share']
  - objection: unsupported_claim: The hypothesis rests on the 503s being genuine provider responses, which is listed as an assumption. No telemetry distinguishes provider-returned 503s from loca [L0186, L0402, H10]
  - objection: alternative_not_ruled_out: Local outbound-client failure (e.g. a client-side circuit breaker or bulkhead returning 503-like errors) fits the same log signature, has the same onset, and sh [L0186, L0200, M34]
- **S06_multi_agent_r2** (expected inconclusive: False, top inventory-db/infrastructure_failure, top correct: True): failed ['contradiction_share']
  - objection: ignored_contradiction: Replication and connections recovered at 13:10 but the read-only UPDATE errors continue at a steady cadence to 13:30. H1 attributes this to the endpoint still r [M16, M20, M22, L0317, H06]
- **S06_multi_agent_r3** (expected inconclusive: False, top inventory-db/infrastructure_failure, top correct: True): failed ['contradiction_share']
  - objection: unsupported_claim: The analysis asserts that inventory writes are routed to read-only standby db-inv-2 and that db-inv-1 is unavailable. No ledger record shows the write connectio [L0185, L0206, H06, L0180, L0183]
  - objection: alternative_not_ruled_out: H2 (inventory-service connection target misconfigured to the standby) fits the same 25006 error signature and is not excluded. The replication break at 12:59:32 [L0185, M16, H07, L0180]
- **S07_multi_agent_r1** (expected inconclusive: False, top checkout-service/traffic_surge, top correct: True): failed ['contradiction_share']
  - objection: alternative_not_ruled_out: Inventory-service latency rose from about 90ms to about 142-145ms (about 1.6x) at 18:00 and checkout logs show sparse slow inventory reservation warnings (679-1 [M23, L0241, L0302, L0318]
- **S08_multi_agent_r1** (expected inconclusive: False, top payment-service/deployment_regression, top correct: True): failed ['contradiction_share']
  - objection: alternative_not_ruled_out: The payment-provider failure (H3) is not excluded by the evidence. Provider telemetry is entirely absent, and the status-page check ran after onset and is shall [M33, C09, H10]
- **S08_multi_agent_r2** (expected inconclusive: False, top payment-service/deployment_regression, top correct: True): failed ['confidence']
  - objection: ignored_contradiction: The checkout log L0212 attributes a rejection to 'card declined by issuer'. Under H-A, payment writes fail with ORM/schema errors, which would not produce issue [L0212]
  - objection: unsupported_claim: The claim that health checks do not exercise the payment write path is correct, but the report uses this to keep H-A alive without any positive evidence of a wr [H11, H12]
- **S08_multi_agent_r3** (expected inconclusive: False, top payment-service/deployment_regression, top correct: True): failed ['contradiction_share']
  - objection: unsupported_claim: The claim that the deploy is the trigger rests on the onset coinciding with C09 three minutes earlier, which the critique notes is the trap of blaming a change  [C09, M33, M34, M36, H10]
- **S09_multi_agent_r1** (expected inconclusive: False, top inventory-service/config_error, top correct: True): failed ['confidence', 'contradiction_share']
  - objection: unsupported_claim: The causal mechanism requires that realtime_stock_recalc gates StockRecalculator.recomputeAll. No ledger record confirms this: the flag-history and past-inciden [C09, L0186]
  - objection: alternative_not_ruled_out: H-B (a non-flag-gated recompute job starting near 15:00) fits the same CPU, error and latency step and the same WARN signature. The ledger has no evidence that  [C09, M21, M23, L0186, L0313]
- **S09_multi_agent_r2** (expected inconclusive: False, top inventory-service/deployment_regression, top correct: False): failed ['contradiction_share']
  - objection: unsupported_claim: H1 asserts that realtime_stock_recalc gates the recomputeAll path, but no ledger record or tool output shows this; T5 explicitly failed to confirm it. Supportin [C09, L0186]
  - objection: alternative_not_ruled_out: H2 (an internal or scheduled recomputeAll unrelated to the flag) explains the same 15:00 step, the same CPU saturation and the same deadline WARNs. No ledger ev [C09, L0186, M21, M23]
  - objection: ignored_contradiction: Checkout p99 rose from about 310 ms to 2.5 s with a step matching inventory, yet checkout error rate stayed at 0.3% and checkout logs show no inventory-related  [M13, M12, M22, L0039, L0112]
- **S10_multi_agent_r1** (expected inconclusive: True, top search-service/dependency_failure, top correct: False): failed ['confidence', 'contradiction_share']
  - objection: ignored_contradiction: Identical slow-upstream warnings at 19:26 (1068ms) and 19:42 (885ms) occurred while p99 stayed near 180ms, and the largest logged upstream time (1079ms) is belo [L0083, L0126, M03, L0192]
- **S10_multi_agent_r2** (expected inconclusive: True, top search-service/dependency_failure, top correct: False): failed ['confidence', 'verified_support', 'contradiction_share']
  - objection: alternative_not_ruled_out: The 1633 ms p99 exceeds every logged upstream time (max 1079 ms), and the only fast search request in the window (169 ms at 20:03:40) sits between slow ones. Th [M03, L0178, L0185, L0192, L0193]
  - objection: unsupported_claim: The claim that /api/v1/search is served by search-service rests on a single sync_http edge (D02). No routing configuration, upstream host field, or trace confir [D02, L0178, L0185, L0192]
- **S10_multi_agent_r3** (expected inconclusive: True, top search-service/dependency_failure, top correct: False): failed ['confidence', 'verified_support', 'contradiction_share']
  - objection: unsupported_claim: The claim that search-service serves /api/v1/search rests only on the existence of one dependency edge D02; no route configuration was obtained and the T6 resul [D02]
  - objection: alternative_not_ruled_out: The slow-upstream WARN lines are emitted by the gateway after it waits on upstream calls, so they cannot distinguish a slow upstream from gateway-side queuing o [L0151, L0178, L0185, L0192, M01, M05]
- **S12_multi_agent_r1** (expected inconclusive: True, top api-gateway/config_error, top correct: False): failed ['confidence', 'contradiction_share']
  - objection: unsupported_claim: The hypothesis assumes 429s make up a substantial share of the 4xx increase, but no per-status or 429 counter was retrieved. The gateway logs were access-denied [M02]
  - objection: ignored_contradiction: A rate-limit cut would reduce or leave flat backend auth traffic. Yet auth-service request_rate stepped up about 30% (82 to 108 req/s) in the same 17:00 bucket. [M10, M05]
  - objection: alternative_not_ruled_out: The leader does not explain the sign-out symptom, which the assumptions list as unexplained by this change. The first auth refresh-expired-session warning lands [L0189, L0201, C10]
- **S12_multi_agent_r2** (expected inconclusive: True, top api-gateway/config_error, top correct: False): failed ['confidence', 'contradiction_share']
  - objection: unsupported_claim: H1 asserts the 14% error rate is dominated by 429s and that /api/* covers refresh or login routes. Neither is verified: gateway logs were denied, no status-code [C10, M02, L0193]
  - objection: ignored_contradiction: A +30% auth-service request_rate step at 17:00 with flat gateway request_rate and a fall in checkout request_rate is not explained by throttling, which would re [M10, M05, M15]
- **S12_multi_agent_r3** (expected inconclusive: True, top api-gateway/config_error, top correct: False): failed ['confidence', 'contradiction_share']
  - objection: ignored_contradiction: Auth-side evidence shows session-expiry and refresh warnings beginning at 17:00:32Z and a v2 issuance pattern that coincides with the step. The auth request_rat [L0189, M10, L0188]
  - objection: alternative_not_ruled_out: Whether /api/auth, login and token-refresh routes fall under the /api/* burst limit was not confirmed. If they do, the 20-per-client limit could throttle refres [C10]
