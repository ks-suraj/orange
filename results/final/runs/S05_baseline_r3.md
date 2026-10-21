# Incident report S05

- **Status:** CONCLUSIVE (confidence 0.90, margin 0.85, 6 verified supporting and 1 contradicting evidence items (14%))
- **System:** baseline · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** agent_finished
- **Root cause:** `auth-service` - certificate_expiry (confidence 0.90)

## Summary
Checkout and sign-in failures began when the TLS certificate for auth.internal expired at 08:59:59Z. Its ACME renewal had been rejected (rate limited) since 08:05, and from 09:00:04Z checkout-service's calls to auth-service fail with PKIX 'validity check failed' errors. The error rate jumped from about 0.3% to 33.9% in the 09:00 window. The 08:54 checkout deploy (static copy changes) does not fit the symptoms: its timing is earlier, and the failure is a TLS validation error, not a change in checkout code. Health checks reported healthy because they run over plaintext port 8080, so they do not exercise the TLS path. Confidence in the certificate-expiry cause is high, but I have not checked the api-gateway logs or the certificate's own metadata, so that is a data gap.

## Conclusion decision
- confidence 0.90, margin 0.85, 6 verified supporting and 1 contradicting evidence items (14%)
- Criteria: top `auth-service / certificate_expiry` confidence 0.90, margin 0.85, 6 verified supporting / 1 contradicting items (14% contradicting); 0 evidence-backed material critic objection(s), 0 non-blocking

## Ranked hypotheses
1. **auth-service** - certificate_expiry (confidence 0.90)
   - Mechanism: The auth.internal certificate expired at 08:59:59Z after ACME renewal was rate-limited. checkout-service (and api-gateway) fail PKIX validation on each call to auth-service:8443, so token validation fails and sign-in and checkout return errors.
   - Supporting evidence: `L0018, L0065, L0184, L0190, M12, P06`
   - Contradicting evidence: `H02`
   - Assumptions: The expired cert is the one served on port 8443.; Shallow health checks explain the 'healthy' status.
2. **checkout-service** - deployment_regression (confidence 0.05)
   - Mechanism: The v2.15.1 deploy at 08:54 introduced an error that causes checkout failures.
   - Supporting evidence: `C09`
   - Contradicting evidence: `M12, L0184, L0190, M11, M13, M14, M15`
   - Assumptions: The 'static strings only' description is accurate.
3. **payment-service** - certificate_expiry (confidence 0.03)
   - Mechanism: An expired certificate on payment-service's TLS path causes checkout failures, as in the 2026-06-11 incident.
   - Supporting evidence: `P06`
   - Contradicting evidence: `L0184, L0190, L0243`
   - Assumptions: Payment-service TLS is not checked in the telemetry here.

## Observed facts
- checkout-service error_rate was about 0.26–0.33% from 08:00 to 08:55, then 33.91% at 09:00 and 30.77–32.85% through 09:30. `M12`
- auth-service logged that certificate renewal for cn=auth.internal failed (ACME order rejected, rate limited) at 08:05:03 and 08:20:17, and that the current certificate expires 2026-09-05T08:59:59Z. `L0018, L0065`
- checkout-service logged 'auth-service token validation failed: SSLHandshakeException: PKIX path validation failed ... validity check failed (peer auth.internal:8443)' starting at 09:00:04Z, with 45 such errors in the window. `L0184, L0190, L0243`
- The deploy v2.15.1 to checkout-service at 08:54:00Z was described as 'update checkout button copy and translations (static strings only)'. `C09`
- checkout-service cpu (about 39–43%), memory (about 56–60%), request rate (about 82–87 req/s) and p99 latency (about 307–332 ms) stayed flat across 08:00–09:30. `M11, M13, M14, M15`
- The health check for auth-service is HTTP /health 200 on the plaintext admin port 8080, and all services show 'healthy' at 09:28:00Z. `H02`
- A past incident (2026-06-11) had checkout 5xx errors caused by an expired TLS certificate on payment-service after a cert-manager misconfiguration. `P06`
- A config change on 2026-08-31 lowered the log level for /healthz on auth-service; no other auth-service change appears in the last 7 days. `C02`

## Assumptions
- The auth.internal certificate that expired at 08:59:59Z is the one served on auth-service port 8443 that checkout-service validates against.
- The health checks do not exercise TLS, so 'healthy' does not contradict the certificate failure.
- api-gateway's errors (also alerting) stem from its sync dependency on checkout-service and auth-service, though its logs were not queried.
- The one card-declined and one slow-inventory log line are background noise and not part of the incident.

## Inferred conclusions
- The auth-service certificate expired at 08:59:59Z because its ACME renewal was rate-limited and never succeeded, and this expiry is the root cause of the checkout and sign-in failures. (confidence 0.90) `L0018, L0065, L0184, M12`
- The checkout v2.15.1 deploy at 08:54 is unlikely to be the cause: its change is static copy, the errors are TLS validation failures, and the error rate was flat until 09:00, six minutes after the deploy. (confidence 0.85) `C09, M12, L0184`
- Monitoring gap: the health checks were shallow, so the expired certificate went undetected and the service showed as healthy during the outage. (confidence 0.75) `H02, H03`

## Remediation
- **immediate** - Immediately install a valid certificate for auth.internal (manually issue or import one, or use a fallback CA) on auth-service port 8443 and restart or reload it. _(Restores TLS validation for checkout-service and api-gateway calls to auth-service.)_
- **immediate** - Verify that checkout sign-in and checkout succeed end-to-end, and that checkout error_rate returns to about 0.3%. _(Confirms recovery, since health checks are shallow.)_
- **short_term** - Reset or back off the ACME rate limit and rerun renewal for cn=auth.internal. _(Stops the cert from expiring again once the temporary certificate runs out.)_
- **short_term** - Add certificate-expiry alerting for auth.internal and other internal certs, and alert on renewal failures. _(The renewal failures from 08:05 gave about 55 minutes of warning and nobody acted on them.)_
- **long_term** - Make health checks exercise the TLS port (8443) with a real handshake. _(The plaintext admin-port check reported healthy during the outage.)_
- **long_term** - Review renewal rate-limit handling and cert-manager configuration, following the 2026-06-11 incident. _(Avoids repeat expiry from the same class of failure.)_

## Open questions
- Why did ACME renewal get rate-limited, and what caused the repeated attempts?
- Do the api-gateway logs show the same PKIX errors, and what do they show for its calls to auth-service?
- Is the 08:54 checkout deploy truly unrelated, or did it change anything that also touches auth calls? The change record suggests not.
- Why did the auth-service /healthz log-level change on 08-31 matter, if at all?
- Were any other certificates close to expiry?

## Data gaps and tool failures (0 shown, 0 reported)
_None._
