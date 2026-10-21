# Incident report S05

- **Status:** CONCLUSIVE (confidence 0.90, margin 0.85, 6 verified supporting and 1 contradicting evidence items (14%))
- **System:** baseline · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** agent_finished
- **Root cause:** `auth-service` - certificate_expiry (confidence 0.90)

## Summary
Checkout and sign-in failures start at 09:00 UTC because the auth.internal certificate expired at 08:59:59 UTC. Auth-service's ACME renewal was rate-limited, so the certificate was never renewed, and both api-gateway and checkout-service now fail TLS validation against auth-service. checkout-service error rate jumped from 0.26% at 08:55 to 33.91% at 09:00. The 08:54 checkout deploy (v2.15.1, static strings only) is coincidental: its timing is close, but the failure signature is TLS, not application code. Health checks report healthy because they hit plaintext /health endpoints and do not exercise TLS.

## Conclusion decision
- confidence 0.90, margin 0.85, 6 verified supporting and 1 contradicting evidence items (14%)
- Criteria: top `auth-service / certificate_expiry` confidence 0.90, margin 0.85, 6 verified supporting / 1 contradicting items (14% contradicting); 0 evidence-backed material critic objection(s), 0 non-blocking

## Ranked hypotheses
1. **auth-service** - certificate_expiry (confidence 0.90)
   - Mechanism: The auth.internal certificate expired at 08:59:59Z. Its ACME renewal was rate-limited, so auth-service kept serving the expired certificate. Callers api-gateway and checkout-service reject the TLS handshake, so token validation fails and sign-in and checkout break.
   - Supporting evidence: `L0018, L0065, L0184, L0185, M12, L0254`
   - Contradicting evidence: `H02`
   - Assumptions: The served certificate is the one that expired at 08:59:59Z.; Health checks do not exercise TLS.
2. **checkout-service** - deployment_regression (confidence 0.05)
   - Mechanism: The v2.15.1 deploy at 08:54 may have changed TLS or trust-store handling, causing checkout to reject a valid certificate.
   - Supporting evidence: `C09`
   - Contradicting evidence: `M12, L0184, L0185`
   - Assumptions: The deploy may have included non-static changes not in the description.
3. **payment-service** - certificate_expiry (confidence 0.03)
   - Mechanism: An expired certificate on a downstream service could cause checkout failures, as in past incident P06.
   - Supporting evidence: `P06`
   - Contradicting evidence: `H11, L0044`
   - Assumptions: Payment calls are the source of the errors. No payment TLS errors were found in the logs I queried.

## Observed facts
- checkout-service error_rate was 0.26% at 08:55 and 33.91% at 09:00, with a max at 09:00 and 30.77% at 09:30. `M12`
- auth-service logged twice that certificate renewal for cn=auth.internal failed with ACME order rejected (rate limited); current certificate expires 2026-09-05T08:59:59Z, at 08:05:03 and 08:20:17. `L0018, L0065`
- checkout-service's first PKIX 'validity check failed' error against auth.internal:8443 occurred at 09:00:04, and 45 such errors appear in the window. `L0184, L0190`
- api-gateway logged 'auth check failed: x509 certificate has expired' for cn=auth.internal from 09:00:15 onward, 20 errors in the window. `L0185, L0254`
- The only change in the window is checkout-service deploy v2.15.1 at 08:54:00, described as static copy and translation changes; no auth-service certificate or deploy change appears. `C09`
- The health check for auth-service returns 200 on the plaintext admin port 8080, and the checkout and gateway health checks return 200. `H02, H03, H01`
- checkout-service CPU (about 40-43%), memory (about 56-60%), latency p99 (about 307-332 ms) and request rate (about 82-87 req/s) stayed flat across 08:00-09:30. `M11, M13, M14, M15`
- A past incident (2026-06-11) had checkout 5xx errors caused by an expired TLS certificate on payment-service, with the fix being renewal plus expiry alerting. `P06`

## Assumptions
- The 08:59:59Z expiry in the auth-service warning is the certificate now served on auth.internal:8443, since the gateway and checkout errors cite the same expiry.
- The auth-service ACME rate limit has not lifted, so the certificate has not been renewed by 09:30.
- The health checks do not exercise TLS on the 8443 listener, as implied by the plaintext 8080 health detail.
- The 33% error rate is driven by auth validation failures and not by the single card-decline error.

## Inferred conclusions
- Root cause: expired auth.internal certificate on auth-service, which failed to renew because of ACME rate limiting. This breaks TLS token validation in checkout-service and the api-gateway auth check, causing sign-in and checkout failures. (confidence 0.90) `L0018, L0065, L0184, L0185, M12`
- The checkout-service v2.15.1 deploy at 08:54 is unlikely to be the cause: it changed only static strings, the errors are TLS validation errors, and the error rate was flat until 09:00. (confidence 0.85) `C09, M12, L0184`
- The lack of alerting on certificate expiry and the TLS-blind health checks let this go unnoticed until the outage, and the renewal failures at 08:05 and 08:20 gave roughly 55 minutes of warning. (confidence 0.60) `L0018, L0065, H02`

## Remediation
- **immediate** - Install a valid certificate on auth-service now, either by manually issuing or importing one from the internal CA, or by using an alternate ACME account or an override to bypass the rate limit. Then restart or reload the listener on 8443. _(The expired certificate causes all token validation to fail, so this directly restores sign-in and checkout.)_
- **immediate** - Confirm that checkout-service and api-gateway recover, and that the error rate returns to about 0.3%. _(Verifies the mitigation worked.)_
- **short_term** - Fix the ACME rate-limit failure and retry renewal with backoff, and check the cert-manager and ACME account configuration. _(Prevents the certificate from expiring again.)_
- **short_term** - Add certificate-expiry alerts at 30, 14 and 7 days and alerts on renewal failure. _(Renewal failures at 08:05 and 08:20 were logged as WARN and did not page anyone.)_
- **long_term** - Make health checks exercise the TLS listener on 8443 and validate the certificate expiry date. _(Plaintext /health returned healthy during the outage.)_
- **short_term** - Investigate the v2.15.1 deploy only to rule it out, and do not roll back unless errors persist after the cert fix. _(Avoids a rollback that would not fix the cause.)_

## Open questions
- Why was the ACME order rate-limited, and what triggered the excessive renewal attempts?
- Did anyone receive the renewal-failure warnings, and was there an alerting gap?
- Is the certificate on other internal listeners (for example payment-service) also near expiry?
- Why does the 08:05 renewal failure report expiry 08:59:59 when the 'expires' timestamp was not flagged earlier?

## Data gaps and tool failures (0 shown, 0 reported)
_None._
