# Incident report S12

- **Status:** CONCLUSIVE (confidence 0.60, margin 0.25, 4 verified supporting and 0 contradicting evidence items (0%))
- **System:** baseline · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** agent_finished
- **Root cause:** `api-gateway` - config_error (confidence 0.60)

## Summary
api-gateway 4xx rate jumped from about 0.4% to about 14% starting at 17:00 UTC, the same window as two changes made at 16:57: a netops rate-limit change cutting /api/* burst from 200 to 20 per client, and an auth-service v4.0.0 deploy that issues session tokens in format v2. The 'too many requests' symptom matches the rate-limit change directly, and the sign-outs match the token-format change, but the api-gateway logs were inaccessible, so I could not confirm which status codes or token errors the gateway is returning. Both changes are plausible causes, and the rate-limit change is the better-supported one for the 4xx spike. Health checks are green everywhere, so they do not reflect this failure.

## Conclusion decision
- confidence 0.60, margin 0.25, 4 verified supporting and 0 contradicting evidence items (0%)
- Criteria: top `api-gateway / config_error` confidence 0.60, margin 0.25, 4 verified supporting / 0 contradicting items (0% contradicting); 0 evidence-backed material critic objection(s), 0 non-blocking

## Ranked hypotheses
1. **api-gateway** - config_error (confidence 0.60)
   - Mechanism: Burst limit cut from 200 to 20 per client at 16:57 causes legitimate client bursts to receive 429 'too many requests', producing the 14% 4xx rate and pushing clients into retries and re-auth.
   - Supporting evidence: `C10, M02, M05, M10`
   - Contradicting evidence: none
   - Assumptions: Typical client bursts exceed 20 requests.
2. **auth-service** - deployment_regression (confidence 0.35)
   - Mechanism: v4.0.0 issues v2-format session tokens that some clients or the gateway fail to validate, so sessions are invalidated, refresh fails, and users are signed out.
   - Supporting evidence: `C09, L0189, L0193, M10`
   - Contradicting evidence: none
   - Assumptions: v1 tokens are still accepted, so the failure is client-side or gateway-side for v2 tokens.
3. **platform** - infrastructure_failure (confidence 0.05)
   - Mechanism: The 08:00 node pool upgrade causes intermittent failures. It is unlikely because the onset is at 17:00 and all nodes were Ready.
   - Supporting evidence: `C08`
   - Contradicting evidence: none
   - Assumptions: Node issues would show up in resource metrics.

## Observed facts
- api-gateway error_rate went from 0.37% at 16:55 to 14.83% at 17:00 and stayed between 13.6% and 14.6% through 17:30. `M02`
- api-gateway request_rate stayed flat (about 403-432 req/s) across the window, with no traffic jump at 17:00. `M05`
- Two changes were recorded at 16:57:00Z: auth-service deploy v4.0.0 (session tokens issued in format v2, v1 still accepted) and api-gateway config change lowering /api/* burst 200 -> 20 per client. `C09, C10`
- auth-service request_rate rose from about 80 req/s to about 105-108 req/s starting at 17:00, while its error_rate stayed at about 0.06-0.15%. `M10, M07`
- auth-service logged repeated WARN 'token refresh requested for expired or invalid session' messages from 17:00:32 through 17:30:00 (10 in the window), plus one ERROR 'rejected malformed Authorization header' at 17:01:01. `L0189, L0193, L0303`
- api-gateway latency_p99 stayed around 173-187 ms and CPU and memory stayed flat, so there is no sign of gateway resource exhaustion. `M03, M01, M04`
- Dependency health checks for api-gateway, auth-service, checkout-service and search-service all returned HTTP 200 at 17:28. `H01, H02, H03, H14`

## Assumptions
- The 4xx spike is 429 responses from the new burst limit of 20 per client; this is not confirmed because gateway logs were unavailable.
- Users' sign-outs come from v2 session tokens being rejected or failing refresh; no auth-service log names the token format directly.
- Health checks do not exercise rate limiting or token validation, so their green status does not rule out either fault.
- The 16:57 timestamps for C09 and C10 are accurate and the changes took effect at that time.
- (unverified - no valid evidence cited) query_logs on api-gateway-* failed with 'access denied: requires elevated permissions'.

## Inferred conclusions
- The api-gateway rate-limit policy change (burst 200 -> 20 per client) most likely explains the 4xx spike and the 'too many requests' errors, because it coincides to the minute with the onset and cuts the allowed burst tenfold while traffic is unchanged. (confidence 0.60) `C10, M02, M05`
- The auth-service v4.0.0 token-format change is the likely cause of sign-outs and refresh failures, and it may also contribute to 4xx responses; the spike in auth request_rate suggests clients are re-authenticating in response. (confidence 0.35) `C09, L0189, M10`
- The two changes are not distinguishable from the available data, because both start at 16:57 and both are visible in the first 17:00 bucket. (confidence 0.50) `C09, C10, M02`

## Remediation
- **immediate** - Roll back the api-gateway rate-limit change C10 to burst 200 per client, which is the fastest test of the rate-limit hypothesis. _(It is a reversible config change tied to the exact onset minute.)_
- **immediate** - Roll back or pause auth-service v4.0.0 (C09), or force clients to keep using v1 tokens, to stop the refresh failures and sign-outs. _(Auth refresh errors and the auth request surge both start at 17:00.)_
- **immediate** - Get api-gateway status-code and log access for the incident responders so the 429 versus 401 split can be checked. _(Current gateway logs are blocked, so the root cause cannot be confirmed.)_
- **short_term** - Verify the rollback by checking api-gateway error_rate returns to about 0.4% and auth refresh warnings stop. _(Confirms which change was responsible.)_
- **long_term** - Stage rate-limit changes with canary or shadow mode and review burst values before rollout. _(A 10x cut shipped without traffic validation.)_
- **long_term** - Require backward-compatibility testing and a staged rollout for token format migrations. _(v1 was still accepted by design, yet sign-outs still occurred.)_

## Open questions
- What HTTP status codes does api-gateway return for the 4xx responses (429 or 401/403)?
- Did the rate-limit change affect all clients or only some, and what is the per-client request rate after 17:00?
- Does auth-service reject v2 tokens at the gateway, or do clients fail to refresh and then sign out?
- Why did auth request_rate rise about 30% at 17:00 without a matching rise in gateway traffic?
- Did the 16:57 deploy and config change land at exactly the same time, or does the gateway pick up config later than the deploy?

## Data gaps and tool failures (1 shown, 1 reported)
- query_logs(start=2026-09-12T16:00:00Z, end=2026-09-12T17:30:00Z, service=api-gateway, min_level=WARN, limit=20) -> error: Error: access denied: log index 'api-gateway-*' requires elevated permissions
