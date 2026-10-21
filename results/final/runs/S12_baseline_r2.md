# Incident report S12

- **Status:** CONCLUSIVE (confidence 0.60, margin 0.30, 5 verified supporting and 0 contradicting evidence items (0%))
- **System:** baseline · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** agent_finished
- **Root cause:** `api-gateway` - config_error (confidence 0.60)

## Summary
Error rate on api-gateway jumped from ~0.4% to ~14% at the 17:00 bucket, right after two changes logged at 16:57:00Z: an auth-service v4.0.0 deploy (new v2 session token format, v1 still accepted) and a netops gateway rate-limit change tightening /api/* burst from 200 to 20 per client. The gateway rate-limit change is the best fit for the 'too many requests' errors, since the 20x tighter burst lines up with the onset. Auth-service traffic rose from ~80 to ~107 req/s at the same time, with token-refresh warnings for expired or invalid sessions, which fits the sign-outs and may be a retry or refresh amplification effect. Gateway logs were inaccessible, so the 429 attribution is unverified. Health checks are all green, so they do not detect this degradation.

## Conclusion decision
- confidence 0.60, margin 0.30, 5 verified supporting and 0 contradicting evidence items (0%)
- Criteria: top `api-gateway / config_error` confidence 0.60, margin 0.30, 5 verified supporting / 0 contradicting items (0% contradicting); 0 evidence-backed material critic objection(s), 0 non-blocking

## Ranked hypotheses
1. **api-gateway** - config_error (confidence 0.60)
   - Mechanism: The netops rate-limit change cut the /api/* per-client burst from 200 to 20, so normal client bursts are rejected with 429 'too many requests'. Rejected clients retry and fail to refresh sessions, which generates the sign-out reports and the auth refresh traffic increase.
   - Supporting evidence: `C10, M02, M05, M10, L0189`
   - Contradicting evidence: none
   - Assumptions: The 4xx are 429s from this policy.; The change was in effect at 17:00.
2. **auth-service** - deployment_regression (confidence 0.30)
   - Mechanism: The v4.0.0 deploy changed session token issuance to v2. Clients or validators that mishandle v2 tokens see them as expired or invalid, which forces sign-outs and refresh loops that raise auth request volume.
   - Supporting evidence: `C09, L0189, L0201, M10`
   - Contradicting evidence: none
   - Assumptions: Token refresh failures are caused by v2 token handling.; The deploy completed at 16:57.
3. **api-gateway** - traffic_surge (confidence 0.10)
   - Mechanism: A client-side traffic surge or retry storm hit the gateway's /api/* routes and triggered rate limiting.
   - Supporting evidence: `M10`
   - Contradicting evidence: none
   - Assumptions: The auth surge reflects client traffic.

## Observed facts
- api-gateway error_rate was 0.36–0.45% from 16:00 to 16:55, then 14.83% at 17:00 and 13.6–14.6% through 17:30. `M02`
- Two changes were recorded at 16:57:00Z: auth-service deploy v4.0.0 (session tokens issued in v2 format, v1 still accepted) and api-gateway config change lowering /api/* burst 200 -> 20 per client. `C09, C10`
- auth-service request_rate rose from 82.39 req/s (16:55) to 108.05 req/s (17:00), staying ~104–108 through 17:30; it was 77.8–81 req/s before. `M10`
- auth-service logged repeated 'token refresh requested for expired or invalid session' WARNs from 17:00:32 onward (10 in the window), plus one 'rejected malformed Authorization header' ERROR at 17:01:01. `L0189, L0193, L0201, L0217, L0229, L0241, L0253, L0268, L0280, L0291, L0303`
- auth-service CPU (~25%), memory (~43–46%), p99 latency (~40 ms) and error rate (~0.1%) stayed flat across 17:00. `M06, M07, M08, M09`
- api-gateway latency p99 stayed ~175–187 ms and CPU ~38% across the window, with no change at 17:00. `M03, M01`
- All health checks (api-gateway, auth-service, checkout-service, search-service) returned HTTP 200 at 17:28. `H01, H02, H03, H14`

## Assumptions
- The 4xx responses are 429 rate-limit rejections produced by the new burst=20 policy (not verified; gateway logs are inaccessible).
- The health checks are shallow and do not exercise rate limiting or token validation of v2 tokens.
- The 16:57 timestamps for the two changes are accurate and both took effect before the 17:00 bucket.
- Users were signed out because clients failed token refresh or v2 token handling, not because of a password or credential change.
- (unverified - no valid evidence cited) api-gateway WARN/ERROR log query failed with 'access denied: requires elevated permissions'.

## Inferred conclusions
- The gateway rate-limit policy change (burst 200->20) most likely explains the 14% 4xx spike and the 'too many requests' errors, since it coincides with the onset and the request rate did not change at the gateway (~422 req/s, flat). (confidence 0.60) `C10, M02, M05`
- The auth-service v4.0.0 deploy is a plausible contributor to sign-outs, via token format incompatibility or refresh loops that double auth traffic, but auth error rate and latency did not rise, which weakens a hard-failure explanation. (confidence 0.30) `C09, M10, M07, L0189`
- The gateway request rate was unchanged while auth traffic rose ~30%, so the auth surge is probably client-side retries after the 429s or sign-outs, not an independent traffic surge. (confidence 0.35) `M05, M10`

## Remediation
- **immediate** - Roll back the api-gateway rate-limit change (burst 20 -> 200) to restore /api/* access. _(The change is the best-supported cause and the rollback is low-risk and fast.)_
- **immediate** - Pause or roll back auth-service v4.0.0 pending verification of v2 token handling, if sign-outs persist after the gateway rollback. _(The deploy is coincident with the sign-outs and refresh warnings; its impact is not yet confirmed.)_
- **short_term** - Obtain gateway log access to confirm the 4xx status codes are 429 and identify the affected clients and routes. _(Current attribution rests on timing alone.)_
- **long_term** - Add a canary or staged rollout for rate-limit changes and a 4xx-by-status alert. _(The change went straight to production with no alert on rejections.)_
- **long_term** - Add deep health checks covering token validation and rate-limit behaviour. _(The health checks were green during a user-facing outage.)_

## Open questions
- What are the 4xx status codes at the gateway (429 vs 401 vs 403), and which routes do they hit?
- Did the v4.0.0 auth deploy cause token validation failures, or is the sign-out purely client-side refresh behaviour?
- Why did the auth request rate rise ~30% at 17:00 with no gateway traffic change?
- Is the 16:57 timestamp for both changes exact, and which took effect first?

## Data gaps and tool failures (1 shown, 1 reported)
- query_logs(start=2026-09-12T16:00:00Z, end=2026-09-12T17:30:00Z, service=api-gateway, min_level=WARN, limit=20) -> error: Error: access denied: log index 'api-gateway-*' requires elevated permissions
