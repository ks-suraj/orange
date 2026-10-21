# Incident report S12

- **Status:** INCONCLUSIVE (top hypothesis confidence 0.40 is below 0.50; contradicting evidence is 62% of the weighed evidence (max 35%))
- **System:** multi_agent · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** max_rounds_reached

## Summary
System determination is INCONCLUSIVE: the top hypothesis (H1, rate-limit config change C10) has confidence 0.40, below the 0.50 threshold, and contradicting evidence is 62% of weighed evidence against a 35% maximum. Api-gateway error_rate, a proxy for the 4xx rate, stepped abruptly from about 0.4% to about 14% at 17:00Z, and both C09 (auth-service v4.0.0 token format v2 deploy) and C10 (gateway /api/* burst 200 to 20) were completed at 16:57Z. Gateway logs were access-denied, so the 4xx split by status code and route is unknown and the 429 attribution is unverified. Auth-service request_rate stepped up about 30% at 17:00Z while gateway request_rate stayed flat and checkout request_rate fell, which throttling alone does not explain. Neither change shows a rollback, and session-store could not be assessed. The leading cause is unresolved; the two same-minute changes remain active candidates.

## Conclusion decision
- top hypothesis confidence 0.40 is below 0.50
- contradicting evidence is 62% of the weighed evidence (max 35%)
- Criteria: top `api-gateway / config_error` confidence 0.40, margin 0.10, 3 verified supporting / 5 contradicting items (62% contradicting); 2 evidence-backed material critic objection(s), 5 non-blocking
  - objection: unsupported_claim: H1 asserts the 14% error rate is dominated by 429s and that /api/* covers refresh or login routes. Neither is verified: gateway logs were denied, no status-code [C10, M02, L0193]
  - objection: ignored_contradiction: A +30% auth-service request_rate step at 17:00 with flat gateway request_rate and a fall in checkout request_rate is not explained by throttling, which would re [M10, M05, M15]

## Ranked hypotheses
1. **api-gateway** - config_error (confidence 0.40)
   - Mechanism: The 16:57 rate-limit change cut the /api/* per-client burst from 200 to 20, so clients exceeding the burst receive 429s from 17:00, matching the abrupt error-rate step with flat gateway request rate, latency and resources. If refresh or login routes fall under /api/*, throttled refresh calls would also appear to users as sign-outs.
   - Supporting evidence: `C10, M02, M05, M01, M03, M04`
   - Contradicting evidence: `M10, M07, L0189`
   - Assumptions: The 14% error_rate is dominated by 429s, which is unverified because gateway logs were denied; Normal client bursts exceed 20 per client; Auth or refresh routes may fall under /api/* but this is unconfirmed
2. **auth-service** - deployment_regression (confidence 0.30)
   - Mechanism: The v4.0.0 deploy at 16:57 issues v2 session tokens while accepting v1, and some clients or validators fail on v2 tokens, causing refresh failures and forced sign-outs. Re-authentication and refresh retries could explain the auth request-rate step at 17:00 while gateway request rate stayed flat.
   - Supporting evidence: `C09, M10, L0189, L0201`
   - Contradicting evidence: `M07, M08, M05, L0193`
   - Assumptions: v1 acceptance does not work fully as described; Refresh WARNs reflect the migration rather than normal expiry; The auth step comes from re-authentication traffic, which is unconfirmed
3. **api-gateway** - config_error (confidence 0.25)
   - Mechanism: A combined effect: C10 throttles refresh or login calls routed through /api/*, the resulting failed refreshes drive sign-outs, and clients retry, which raises auth-service request rate while gateway total stays flat only if retries are absorbed at the gateway.
   - Supporting evidence: `C10, C09, M10, L0189`
   - Contradicting evidence: `M05, M07`
   - Assumptions: Auth routes fall under /api/* burst limit; Retries inflate auth traffic without raising gateway request rate

## Observed facts
- api-gateway error_rate was 0.36% to 0.45% from 16:00 to 16:55Z, then jumped to 14.83% at 17:00Z and stayed between 13.61% and 14.62% through 17:30Z. `M02`
- api-gateway request_rate, latency_p99, CPU and memory stayed in normal ranges with no step at 17:00Z. `M05, M03, M01, M04`
- Config change C10 (api-gateway, netops) reduced the /api/* burst from 200 to 20 per client at 16:57:00Z and is completed. `C10`
- Deploy C09 (auth-service v4.0.0, deploy-bot) issued session tokens in format v2 with v1 still accepted, completed at 16:57:00Z. `C09`
- auth-service request_rate stepped from about 80 req/s to about 104-108 req/s at 17:00Z and stayed there, while auth error_rate, latency and CPU stayed flat. `M10, M07, M08, M06`
- checkout-service request_rate fell from about 84 to about 61 req/s at 17:00Z. `M15`
- Auth-service logged about 10 token-refresh-expired-or-invalid-session WARNs from 17:00:32Z to 17:30Z, and one malformed Authorization header ERROR at 17:01:01Z. `L0189, L0201, L0217, L0229, L0241, L0253, L0268, L0280, L0291, L0303, L0193`
- Health checks at 17:28Z returned HTTP 200 for api-gateway, auth-service, checkout-service and search-service; these checks are shallow. `H01, H02, H03, H14`
- No rollback records appear for C09 or C10 in the change history reviewed. `C09, C10`

## Assumptions
- The 14% error_rate is dominated by 429 responses; this is unverified because gateway logs were denied and error_rate is a combined figure.
- The /api/* rate-limit rule covers auth or token-refresh routes; the C10 route list could not be retrieved.
- Normal client bursts exceed 20 requests per client.
- Health checks do not exercise rate limiting, token validation or session reads.
- Absence of rollback records means neither change has been reverted.
- Auth-service logs are sampled or truncated, so the 10 refresh WARNs may understate refresh volume.
- (unverified - no valid evidence cited) Log queries on api-gateway were denied for elevated permissions, so no status-code, route or client split of 4xx was obtained.
- (unverified - no valid evidence cited) session-store has no dependency edges, logs, metrics or health checks available, and no change history.

## Inferred conclusions
- C10 is the leading candidate for the throttling symptom (H1), but the top hypothesis is below the confidence threshold and its route scope and 429 share are unverified. (confidence 0.40) `C10, M02`
- C09 is a candidate for the sign-out symptom (H2), but the refresh WARN volume is too small to explain a 14% gateway 4xx rate, so it is at most partial support. (confidence 0.30) `C09, L0189, L0201`
- The 30% auth-service request_rate step with flat gateway traffic suggests extra auth calls, possibly refresh or re-auth retries, which fits C09 better than simple throttling, but its source is not established. (confidence 0.35) `M10, M05, M15`
- The root cause is unresolved: C09 and C10 landed in the same minute and cannot be separated by timing, and no rollback test has been run. (confidence 0.50) `C09, C10`

## Remediation
- **immediate** - Obtain elevated read access to api-gateway logs and break down 4xx by status code (401, 403, 429), route and client for 16:57 to now. _(The gateway 4xx split is the single most important missing evidence and determines which change is responsible.)_
- **immediate** - Consider reverting the /api/* burst limit from 20 to 200 as a low-risk mitigation, and monitor 4xx and sign-out reports for the effect. _(C10 is a plausible throttling cause with a reversible config change, though its effect is not confirmed.)_
- **immediate** - Pause further rollout of auth-service v4.0.0 and prepare a rollback of C09, given the auth request-rate step and refresh warnings. _(Sign-out symptoms and the auth traffic step may relate to the token format change; rollback is a safe mitigation if confirmed.)_
- **short_term** - Confirm whether auth and refresh routes fall under the /api/* rate-limit rule and document the match rules. _(Route scope decides whether C10 explains login and refresh throttling.)_
- **short_term** - Add deep health checks that exercise token validation, refresh and rate limiting, and add session-store to monitoring. _(Current shallow checks cannot detect either failure mode, and session-store is invisible.)_
- **long_term** - Add per-status-code 4xx metrics and per-caller request metrics for auth-service. _(Metrics lacking status-code and caller splits prevented attribution in this incident.)_
- **long_term** - Require that deploys and config changes be staged so that two changes do not land in the same minute. _(Simultaneous changes prevented separating the causes.)_

## Open questions
- What is the status-code split of the gateway 4xx rate, and do 429s and 401s rise together or separately?
- Which routes does the /api/* burst-20 limit cover, and do login or refresh calls match it?
- What is the caller and endpoint breakdown of the auth-service request_rate step at 17:00Z?
- Does auth-service v1 acceptance work as described, and what do INFO logs show for v1 versus v2 tokens?
- Does session-store take part in session validation, and what are its logs and metrics?
- What is the effect of reverting C09 and C10 in isolation?

## Data gaps and tool failures (10 shown, 39 reported)
- query_logs(start=2026-09-12T16:00:00Z, end=2026-09-12T17:30:00Z, service=api-gateway, min_level=WARN, limit=50) -> error: Error: access denied: log index 'api-gateway-*' requires elevated permissions
- query_logs(start=2026-09-12T16:45:00Z, end=2026-09-12T17:15:00Z, service=api-gateway, min_level=WARN, limit=30) -> error: Error: access denied: log index 'api-gateway-*' requires elevated permissions
- query_logs on api-gateway is denied (elevated permissions required for api-gateway-*). No 401/403/429 split, no route split, and no client-segment split were obtained.
- The metric set has no per-status-code 4xx series, so the 429-versus-401 timing question cannot be answered from metrics.
- Error_rate is a combined error figure, not confirmed to be 4xx-only. The alert's 14% 4xx figure matches it, but this is an inference.
- Health checks are shallow (HTTP /health only) and do not test rate limiting, token validation, or the /api/* path, so their healthy status does not rule out either change.
- Change history returns no rollback or feature-flag records; I did not check whether either change has been reverted.
- No telemetry or per-path error breakdown was queried, so I could not confirm which 4xx codes or which endpoints are affected.
- No 16:00 to 17:30 UTC error-rate or latency telemetry for api-gateway, auth-service or session-store was retrieved, so the requested error rates are not reported.
- 30 further gap report(s) in 30 group(s) omitted here (mostly about: auth-service, 4xx, api-gateway, returned, log, check); the full list is in the run record.
