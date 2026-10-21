# Incident report S05

- **Status:** CONCLUSIVE (confidence 0.80, margin 0.72, 9 verified supporting and 2 contradicting evidence items (18%))
- **System:** multi_agent · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** critic_accepted
- **Root cause:** `auth-service` - certificate_expiry (confidence 0.80)

## Summary
Incident S05 is conclusively attributed to an expired certificate for cn=auth.internal, which expired at 2026-09-05T08:59:59Z after two ACME renewal attempts were rate-limited. Checkout-service and api-gateway both began failing on TLS/x509 validation of auth.internal within about a minute of expiry, and auth-service request arrivals collapsed from about 83 to about 3 req/s at 09:00. Checkout error rate rose to about 33% and api-gateway to about 11%, while auth-service's own error and latency metrics stayed flat. The 08:54 checkout v2.15.1 deploy is a weak candidate because its recorded content is static strings and it does not explain the api-gateway x509 errors, though its diff was not verified. The sign-in impact is inferred from the api-gateway 'auth check failed' errors, since logs do not name the sign-in route, and the certificate expiry rests on log text without a direct certificate lookup.

## Conclusion decision
- confidence 0.80, margin 0.72, 9 verified supporting and 2 contradicting evidence items (18%)
- Criteria: top `auth-service / certificate_expiry` confidence 0.80, margin 0.72, 9 verified supporting / 2 contradicting items (18% contradicting); 0 evidence-backed material critic objection(s), 3 non-blocking

## Ranked hypotheses
1. **auth-service** - certificate_expiry (confidence 0.80)
   - Mechanism: The cn=auth.internal certificate expired at 08:59:59Z after ACME renewal was rate-limited (warned 08:05 and 08:20), so TLS validation fails for api-gateway and checkout-service calling auth.internal:8443. Callers rejecting the handshake explain the collapse of auth request arrivals from about 83 to about 3 req/s at 09:00 while auth's own error metrics stay flat.
   - Supporting evidence: `L0018, L0065, L0184, L0185, M10, M12, M02, L0324, L0325`
   - Contradicting evidence: `M07, M08`
   - Assumptions: The certificate served on 8443 is the cn=auth.internal certificate named in the api-gateway log; Log clocks are synchronised across services; Flat auth error and latency metrics reflect requests that never arrive
2. **checkout-service** - deployment_regression (confidence 0.08)
   - Mechanism: The v2.15.1 deploy at 08:54 changed TLS or trust handling in checkout so that auth validation fails from 09:00. This would explain checkout errors only, not the api-gateway x509 errors, and the change is described as static strings only.
   - Supporting evidence: `C09, L0166, L0172`
   - Contradicting evidence: `M12, L0185, M02`
   - Assumptions: The deploy diff touched TLS or trust configuration, which is unverified; api-gateway errors are unrelated to the deploy

## Observed facts
- checkout-service error_rate was 0.26–0.33% from 08:00 to 08:55 and 33.91% at 09:00:00, staying at 30.77–32.85% through 09:30. `M12`
- api-gateway error_rate was 0.34–0.47% from 08:00 to 08:55 and 11.66% at 09:00:00, staying at 10.5–11.76% through 09:30. `M02`
- auth-service request_rate fell from 83.13 req/s at 08:55 to 2.92 req/s at 09:00:00 and stayed near 3 req/s through 09:30; its error_rate (0.07–0.15%) and latency_p99 (about 39–42 ms) showed no step change. `M10, M07, M08`
- auth-service logged WARNs at 08:05:03 and 08:20:17 that renewal of cn=auth.internal failed (ACME order rejected, rate limited), with the current certificate expiring 2026-09-05T08:59:59Z; no successful renewal or certificate reload appears in the auth-service logs through 09:30. `L0018, L0065`
- checkout-service logged its first auth token validation ERROR at 09:00:04 (SSLHandshakeException, PKIX validity check failed, peer auth.internal:8443), with repeated errors through 09:30:00. `L0184, L0325`
- api-gateway logged its first 'auth check failed: x509: certificate has expired' ERROR for cn=auth.internal at 09:00:15, with about 20 such errors through 09:30:00. `L0185, L0324`
- The only change recorded between 08:00 and 09:30 is the checkout-service v2.15.1 deploy at 08:54:00, described as 'update checkout button copy and translations (static strings only)'. `C09`
- Health checks at 09:28 returned HTTP 200 healthy for all listed services, including auth-service on plaintext admin port 8080, which does not exercise the 8443 TLS listener. `H01, H02, H03`
- Before 09:00, checkout and api-gateway logs contain only isolated business-level warnings and errors (one card decline, slow search responses, one client-closed 499), with no comparable error surge; payment-service metrics showed no change at 09:00. `L0044, L0006, L0072, M33, M34`

## Assumptions
- The certificate served on auth.internal:8443 is the cn=auth.internal certificate named in the api-gateway and checkout-service log messages.
- Log clocks are synchronised across checkout-service, api-gateway and auth-service.
- Flat auth-service error and latency metrics reflect requests that never reach the application, consistent with clients failing TLS handshakes.
- The checkout v2.15.1 deploy changed only static strings, as its change record states; the diff itself was not retrieved.
- Sign-in failures are represented by the api-gateway 'auth check failed' errors, although no log line names the sign-in route.

## Inferred conclusions
- The root cause is the expiry of the cn=auth.internal certificate at 08:59:59Z, following two rate-limited ACME renewal attempts, which made TLS validation fail for api-gateway and checkout-service calling auth.internal:8443. (confidence 0.80) `L0018, L0065, L0184, L0185, M10, M12, M02`
- Sign-in and checkout failures share a single dependency (auth.internal certificate) rather than being two separate faults. (confidence 0.70) `L0185, L0184`
- The 08:54 checkout v2.15.1 deploy is unlikely to be the direct cause: error onset lags the certificate expiry, and the api-gateway x509 errors are not explained by a checkout change. (confidence 0.80) `C09, M12, L0166, L0185`
- Auth-service's flat error metrics are most likely explained by requests failing TLS handshakes before reaching its application, so they do not rule out the server-side certificate. (confidence 0.60) `M10, M07, L0018`
- Payment-service is not the source of the incident; its metrics are unchanged and checkout errors are TLS errors on the auth hop. (confidence 0.60) `M33, M34, L0184`
- Sign-in impact is inferred to be the api-gateway auth check failures, since they reference the same expired certificate, but the route is not named in the logs. (confidence 0.55) `L0185, L0324`

## Remediation
- **immediate** - Immediately issue and deploy a valid certificate for cn=auth.internal to the auth-service 8443 listener, reloading the listener, using a manual or alternate CA path if ACME remains rate-limited. _(The expired certificate is the established cause, and renewing it should restore TLS validation for api-gateway and checkout-service.)_
- **immediate** - Verify recovery by confirming that auth-service request_rate returns to about 80 req/s and that checkout and api-gateway error rates return to baseline (about 0.3%). _(Recovery should be measured against the same metrics that showed the outage, not inferred from the renewal alone.)_
- **immediate** - Directly confirm the served certificate's notAfter on port 8443 and check the auth-service TLS listener and reload logs after 09:00. _(The expiry timestamp currently rests on log text, and this lookup would close the main verification gap.)_
- **short_term** - Pull the checkout v2.15.1 diff and confirm it contains no TLS, trust store or auth client changes. _(The deploy has not been fully excluded because its diff was unavailable, so this check settles the remaining alternative.)_
- **short_term** - Add certificate expiry monitoring and alerting for all internal certificates, with alerts well before expiry and on ACME renewal failures. _(Renewal failures were logged at 08:05 and 08:20, roughly 40 minutes before expiry, and no alert acted on them.)_
- **short_term** - Fix the ACME renewal configuration and rate-limit handling so renewals are retried with backoff and do not exhaust the rate limit. _(The renewal was blocked by rate limiting, so the renewal process itself needs correction to prevent recurrence.)_
- **long_term** - Add deep health checks that exercise the 8443 TLS listener and the sign-in and checkout auth paths, instead of relying on the plaintext 8080 /health probe. _(The current health checks reported all services healthy during a full outage, so they do not detect this failure class.)_
- **long_term** - Standardise certificate lifecycle management across services, including inventory, ownership and automated rotation, to reduce the chance of similar expiries such as the 2026-06-11 payment-service incident. _(A past incident had a similar expired-certificate root cause, which points to a systemic gap rather than a one-off.)_

## Open questions
- What is the exact notAfter of the certificate currently served on auth.internal:8443, and was it the same certificate named in the logs?
- Did auth-service log any TLS listener errors on 8443 that the queries missed, or do clients fail before reaching the server?
- Does the checkout v2.15.1 diff touch TLS, trust store or auth client configuration?
- Are HTTP status codes and per-endpoint error splits available to confirm that sign-in requests are failing at the same rate as checkout?
- Did the session store show any telemetry change at 09:00, since it had no data in this investigation?

## Data gaps and tool failures (10 shown, 29 reported)
- No HTTP status codes were returned for either service, so the status-code breakdown is unknown.
- Log lines do not name the endpoint for the auth failures, so checkout-versus-sign-in endpoint attribution is inferred, not measured.
- No metrics were queried for auth-service (cert expiry, error rate, latency), and no metrics were queried for checkout-service or api-gateway beyond error_rate (no latency, request rate or CPU), so those signals are unchecked.
- Certificate expiry was inferred from log text; the issuing CA and deployment history of the cert were not checked.
- Tool budget was exhausted before any deploy diff, change history or auth-service error-rate query could be made, so the deploy's TLS-related content is unverified.
- Coverage is 08:00–09:30 only; the earlier ACME failure before 08:00 and any previous similar incidents were not examined.
- Change history covers only the 08:00-09:30 window for this check. Changes earlier than 08:00 (for example, the previous 7 days) were not reviewed for this task, so a slow-acting cause could be missed.
- Health checks are from 09:28 only and are shallow; no deep or synthetic checks on sign-in or checkout paths were available.
- No telemetry (error logs, per-endpoint error breakdown, or timing of first error) was retrieved, so the exact onset of errors relative to the 08:54 deploy is not confirmed.
- 20 further gap report(s) in 20 group(s) omitted here (mostly about: tls, error, api-gateway, certificate, query, auth-service); the full list is in the run record.
