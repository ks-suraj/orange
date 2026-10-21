# Incident report S12

- **Status:** CONCLUSIVE (confidence 0.60, margin 0.20, 5 verified supporting and 1 contradicting evidence items (17%))
- **System:** baseline · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** agent_finished
- **Root cause:** `api-gateway` - config_error (confidence 0.60)

## Summary
Api-gateway 4xx jumped from about 0.4% to about 14% at 17:00 UTC, the same minute two changes landed at 16:57: a gateway rate-limit tightening (/api/* burst 200 to 20 per client) and an auth-service v4.0.0 deploy that issues v2 session tokens. Request volume at the gateway did not change, which points away from a traffic surge and toward the rate-limit config for the 'too many requests' errors. The sign-outs line up with auth token-refresh warnings and a roughly 35% rise in auth request rate, which fits the auth v4 deploy but is not yet proven. Gateway logs were inaccessible, so the 429 and 401 split is unverified. Both changes are plausible and confounded by timing, so the verdict is not conclusive.

## Conclusion decision
- confidence 0.60, margin 0.20, 5 verified supporting and 1 contradicting evidence items (17%)
- Criteria: top `api-gateway / config_error` confidence 0.60, margin 0.20, 5 verified supporting / 1 contradicting items (17% contradicting); 0 evidence-backed material critic objection(s), 0 non-blocking

## Ranked hypotheses
1. **api-gateway** - config_error (confidence 0.60)
   - Mechanism: The rate-limit policy change cut the /api/* burst limit from 200 to 20 per client at 16:57, so legitimate clients get HTTP 429 'too many requests' from 17:00, and failed refreshes or retries lead to sign-outs.
   - Supporting evidence: `C10, M02, M05, M10, L0189`
   - Contradicting evidence: `H01`
   - Assumptions: The 4xx responses are mostly 429s.; Health checks do not exercise rate limiting.
2. **auth-service** - deployment_regression (confidence 0.40)
   - Mechanism: The v4.0.0 deploy issues v2 session tokens at 16:57, so clients or services that cannot validate v2 tokens see sessions as invalid, triggering refresh failures and sign-outs, with retries raising auth load.
   - Supporting evidence: `C09, L0189, L0201, L0217, M10`
   - Contradicting evidence: `M07, H02, L0193`
   - Assumptions: Refresh failures are caused by the v2 token format rather than the rate limit.; Some services reject v2 tokens.
3. **api-gateway** - traffic_surge (confidence 0.05)
   - Mechanism: A client-side traffic surge or retry storm raises request volume and trips rate limits.
   - Supporting evidence: `M10`
   - Contradicting evidence: `M05`
   - Assumptions: Traffic is measured accurately at the gateway.

## Observed facts
- api-gateway error_rate was about 0.36-0.45% from 16:00 to 16:55, then jumped to 14.83% at 17:00 and stayed between 13.6% and 14.6% through 17:30. `M02`
- api-gateway request_rate stayed flat at about 403-432 req/s before and after 17:00 (mean 422). `M05`
- Two changes were recorded at 2026-09-12T16:57:00Z: auth-service deploy v4.0.0 (issue session tokens in format v2, v1 still accepted) and an api-gateway config change lowering /api/* burst from 200 to 20 per client. `C09, C10`
- auth-service request_rate rose from about 78-82 req/s (16:45-16:55) to about 104-108 req/s from 17:00 onward. `M10`
- auth-service logged repeated WARN 'token refresh requested for expired or invalid session' messages from 17:00:32Z onward, with 10 such warnings in the 16:50-17:30 window. `L0189, L0201, L0217, L0303`
- auth-service logged one ERROR 'rejected malformed Authorization header' at 17:01:01Z, and its error_rate stayed about 0.06-0.15%. `L0193, M07`
- Health checks at 17:28Z returned HTTP 200 for api-gateway, auth-service, checkout-service and search-service. `H01, H02, H03, H14`

## Assumptions
- The gateway 4xx spike is mostly HTTP 429 from the new burst limit of 20 per client, consistent with the 'too many requests' user reports.
- The health checks are shallow and do not exercise rate limiting or token validation.
- Clients that receive 429s on token refresh or re-login end up signed out.
- The auth request-rate rise is driven by client retries after throttling or sign-outs, not by an independent load source.
- (unverified - no valid evidence cited) Gateway logs could not be read (access denied for api-gateway-* index), so the status-code breakdown of the 4xx responses is unknown.

## Inferred conclusions
- The gateway rate-limit tightening (C10) is the most likely cause of the 14% 4xx spike and the 'too many requests' errors, since the step change coincides with the config and request volume is unchanged. (confidence 0.60) `M02, M05, C10`
- The auth-service v4.0.0 token-format change (C09) is a plausible contributor to the sign-outs, as refreshes for invalid sessions began at the deploy minute, but the v1 fallback makes a direct rejection mechanism unproven. (confidence 0.40) `C09, L0189, M10`
- The two changes are confounded in time, and the gateway logs needed to separate 429 from 401 responses were unavailable, so the attribution between them is not settled. (confidence 0.50) `C09, C10`

## Remediation
- **immediate** - Roll back the api-gateway rate-limit change (burst 20 back to 200) to clear the 429 errors. _(The step change matches the config time and the symptom is throttling.)_
- **immediate** - Consider rolling back auth-service v4.0.0 if sign-outs persist after the gateway rollback. _(Refresh failures for invalid sessions started at the deploy minute.)_
- **immediate** - Get access to the api-gateway logs and break down 4xx by status code (429 vs 401) and by client. _(Needed to confirm which change drives which symptom.)_
- **short_term** - Re-tune the per-client burst limit with a staged rollout, using measured client traffic. _(A 10x cut in burst is far too aggressive for normal API usage.)_
- **short_term** - Add a canary and a pre-merge check for auth token-format changes covering refresh across v1 and v2 tokens. _(The health checks did not catch the session problem.)_
- **long_term** - Require change-review for gateway rate-limit policy changes and alert on 4xx rate and per-client 429 counts. _(The 14% 4xx spike was not caught before users were affected.)_

## Open questions
- What is the HTTP status breakdown of the gateway 4xx responses (429 vs 401 vs 403)?
- Are the sign-outs tied to 401 responses from the gateway or to auth refresh failures?
- Does the auth request-rate rise come from client retries after 429s?
- Are the v1 tokens still accepted by all services, and do any services reject v2 tokens?
- Why did the health checks stay green when the 4xx rate is at 14%?

## Data gaps and tool failures (2 shown, 2 reported)
- query_logs(start=2026-09-12T16:00:00Z, end=2026-09-12T17:30:00Z, service=api-gateway, min_level=WARN, limit=20) -> error: Error: access denied: log index 'api-gateway-*' requires elevated permissions
- query_logs(start=2026-09-12T16:55:00Z, end=2026-09-12T17:05:00Z, service=api-gateway, min_level=INFO, limit=15) -> error: Error: access denied: log index 'api-gateway-*' requires elevated permissions
