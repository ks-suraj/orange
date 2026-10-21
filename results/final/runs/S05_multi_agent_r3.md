# Incident report S05

- **Status:** CONCLUSIVE (confidence 0.75, margin 0.65, 7 verified supporting and 0 contradicting evidence items (0%))
- **System:** multi_agent · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** critic_accepted
- **Root cause:** `auth-service` - certificate_expiry (confidence 0.75)

## Summary
Checkout-service and api-gateway error rates jumped at 09:00 UTC, well after the 08:54 checkout deploy, and both services began logging certificate failures for auth.internal within seconds of its stated notAfter of 08:59:59Z. The system determination is conclusive at confidence 0.75, with the leading hypothesis being expiry of the auth.internal serving certificate. Errors persisted through 09:30 with no contradicting evidence recorded. Served-certificate identity (subject, notAfter, fingerprint) was never retrieved, so the certificate-to-expiry link is supported by log text but not directly verified. The checkout deploy v2.15.1 is a weak lead, described as copy-only and not diffed. Sign-in and checkout failures share the auth.internal dependency rather than being independent faults.

## Conclusion decision
- confidence 0.75, margin 0.65, 7 verified supporting and 0 contradicting evidence items (0%)
- Criteria: top `auth-service / certificate_expiry` confidence 0.75, margin 0.65, 7 verified supporting / 0 contradicting items (0% contradicting); 0 evidence-backed material critic objection(s), 3 non-blocking

## Ranked hypotheses
1. **auth-service** - certificate_expiry (confidence 0.75)
   - Mechanism: The auth.internal serving certificate reached notAfter at 08:59:59Z, so TLS clients validating it fail from 09:00. checkout-service fails PKIX validity checks on auth.internal:8443 from 09:00:04Z and api-gateway fails x509 auth checks on cn=auth.internal from 09:00:15Z, producing the 09:00 error step in both services and the drop in auth request_rate to about 3 req/s.
   - Supporting evidence: `L0184, L0185, L0324, M12, M02, M10, M07`
   - Contradicting evidence: none
   - Assumptions: The certificate served on auth.internal:8443 is the one whose notAfter is 08:59:59Z, which is not directly verified; Client error text accurately names the cause; auth-service request_rate drop reflects clients failing TLS before reaching auth
2. **auth.internal** - infrastructure_failure (confidence 0.10)
   - Mechanism: Clock skew or a different served certificate on auth.internal:8443 causes PKIX validity failures starting at 09:00 without a true expiry, with the gateway error text misleading. Both clients would still fail in the same bucket.
   - Supporting evidence: `L0184, L0185`
   - Contradicting evidence: `L0185`
   - Assumptions: Client clocks or served certificate differ from what error text states; No clock-skew query was run
3. **checkout-service** - deployment_regression (confidence 0.08)
   - Mechanism: The v2.15.1 deploy at 08:54:00Z changed certificate or trust-store validation in checkout so it rejects a valid auth.internal certificate. This would explain checkout errors, but not the api-gateway x509 expiry errors, and the six-minute gap before onset makes it less likely.
   - Supporting evidence: `C09, L0184`
   - Contradicting evidence: `M12, M02, L0185`
   - Assumptions: The deploy diff contains more than its described static-string changes; api-gateway failures are a separate coincidence

## Observed facts
- checkout-service error_rate was about 0.28-0.33% from 08:00 through 08:45, then 33.91% at 09:00 and 30.77-32.85% through 09:30. `M12`
- api-gateway error_rate was about 0.37-0.47% through 08:45, then 11.66% at 09:00 and 10.5-11.76% through 09:30. `M02`
- The first checkout-service error at 09:00:04Z reads PKIX path validation failed, validity check failed (peer auth.internal:8443). `L0184`
- The first api-gateway error at 09:00:15Z reads x509 certificate has expired, current time is after 2026-09-05T08:59:59Z (cn=auth.internal). `L0185`
- api-gateway logged 20 expiry errors from 09:00:15Z to 09:30:00Z, and checkout-service ERROR lines continue through 09:30:00Z. `L0324, L0325`
- auth-service request_rate fell from about 83 req/s to about 2.9 req/s at 09:00Z and stayed near 3 req/s through 09:30Z. `M10`
- auth-service error_rate, latency, CPU and memory stayed flat across the window, and its logs contain no cert, handshake or x509 lines for 08:00-09:30Z. `M07, M06, M08, M09`
- The only change in the 08:00-09:30Z window is checkout-service deploy v2.15.1 at 08:54:00Z, described as 'static strings only'; no cert-manager, trust-store or auth.internal renewal record was returned. `C09`
- Health checks at 09:28Z returned HTTP 200 for all services, but these are shallow /health probes, and the auth-service probe targets plaintext port 8080. `H01, H02, H03`

## Assumptions
- The certificate served on auth.internal:8443 is the one whose notAfter is 08:59:59Z; this was not directly verified by subject, notAfter or fingerprint.
- The client error text accurately names the cause (expiry rather than clock skew or a different certificate).
- The auth-service request_rate drop reflects clients failing TLS before reaching auth-service.
- The v2.15.1 deploy contains only the described copy and translation changes; the code diff was not checked.
- The health checks do not exercise TLS or token validation, so their green results do not exclude the failure.
- Certificate-related events not captured in the 7-day change history (for example failed renewals earlier than that) are not excluded.

## Inferred conclusions
- The leading cause is expiry of the auth.internal serving certificate at 08:59:59Z, which causes TLS validation failures in checkout-service and api-gateway from 09:00 onward; this is the system's conclusive determination. (confidence 0.75) `L0184, L0185, L0324, M12, M02, M10`
- The 08:54 checkout deploy is unlikely to be the direct trigger, because error rates stayed normal for six minutes after it and the errors cite certificate expiry rather than a checkout code path. (confidence 0.70) `C09, M12, L0184`
- Sign-in and checkout failures share one upstream cause at auth.internal rather than being two separate faults, given that both services fail on the same certificate within 11-15 seconds. (confidence 0.75) `L0184, L0185`
- Clock skew or a different served certificate on auth.internal is a lower-probability alternative that the available evidence does not rule out. (confidence 0.10) `L0184, L0185`

## Remediation
- **immediate** - Renew or replace the auth.internal serving certificate immediately and reload auth-service so it serves a valid certificate. _(The expired certificate is the leading cause of the 33% checkout and 11% gateway error rates, and no other mitigation addresses it.)_
- **immediate** - Verify the served certificate on auth.internal:8443 (subject, notAfter, fingerprint) after renewal and confirm that checkout and api-gateway errors stop. _(The certificate identity is unverified, and post-fix confirmation is the only check that settles it.)_
- **immediate** - Hold further checkout-service rollouts until v2.15.1 is diffed for trust-store or TLS-validation changes. _(The deploy is a weak lead and its code diff was never checked, so a rollback decision should rest on evidence.)_
- **short_term** - Find out why cert-manager did not renew auth.internal before 08:59:59Z and fix that renewal path. _(Renewal history was not retrieved, so the failure mode behind the missed renewal is unknown.)_
- **short_term** - Add certificate expiry alerting for auth.internal and other internal serving certificates with lead time before notAfter. _(The incident was detected only after the certificate had already expired and 33% of checkout requests had failed.)_
- **short_term** - Make the auth-service health check exercise the TLS serving path on 8443 and validate certificate validity. _(The current plaintext /health check on 8080 reported healthy during a full outage.)_
- **long_term** - Add auth-service logging for TLS handshake and certificate events so that rejected clients are visible on the server side. _(auth-service logged nothing for the failure, which made the server-side view hard to confirm.)_
- **long_term** - Run a fleet-wide certificate expiry audit and check payment-service for the same PKIX error, following the P06 pattern. _(The payment-service check was not run, and P06 shows a similar expiry failure has happened before.)_

## Open questions
- What are the subject, notAfter and fingerprint of the certificate served on auth.internal:8443, and does it match the certificate that expired at 08:59:59Z?
- Why did cert-manager fail to renew auth.internal before expiry, and does a renewed certificate exist?
- Does the v2.15.1 code diff contain any trust-store or TLS-validation change?
- Do payment-service or other clients log the same PKIX or x509 error, and do any hosts show clock skew around 09:00Z?
- What are the HTTP status codes and sign-in endpoint error rates, since the log records carry no status or route fields?

## Data gaps and tool failures (10 shown, 40 reported)
- Log records contain no HTTP status code or endpoint/route field for the auth and checkout errors, so the status-code breakdown and sign-in vs checkout endpoint split could not be confirmed directly.
- checkout-service ERROR logs were truncated to 30 of 48 matching lines (the 09:00–09:20 range is shown, and later lines are not included), so the tail of the error stream after 09:19:45Z was not sampled.
- The window is 08:00–09:30 and the expiry timestamp is outside it, so the certificate's issuance and renewal history and the 08:54 deploy's contents were not checked with the 6 tool calls available.
- No metrics were queried for auth-service or the auth.internal certificate itself, so the auth-service side of the failure is not directly observed.
- Health-check history around 09:00 UTC is not available; only a single 09:28Z snapshot was returned.
- Deploy record lacks rollout progress and per-instance status; the change tool does not show rollback state beyond absence of a rollback record.
- Change history was not queried over a longer lookback for auth-service or api-gateway config (only the 08:00–09:30 window was checked).
- Health checks may be shallow (HTTP /health only), so they do not confirm sign-in or payment success paths.
- Telemetry for error-rate breakdown by upstream was not available to this role.
- 31 further gap report(s) in 31 group(s) omitted here (mostly about: certificate, query, auth-service, tls, error, auth.internal); the full list is in the run record.
