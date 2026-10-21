# Incident report S05

- **Status:** CONCLUSIVE (confidence 0.75, margin 0.68, 9 verified supporting and 1 contradicting evidence items (10%))
- **System:** multi_agent · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** max_rounds_reached
- **Root cause:** `auth-service` - certificate_expiry (confidence 0.75)

## Summary
Incident S05 was determined conclusive at confidence 0.75: the expired auth.internal certificate is the leading root cause, with checkout-service and api-gateway failing TLS/x509 validation against auth.internal from 09:00 UTC. The auth.internal certificate's renewal was rejected as ACME rate-limited at 08:05 and 08:20 and was not replaced before its 08:59:59Z expiry. Checkout error rate rose from about 0.3% to 33.9% and gateway error rate from about 0.4% to 11.7% at 09:00. The 08:54 checkout v2.15.1 deploy preceded onset by six minutes but is described as static strings only and cannot produce gateway x509 errors. Caveats: the certificate actually served on port 8443 and its notAfter were never verified, the roughly 96% auth request-rate drop is larger than client error shares would explain, and checkout logs contain no x509 matches, so the 33% checkout error rate is not fully reconciled.

## Conclusion decision
- confidence 0.75, margin 0.68, 9 verified supporting and 1 contradicting evidence items (10%)
- Criteria: top `auth-service / certificate_expiry` confidence 0.75, margin 0.68, 9 verified supporting / 1 contradicting items (10% contradicting); 0 evidence-backed material critic objection(s), 5 non-blocking

## Ranked hypotheses
1. **auth-service** - certificate_expiry (confidence 0.75)
   - Mechanism: The auth.internal certificate expired at 08:59:59Z after ACME renewal was rate-limited at 08:05 and 08:20 and never replaced. From 09:00 api-gateway and checkout-service fail PKIX/x509 validation against auth.internal, producing the step-up in checkout errors (0.3% to 33.9%) and gateway errors (0.4% to 11.7%) and failing token validation through auth; the auth request-rate collapse from about 80 to about 3 req/s coincides with the handshake failures.
   - Supporting evidence: `L0018, L0065, L0184, L0185, L0194, M12, M02, M10, M07, M08`
   - Contradicting evidence: `M10`
   - Assumptions: The 08:59:59Z expiry in auth and client logs refers to the certificate served on auth.internal:8443.; Client error counts reflect failed auth calls, and the request-rate drop is largely handshake failures before requests reach auth-service.
2. **checkout-service** - deployment_regression (confidence 0.07)
   - Mechanism: The v2.15.1 deploy at 08:54 altered client-side trust or TLS handling for auth.internal, so checkout calls fail validation from 09:00. This would explain checkout errors but not the gateway's identical x509 expiry messages from a separate component.
   - Supporting evidence: `C09, M12`
   - Contradicting evidence: `L0185, L0194, L0202, L0018, L0065`
   - Assumptions: The 'static strings only' description may be inaccurate; the v2.15.1 diff was not retrieved.; Gateway errors would need a separate explanation under this hypothesis.
3. **auth-service** - dependency_failure (confidence 0.04)
   - Mechanism: A non-TLS fault inside auth-service sign-in or token path rejects requests and raises errors on both callers. Auth error rate and latency are flat and it logs no WARN or ERROR from 08:50 to 09:30, so the data does not support it.
   - Supporting evidence: `M10`
   - Contradicting evidence: `M07, M08, L0184, L0185`
   - Assumptions: Auth-side logging captures all sign-in failures, which is not fully verified.

## Observed facts
- checkout-service error_rate was about 0.26-0.33% from 08:00 to 08:55, then 33.91% at 09:00:00 and 30.77% at 09:30. `M12`
- api-gateway error_rate was about 0.34-0.47% before 09:00, then 11.66% at 09:00:00 and 10.95% at 09:30. `M02`
- auth-service logged WARN at 08:05:03Z and 08:20:17Z that renewal for cn=auth.internal failed (ACME order rejected, rate limited) and that the current certificate expires 2026-09-05T08:59:59Z. `L0018, L0065`
- api-gateway ERROR 'x509: certificate has expired' citing cn=auth.internal first appears at 09:00:15Z and recurs through 09:30:00Z (20 shown). `L0185, L0324`
- checkout-service ERROR 'PKIX path validation failed ... validity check failed (peer auth.internal:8443)' first appears at 09:00:04Z and recurs through 09:30:00Z (45 lines in window). `L0184, L0325`
- auth-service request_rate was about 79-83 req/s from 08:00 to 08:55 and dropped to 2.92 req/s at 09:00:00, staying near 3 req/s through 09:30. `M10`
- auth-service error_rate (0.07-0.15%), p99 latency (39-42 ms) and CPU stayed flat across 09:00, and auth-service logged no WARN or ERROR from 08:50 to 09:30. `M07, M08, M06`
- The only change in the 00:00-09:30 window affecting checkout is v2.15.1 at 08:54:00Z, described as 'update checkout button copy and translations (static strings only)'; no auth-service or api-gateway change occurred in the window. `C09, C08`
- All service health checks returned HTTP /health 200 at 09:28Z, but auth-service was checked on plaintext admin port 8080 and checks are shallow. `H01, H02, H03`
- checkout-service logged zero WARN or ERROR lines containing 'x509' from 08:00 to 09:30. `L0184`
- payments-db metrics (connections, CPU, latency, replication lag, disk) stayed in normal ranges across 08:45-09:30. `M37, M38, M39, M40, M41`

## Assumptions
- The 08:59:59Z expiry in auth and client logs refers to the certificate served on auth.internal:8443.
- Client error counts reflect failed auth calls, and the auth request-rate drop is largely handshake failures before requests reach auth-service.
- The v2.15.1 description 'static strings only' is accurate; the diff was not retrieved.
- Auth-side logging captures all sign-in failures.
- Checkout's zero x509 log matches reflect a log-field or message-format difference rather than the absence of the same failure.

## Inferred conclusions
- The expired auth.internal certificate is the root cause of the sign-in and checkout failures, because errors start 15 seconds after expiry and every gateway error cites that certificate. (confidence 0.75) `L0065, L0185, L0184, M12, M02`
- The ACME rate-limit rejections before expiry explain why the certificate was not renewed in time; the renewal failed without a recorded successful reissue. (confidence 0.60) `L0018, L0065`
- The checkout v2.15.1 deploy is unlikely to be the cause, since its described change does not touch TLS or auth and cannot produce gateway x509 errors, though the diff remains unverified. (confidence 0.70) `C09, L0185`
- Auth-side degradation did not precede the failures; the auth request-rate drop is consistent with clients failing handshakes before reaching auth-service. (confidence 0.60) `M10, M07, M08`
- The sign-in impact is inferred from the gateway and checkout auth-check failures, since no sign-in route-level errors were observed. (confidence 0.50) `L0185, L0184`
- A non-TLS fault in auth-service is unlikely given flat error and latency metrics and no auth-side warnings after 08:50. (confidence 0.40) `M07, M08, M10`

## Remediation
- **immediate** - Immediately renew or reissue the auth.internal certificate (manually if ACME remains rate-limited) and reload auth-service so it serves a valid certificate on port 8443. _(The leading cause is an expired certificate causing client handshake failures on both checkout and gateway.)_
- **immediate** - Verify the served certificate on auth.internal:8443 and its notAfter value after reload, and confirm the x509 and PKIX errors stop and error rates return to baseline. _(The served certificate was never checked, so the expiry link is not yet confirmed at the endpoint.)_
- **short_term** - Roll back or hold checkout-service v2.15.1 only if the diff shows TLS or truststore changes; otherwise leave it. _(The deploy timing is unexplained by content and the diff has not been reviewed.)_
- **short_term** - Add certificate expiry monitoring and alerting for auth.internal and all client-facing certificates with thresholds well before notAfter. _(Expiry went unnoticed despite two failed renewal warnings before the outage.)_
- **long_term** - Alert on repeated ACME renewal failures and review rate-limit handling and renewal lead time in the certificate automation. _(Renewal failed silently for about 55 minutes before expiry, and ACME rate limits caused the failure.)_
- **long_term** - Extend health checks to exercise the TLS sign-in and token validation path on the serving port rather than plaintext /health on port 8080. _(Current health checks reported healthy during a full outage.)_
- **short_term** - Collect checkout-service and gateway request-level status codes and handshake error breakdowns by caller to explain the traffic drop and checkout error share. _(The request-rate collapse exceeds client error shares and the checkout x509 zero-match is unexplained.)_

## Open questions
- Does the certificate served on auth.internal:8443 have notAfter 2026-09-05T08:59:59Z, confirming the expiry on the live endpoint?
- Why do checkout-service logs show zero x509 matches while the alert and PKIX lines describe the same validity failure (log-field or message mismatch)?
- What accounts for the roughly 96% auth request-rate drop beyond the client error shares, and are other callers affected?
- Did any renewal or reload occur after 08:20:17Z, using search terms beyond 'acme'?
- What does the v2.15.1 diff actually change, and does it touch TLS, truststore or auth client config?
- What are the session-store and checkout-db states, which had no metrics in this telemetry?

## Data gaps and tool failures (10 shown, 33 reported)
- Past-incident search returned 3 of 6 matches; no per-service history for auth-service or the TLS state of its endpoints was retrieved. (reported 2x)
- No endpoint-level breakdown: the logs do not show HTTP status codes or routes for checkout-service or the sign-in and checkout paths in the 08:00–09:30 window.
- Metrics show error_rate only. No request_rate, latency or status-code series were queried for either service.
- No logs from auth-service after 08:48 were retrieved beyond the WARN level, so the state of the renewal after 08:20 and any post-expiry auth-service errors are not visible.
- The 08:54 deploy's contents and change record were not queried. Whether it touched TLS or cert config is unknown.
- Diff contents of v2.15.1 were not returned; only a free-text description is available, so the claim of 'static strings only' is unverified.
- The change history has no records of auth-service changes in this window, but this tool does not show whether config or secret rotations are logged there. Coverage is therefore unknown.
- Health checks are shallow (/health only) and do not exercise sign-in or checkout paths; no telemetry (error logs, per-endpoint metrics) was queried by this role.
- No metrics tool exists in this toolset, so error rates, latency and per-endpoint status for 08:45-09:30 were not checked.
- 23 further gap report(s) in 23 group(s) omitted here (mostly about: auth-service, checked, query, log, api-gateway, certificate); the full list is in the run record.
