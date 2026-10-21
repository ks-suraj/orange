# Incident report S12

- **Status:** INCONCLUSIVE (top hypothesis confidence 0.40 is below 0.50; contradicting evidence is 50% of the weighed evidence (max 35%))
- **System:** multi_agent · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** max_rounds_reached

## Summary
Between 16:55 and 17:00 UTC, api-gateway 4xx error_rate stepped from about 0.4% to about 14% and stayed there through 17:30, while gateway request_rate, latency and resource use stayed flat. Two completed changes, C10 (api-gateway /api/* burst limit cut from 200 to 20 per client) and C09 (auth-service v4.0.0 issuing v2 session tokens), both landed at 16:57 UTC, three minutes before onset. Auth-service request_rate rose about 31% at 17:00 and session-refresh WARN lines began at 17:00:32, but auth error_rate stayed flat and no v2 rejection was logged. Gateway logs and status-code breakdowns were inaccessible, so the 429 versus 401 mix is unknown. The system determination is INCONCLUSIVE: the leading hypothesis (C10 causing 429s) has confidence 0.40, below the 0.50 threshold, and contradicting evidence is 50% of weighed evidence. The incident cannot be attributed to a single cause on current evidence.

## Conclusion decision
- top hypothesis confidence 0.40 is below 0.50
- contradicting evidence is 50% of the weighed evidence (max 35%)
- Criteria: top `api-gateway / config_error` confidence 0.40, margin 0.10, 4 verified supporting / 4 contradicting items (50% contradicting); 2 evidence-backed material critic objection(s), 5 non-blocking
  - objection: ignored_contradiction: Auth-side evidence shows session-expiry and refresh warnings beginning at 17:00:32Z and a v2 issuance pattern that coincides with the step. The auth request_rat [L0189, M10, L0188]
  - objection: alternative_not_ruled_out: Whether /api/auth, login and token-refresh routes fall under the /api/* burst limit was not confirmed. If they do, the 20-per-client limit could throttle refres [C10]

## Ranked hypotheses
1. **api-gateway** - config_error (confidence 0.40)
   - Mechanism: The netops change C10 at 16:57:00Z cut the /api/* burst limit from 200 to 20 per client, so legitimate bursty clients are rejected with 429s, producing the sustained step in api-gateway error_rate from about 0.4% to about 14% at 17:00. Flat request_rate, latency and CPU/memory rule out load-driven failure, so the rejections are rule-driven.
   - Supporting evidence: `C10, M02, M05, M01, M03`
   - Contradicting evidence: `L0189`
   - Assumptions: The 4xx step is dominated by 429s, which is unverified because gateway logs and status-code breakdowns were denied; The burst limit is enforced per client as the change text states; Flat request_rate rules out a volume surge but not a rule change
2. **auth-service** - deployment_regression (confidence 0.30)
   - Mechanism: The v4.0.0 deploy C09 at 16:57:00Z began issuing v2 session tokens, and some validators or clients reject them, invalidating sessions and forcing sign-outs. Session refresh warnings beginning at 17:00:32Z and the auth request_rate step at 17:00 are consistent with this, though no v2 rejection was logged.
   - Supporting evidence: `C09, M10, L0189, L0188`
   - Contradicting evidence: `M07, M08, L0148`
   - Assumptions: Some validators reject v2 tokens although v1 is still accepted, which is unverified; The sign-out symptom is a session-invalidation effect inferred from refresh warnings alone; Auth error_rate staying low means failures occur at the gateway or in clients
3. **api-gateway** - config_error (confidence 0.20)
   - Mechanism: C09 and C10 interact: session invalidation from v2 tokens drives re-logins and retries, and these hit the tightened 20-per-client burst limit, so the 4xx step is a feedback loop across both changes. A single-cause explanation fits the step less well, since the auth error_rate did not rise and the gateway was flat.
   - Supporting evidence: `C09, C10, M10, M02`
   - Contradicting evidence: `M07`
   - Assumptions: Both changes are active during the window; The auth request_rate step reflects re-logins rather than ordinary traffic; Timestamps cannot separate the contributions

## Observed facts
- api-gateway error_rate was 0.36-0.41% from 16:00 to 16:55Z, then 14.83% at 17:00Z, and stayed between 13.6% and 14.6% through 17:30Z. `M02`
- api-gateway request_rate stayed in a 411-432 req/s band across the window with no step at 17:00Z; latency_p99 and CPU/memory also showed no step change. `M05, M03, M01, M04`
- C10 at 16:57:00Z was a completed netops config change lowering the /api/* burst limit from 200 to 20 per client; no config diff or route scope was retrieved. `C10`
- C09 at 16:57:00Z was a completed deploy-bot deploy of auth-service v4.0.0 issuing session tokens in format v2 while v1 is still accepted. `C09`
- auth-service request_rate rose from 82.39 req/s at 16:55Z to 108.05 req/s at 17:00Z and stayed about 104-108 req/s through 17:30Z. `M10`
- auth-service error_rate stayed between 0.06% and 0.15%, with latency and CPU flat across 17:00Z. `M07, M08, M06`
- The first 'token refresh requested for expired or invalid session' WARN appeared at 17:00:32Z; about ten such WARN lines appear roughly every three minutes through 17:30Z. `L0189, L0201, L0217, L0303`
- Only one ERROR line appears in auth-service in the window (a malformed Authorization header rejection at 17:01:01Z). `L0193`
- Health checks at 17:28Z returned HTTP 200 for api-gateway, auth-service, checkout-service and search-service; these shallow checks do not exercise rate limiting or token validation. `H01, H02, H03, H14`
- No revert, rollback, canary or feature-flag record appears for either change in the 16:50-17:30Z window. `C09, C10`

## Assumptions
- The 4xx step is dominated by 429 responses from the burst limit; this is unverified because gateway status codes were not obtained.
- The burst limit is enforced per client as the change description states.
- Auth-service v1 tokens remain accepted by all validators, and some validator rejects v2; the latter is unverified.
- Session-refresh WARN lines reflect expected expiry messages rather than a new rejection pattern.
- The /api/* pattern may or may not cover /api/auth, login and token-refresh routes; this is not confirmed.
- Health checks are shallow and their healthy results do not rule out either failure mode.
- Telemetry after 17:30Z is unavailable, so recovery or continuation is unknown.
- (unverified - no valid evidence cited) All api-gateway log queries were denied for lack of permissions, and the metrics store has no per-status-code series, so the 429, 401 and 403 split is unknown.

## Inferred conclusions
- C10 is a plausible direct cause of the 4xx step through rate-limit rejections, but the 429 share is unverified and the leading hypothesis is below the 0.50 confidence threshold. (confidence 0.40) `C10, M02, M05`
- C09 is a plausible cause of the sign-outs and the auth request_rate step through a re-login surge, but no v2 rejection or auth error rise was observed. (confidence 0.30) `C09, M10, L0189, M07`
- A feedback loop between C09 and C10 cannot be excluded and fits both symptoms; it is not supported by direct evidence either way. (confidence 0.20) `C09, C10, M10, M02`
- The gateway is not failing from resource exhaustion or load, so the cause is most likely a rule or token-handling change rather than traffic volume. (confidence 0.60) `M05, M03, M01, M04`
- Because C09 and C10 share a timestamp and no decisive split is available, the data cannot assign the incident to one change. (confidence 0.70) `C09, C10`

## Remediation
- **immediate** - Revert or temporarily relax the C10 /api/* burst limit back to 200 per client as a reversible mitigation, and monitor gateway error_rate. _(C10 is the leading candidate for the 4xx step and reverting it is low-risk and fast to confirm or rule out.)_
- **immediate** - Obtain api-gateway status-code breakdown (401, 403, 429) and access logs by client and route, after granting the required log permissions. _(The 429 versus 401 split is the decisive missing evidence between H-A and H-B.)_
- **short_term** - Check whether auth-service validators reject v2 tokens; if so, consider rolling back C09 or pinning token issuance to v1 while keeping v1 accepted. _(The sign-out mechanism depends on v2 validation scope, which is unverified.)_
- **short_term** - Run a controlled rollback test reverting C10 alone, then C09 alone, and check whether the 17:00 step recovers. _(A rollback test is the only way to separate two changes that share a timestamp.)_
- **short_term** - Retrieve the C10 config diff and confirm whether /api/auth, login and token-refresh routes fall under the burst limit. _(If refresh traffic is throttled, that would link the two symptoms and change which change is primary.)_
- **long_term** - Make health checks exercise token validation and rate-limit paths. _(Current shallow checks reported healthy during a 14% error rate and cannot detect these failure modes.)_
- **long_term** - Require canary rollout and recorded rollback steps for gateway rate-limit and auth token-format changes, and make changes to one service at a time. _(Simultaneous changes to two services at the same timestamp prevented attribution.)_

## Open questions
- What is the status-code split (401 vs 429) of the 4xx step from 16:55Z onward?
- Does the /api/* burst limit cover login and token-refresh routes?
- Which validators accept v1 and v2 tokens, and do any reject v2?
- Does reverting C10 alone or C09 alone restore the error rate to baseline?
- Is the auth request_rate step caused by re-logins or refresh retries rather than ordinary traffic?
- Did the 4xx step persist after 17:30Z, and did any manual revert occur that is not in change history?

## Data gaps and tool failures (10 shown, 39 reported)
- query_logs(start=2026-09-12T16:00:00Z, end=2026-09-12T17:30:00Z, service=api-gateway, min_level=WARN, limit=50) -> error: Error: access denied: log index 'api-gateway-*' requires elevated permissions
- query_logs(start=2026-09-12T16:00:00Z, end=2026-09-12T17:30:00Z, service=api-gateway, min_level=INFO, contains=sign, limit=30) -> error: Error: access denied: log index 'api-gateway-*' requires elevated permissions
- query_logs(start=2026-09-12T16:00:00Z, end=2026-09-12T17:30:00Z, service=api-gateway, min_level=INFO, contains=too many requests, limit=30) -> error: Error: access denied: log index 'api-gateway-*' requires elevated permissions
- query_logs(start=2026-09-12T16:45:00Z, end=2026-09-12T17:30:00Z, service=api-gateway, min_level=WARN, limit=50) -> error: Error: access denied: log index 'api-gateway-*' requires elevated permissions
- query_logs(start=2026-09-12T16:45:00Z, end=2026-09-12T17:30:00Z, service=api-gateway, min_level=INFO, contains=429, limit=50) -> error: Error: access denied: log index 'api-gateway-*' requires elevated permissions
- api-gateway log index access denied (3 queries), so no status code (401/403/429/other) breakdown, no route or client segment breakdown, and no sign-out or 'too many requests' signatures were obtained.
- The 4xx-specific metric (count by status code) was not available in the metrics returned; only aggregate error_rate was. Breakdown by route or client is unknown.
- Telemetry ends at 17:30Z, so recovery or continuation after that is unknown.
- Health checks are shallow and do not confirm rate-limit or token-validation behaviour, so their 'healthy' results do not rule out either change.
- 30 further gap report(s) in 30 group(s) omitted here (mostly about: returned, counts, 4xx, 429, budget, api-gateway); the full list is in the run record.
