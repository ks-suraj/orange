# Incident report S05

- **Status:** CONCLUSIVE (confidence 0.90, margin 0.85, 6 verified supporting and 2 contradicting evidence items (25%))
- **System:** baseline · **Model:** anthropic/claude-haiku-5.5 · **Stopped because:** agent_finished
- **Root cause:** `auth-service` - certificate_expiry (confidence 0.90)

## Summary
The incident is caused by the expired TLS certificate for auth.internal (auth-service), not by the 08:54 checkout deploy. The auth certificate expired at 08:59:59Z, and its ACME renewal had been failing with rate-limit rejections since 08:05Z. From 09:00Z, checkout-service and api-gateway fail TLS validation against auth-service, which produces the checkout error spike and sign-in failures. The v2.15.1 deploy changed only static button copy and its timing lines up with the failures only by coincidence. The auth health check is plaintext on port 8080 and reports healthy, so it does not exercise the TLS certificate. Confidence is high, and the one-off card-decline error is noise.

## Conclusion decision
- confidence 0.90, margin 0.85, 6 verified supporting and 2 contradicting evidence items (25%)
- Criteria: top `auth-service / certificate_expiry` confidence 0.90, margin 0.85, 6 verified supporting / 2 contradicting items (25% contradicting); 0 evidence-backed material critic objection(s), 0 non-blocking

## Ranked hypotheses
1. **auth-service** - certificate_expiry (confidence 0.90)
   - Mechanism: The auth.internal certificate expired at 08:59:59Z after ACME renewal was rate-limited. checkout-service and api-gateway TLS validation to auth-service then fails, so token checks fail and checkout and sign-in errors rise from 09:00Z.
   - Supporting evidence: `L0018, L0065, L0184, L0185, L0194, M12`
   - Contradicting evidence: `L0023, L0057`
   - Assumptions: The certificate was not renewed before expiry.
2. **checkout-service** - deployment_regression (confidence 0.05)
   - Mechanism: The v2.15.1 deploy at 08:54Z introduced a fault that breaks token validation. The timing is close to onset, but the change is static strings only.
   - Supporting evidence: `C09`
   - Contradicting evidence: `L0184, L0185, M11, M13`
   - Assumptions: The change record is complete and no config or TLS client change was bundled into the deploy.
3. **payment-service** - certificate_expiry (confidence 0.05)
   - Mechanism: An expired certificate on a downstream service would cause checkout failures. The June incident had this pattern, but no payment-service TLS errors were found in this window.
   - Supporting evidence: `P06`
   - Contradicting evidence: `L0184`
   - Assumptions: Payment-service was not queried in this window.

## Observed facts
- checkout-service error_rate jumped from about 0.3% (08:55:00Z, 0.26%) to 33.91% at 09:00:00Z and stayed between 30.8% and 33.9% through 09:30:00Z. `M12`
- auth-service logged a WARN at 08:05:03Z that certificate renewal for cn=auth.internal failed (ACME order rejected, rate limited), with current certificate expiry 2026-09-05T08:59:59Z; the same renewal failure was logged again at 08:20:17Z. `L0018, L0065`
- checkout-service ERROR logs starting 09:00:04Z show PKIX validation failure 'validity check failed' when validating auth-service at auth.internal:8443; 45 such errors appear in the signature count. `L0184, L0190, L0243`
- api-gateway ERROR logs starting 09:00:15Z show 'certificate has expired... current time is after 2026-09-05T08:59:59Z (cn=auth.internal)'. `L0185, L0194`
- The v2.15.1 checkout-service deploy at 08:54:00Z only changed checkout button copy and translations (static strings only). `C09`
- checkout-service cpu, memory, latency p99 and request rate stayed in normal ranges across 08:00Z to 09:30Z (latency p99 about 307-332 ms). `M11, M13, M14, M15`
- Health checks for api-gateway, auth-service, and checkout-service all report healthy at 09:28:00Z; the auth check is HTTP /health 200 on the plaintext admin port 8080. `H01, H02, H03`
- A past incident (2026-06-11) on payment-service and checkout-service had identical symptoms: TLS handshake failures and checkout 5xx, caused by an unrenewed certificate. `P06`

## Assumptions
- The auth.internal certificate was not renewed after the ACME rate-limit failures, so it remained expired after 08:59:59Z.
- The plaintext health check on port 8080 does not exercise the TLS listener on 8443, so it cannot detect this failure.
- Sign-in failures are caused by the same auth-service TLS failure as checkout, since api-gateway's auth checks fail the same way.
- Telemetry for the last 30 minutes is complete; no gaps were found in the returned data.

## Inferred conclusions
- The root cause is the expired auth.internal TLS certificate on auth-service, which was not renewed because ACME renewal was rate-limited; the fault originates in auth-service's certificate lifecycle. (confidence 0.90) `L0018, L0065, L0184, L0185`
- The v2.15.1 checkout deploy is not the cause; the timing coincidence is explained by the certificate expiry at 08:59:59Z. (confidence 0.85) `C09, M12, L0184`
- Checkout and api-gateway errors are downstream propagation of the auth-service certificate failure along the sync_http dependencies. (confidence 0.85) `D03, D06, L0184, L0185`

## Remediation
- **immediate** - Immediately issue or install a valid certificate for cn=auth.internal on auth-service's TLS listener (port 8443), bypassing the rate-limited ACME order, for example by using a manually issued certificate or an alternate CA. _(The expired certificate is the direct cause of the checkout and sign-in failures.)_
- **immediate** - Verify checkout-service and api-gateway recover to a near-zero error rate once the new certificate is served, and confirm sign-in works. _(Confirms that the fix resolves the symptoms.)_
- **immediate** - Do not roll back v2.15.1, since it is unrelated to the failure. _(Avoids an unnecessary rollback that would not fix the outage.)_
- **short_term** - Fix the cert-manager/ACME renewal path so that renewal retries are backed off and rate limits are not exhausted, and the renewal is not retried in a loop. _(The renewal failed for over 50 minutes before expiry without escalation.)_
- **short_term** - Add certificate expiry alerting (e.g. 30/14/7 days before expiry) and a TLS-level health check on port 8443 for auth-service. _(The current plaintext /health check reported healthy during the outage, and a 2026-06-11 incident had the same failure mode.)_
- **long_term** - Audit all other internal certificates for expiry and renewal status. _(The same failure happened on payment-service in June, so the renewal process is a systemic risk.)_

## Open questions
- Why was the ACME order rate-limited, and what triggered the repeated renewal attempts?
- Was the expiry date set to 08:59:59Z a deliberate short-lived certificate or a misissue?
- Is the sign-in failure (bad password WARNs) a separate cause or just user-facing noise?
- Did the 08:54 deploy change any TLS or auth client configuration? Only static strings were recorded, but no config diff was available.

## Data gaps and tool failures (0 shown, 0 reported)
_None._
