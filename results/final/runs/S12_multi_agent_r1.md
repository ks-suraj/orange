# Incident report S12

- **Status:** INCONCLUSIVE (top hypothesis confidence 0.40 is below 0.50; contradicting evidence is 62% of the weighed evidence (max 35%))
- **System:** multi_agent · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** tool_budget_exhausted

## Summary
Api-gateway 4xx/error rate rose from about 0.4% to about 14.8% at 17:00:00Z and stayed elevated through 17:30Z, while gateway traffic, CPU, memory and latency stayed flat. Two changes landed at 16:57Z: a netops cut of the /api/* per-client burst from 200 to 20 (C10) and an auth-service v4.0.0 deploy issuing v2 session tokens while still accepting v1 (C09). The system determination is INCONCLUSIVE: the leading hypothesis (H-rate-limit) has confidence 0.40, below the 0.50 threshold, and contradicting evidence is 62% of weighed evidence. The status-code split could not be obtained because api-gateway logs were access-denied and no per-status metric exists, so the rate-limit and token-change explanations remain unseparated. Identity-service and session-store have no telemetry, and the investigation stopped on tool-budget exhaustion.

## Conclusion decision
- top hypothesis confidence 0.40 is below 0.50
- contradicting evidence is 62% of the weighed evidence (max 35%)
- Criteria: top `api-gateway / config_error` confidence 0.40, margin 0.10, 3 verified supporting / 5 contradicting items (62% contradicting); 3 evidence-backed material critic objection(s), 4 non-blocking
  - objection: unsupported_claim: The hypothesis assumes 429s make up a substantial share of the 4xx increase, but no per-status or 429 counter was retrieved. The gateway logs were access-denied [M02]
  - objection: ignored_contradiction: A rate-limit cut would reduce or leave flat backend auth traffic. Yet auth-service request_rate stepped up about 30% (82 to 108 req/s) in the same 17:00 bucket. [M10, M05]
  - objection: alternative_not_ruled_out: The leader does not explain the sign-out symptom, which the assumptions list as unexplained by this change. The first auth refresh-expired-session warning lands [L0189, L0201, C10]

## Ranked hypotheses
1. **api-gateway** - config_error (confidence 0.40)
   - Mechanism: The netops change at 16:57Z cut the /api/* per-client burst from 200 to 20, so legitimate bursty clients are throttled and receive 429 responses starting at the 17:00 onset. Gateway traffic, CPU, memory and latency stay flat because the rejections are policy decisions, not capacity effects.
   - Supporting evidence: `C10, M02, M05, M01, M03, M04`
   - Contradicting evidence: `M10`
   - Assumptions: Normal client bursts exceed 20 per client; 429s make up a substantial share of the 4xx increase; Sign-outs are not explained by this change alone
2. **auth-service** - deployment_regression (confidence 0.30)
   - Mechanism: The v4.0.0 deploy at 16:57Z began issuing v2 session tokens, and some downstream validators or clients reject them, causing 401s and forced sign-outs. Re-authentication traffic may explain the auth-service request-rate step from about 82 to 108 req/s at 17:00Z.
   - Supporting evidence: `C09, M10, M02, L0189`
   - Contradicting evidence: `M07, M08, M06, M09`
   - Assumptions: v1 acceptance is incomplete for some consumers; Auth-service's own error metrics hide rejections by downstream validators; Sign-outs drive the throttling via retries
3. **api-gateway** - other (confidence 0.20)
   - Mechanism: Both 16:57Z changes contribute: the token change forces re-login and the rate-limit cut throttles the resulting retry traffic, amplifying the 4xx rate beyond either change alone.
   - Supporting evidence: `C09, C10, M10, M02`
   - Contradicting evidence: `M05`
   - Assumptions: Both changes take effect simultaneously; Retry amplification is occurring

## Observed facts
- api-gateway error_rate was flat at 0.36-0.45% from 16:00 to 16:55Z, then rose to 14.83% at 17:00Z and stayed between 13.61% and 14.62% through 17:30Z. `M02`
- api-gateway request_rate stayed in a 403-432 req/s band across the window with no step at 17:00Z, and cpu, memory and p99 latency show no comparable step. `M05, M01, M03, M04`
- auth-service request_rate stepped from about 82 req/s to 108.05 req/s at 17:00Z and stayed about 104-108 req/s through 17:30Z. `M10`
- auth-service error_rate, latency, CPU and memory showed no step change at 17:00Z. `M07, M08, M06, M09`
- Config change C10 by netops at 16:57Z reduced the api-gateway /api/* rate-limit burst from 200 to 20 per client; it is the only api-gateway change in the window. `C10`
- Deploy C09 by deploy-bot at 16:57Z released auth-service v4.0.0, issuing session tokens in format v2 while still accepting v1; it is the only auth-service change in the window. `C09`
- auth-service logged 10 WARN 'token refresh requested for expired or invalid session' lines between 17:00:32Z and 17:30:00Z, plus one malformed Authorization header ERROR and one bad-password WARN. `L0189, L0201, L0217, L0229, L0241, L0253, L0268, L0280, L0291, L0303, L0193, L0202`
- Health checks at 17:28Z returned healthy for api-gateway, auth-service, checkout-service and search-service. `H01, H02, H03, H14`

## Assumptions
- Normal client bursts exceed 20 requests per client, so the C10 cut would throttle legitimate traffic.
- The rate limit is keyed per client as the change text states; the actual keying implementation was not verified.
- The health checks are shallow HTTP /health checks and do not exercise rate limiting or token validation.
- Metrics at 5-minute resolution cannot order the 16:57 changes against the 17:00 error step.
- auth-service's own error metrics may not capture rejections made by downstream validators or refresh-required responses.
- (unverified - no valid evidence cited) All api-gateway log queries (including 429, 401 and 403 filters) were denied with 'requires elevated permissions', and no 429 or 401/403 metric exists in the returned telemetry.
- (unverified - no valid evidence cited) No changes were recorded for identity-service, session-store or feature flags in 14:00-17:30Z, and no telemetry or logs exist for identity-service or session-store.

## Inferred conclusions
- The 4xx step at 17:00Z is abrupt and policy-like rather than a capacity effect, consistent with the C10 rate-limit cut, but the 429 share of the 4xx rate is unverified. (confidence 0.40) `M02, M05, M01, M03, M04, C10`
- The auth-service v2 token change (C09) may contribute to sign-outs and the auth request-rate step via re-login or refresh traffic, but v1 is still accepted and no v2 rejection counter was observed. (confidence 0.30) `C09, M10, L0189`
- A combined cause (token change driving re-login traffic while the rate-limit cut throttles retries) is possible but untested, since retry amplification has not been shown. (confidence 0.20) `C09, C10, M10`
- The true root cause cannot be determined from the current evidence, because the status-code split, per-client 429 breakdown and identity/session-store state are unobtainable with current tools. (confidence 0.80)

## Remediation
- **immediate** - Consider reverting or raising the /api/* per-client burst from 20 toward the previous 200 as a time-boxed mitigation, after confirming with netops that this does not break rate-limit protections. _(C10 is the change that directly matches the 'too many requests' symptom and is cheap to reverse, though the status-code split is unverified.)_
- **immediate** - Pause further rollout of auth-service v4.0.0 and verify v1 and v2 token acceptance across downstream validators before rolling forward or back. _(C09 is the other change at 16:57Z and may drive sign-outs and the auth request-rate step; a rollout pause limits exposure while the cause is unresolved.)_
- **immediate** - Obtain elevated-access api-gateway logs for 16:55-17:05Z and break down 401, 403 and 429 counts per minute, endpoint and client. _(This is the single check most likely to separate the rate-limit hypothesis from the token hypothesis.)_
- **short_term** - Add per-status-code error metrics for api-gateway (401, 403, 429) and token-invalid counters on auth-service and downstream validators. _(Current aggregate error_rate cannot attribute the 4xx surge to a cause.)_
- **short_term** - Replay the rate-limit policy in staging with burst values of 20 and 200 against recorded client traffic. _(Would confirm whether a burst of 20 throttles legitimate clients at the observed scale.)_
- **long_term** - Add telemetry and health checks that exercise rate limiting and v1/v2 token validation end to end, and bring identity-service and session-store into monitoring. _(Current shallow health checks passed during the incident and cannot detect either failure mode.)_
- **long_term** - Require change-review gating for rate-limit and auth token-format changes, with staged rollout and canary validation. _(Two changes landed in the same minute with no staged validation, which prevents ordering and attribution of their effects.)_

## Open questions
- What share of the 4xx rate is 429 versus 401 or 403, and which of these leads at the 17:00Z onset?
- Do the throttled clients overlap with the clients reporting sign-outs?
- What are the v1 versus v2 token issuance counts and token-invalid 401 counts after 16:57Z?
- What do identity-service and session-store metrics and logs show for 16:00-17:30Z?
- Does the rate-limit key use client ID, IP or token, and would a shared NAT or gateway identity hit the limit faster?
- Would finer-resolution telemetry show whether C10 or C09 took effect first within the 16:57-17:00 interval?

## Data gaps and tool failures (10 shown, 45 reported)
- query_logs(start=2026-09-12T16:30:00Z, end=2026-09-12T17:30:00Z, service=api-gateway, min_level=WARN, limit=20) -> error: Error: access denied: log index 'api-gateway-*' requires elevated permissions
- query_logs(start=2026-09-12T16:00:00Z, end=2026-09-12T17:30:00Z, service=api-gateway, min_level=WARN, contains=429, limit=30) -> error: Error: access denied: log index 'api-gateway-*' requires elevated permissions
- query_logs(start=2026-09-12T16:00:00Z, end=2026-09-12T17:30:00Z, service=api-gateway, min_level=WARN, contains=401, limit=30) -> error: Error: access denied: log index 'api-gateway-*' requires elevated permissions
- query_logs(start=2026-09-12T16:00:00Z, end=2026-09-12T17:30:00Z, service=api-gateway, min_level=WARN, contains=403, limit=30) -> error: Error: access denied: log index 'api-gateway-*' requires elevated permissions
- query_logs(start=2026-09-12T16:55:00Z, end=2026-09-12T17:05:00Z, service=api-gateway, min_level=WARN, limit=10) -> error: Error: access denied: log index 'api-gateway-*' requires elevated permissions
- query_logs(start=2026-09-12T16:57:00Z, end=2026-09-12T17:30:00Z, service=api-gateway, min_level=WARN, limit=30) -> error: Error: access denied: log index 'api-gateway-*' requires elevated permissions
- No metrics exist for identity-service or session-store in the telemetry store (tool returned no records), so their error rate, latency and token-refresh volume could not be checked. (reported 2x)
- api-gateway log index is access-denied (requires elevated permissions): no 401/403/429 counts, endpoint breakdown, client/tenant identifiers, or per-minute ordering of status codes could be obtained for 16:00–17:30Z.
- Metrics available for api-gateway are aggregate only (error_rate, not split by status code); no per-status or per-endpoint metric was returned.
- 35 further gap report(s) in 35 group(s) omitted here (mostly about: api-gateway, checked, auth-service, tool-call, budget, 4xx); the full list is in the run record.
