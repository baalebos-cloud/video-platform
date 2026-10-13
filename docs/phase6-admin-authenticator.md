# Phase 6 — Administrator authenticator step-up security

Merges on top of Phase 5. The sensitive credit adjustment endpoint now
requires **both** the existing logged-in admin access token and a second,
purpose-scoped authorization token issued after password + 6-digit TOTP.

## Deployment
1. Run Alembic migration `0007_admin_totp_credentials`.
2. Generate a stable Fernet key **locally**, once:
   `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
3. Set `ADMIN_MFA_ENCRYPTION_KEY` on the backend only using the deployment
   secrets manager. **Do not commit it** or place in NEXT_PUBLIC_ variables.
4. If production administrators are provisioned, the app now refuses to start
   until an encryption key is configured. Retain the same encryption key
   between deployments. Back it up securely. Losing the key means existing
   encrypted authenticator secrets cannot be decrypted.
5. Administrators visit Dashboard → Administration and enroll an authenticator
   (Google Authenticator, Microsoft Authenticator, 1Password, etc.) with
   their password, copy/scan the `otpauth://` URI or enter the secret, then
   confirm a current 6-digit code.
6. For each credit adjustment, supply the current password and a *fresh*
   TOTP code. The server issues a three-minute authorization token bound to
   the exact **account UUID, amount, reason, and request ID**.
7. The frontend submits that token only in `X-Admin-Authorization` on
   POST /admin/credits/adjust. Changing any part of the request invalidates
   the authorization. Replaying the exact credit request is idempotent.

## Security notes
- The second-factor seed is encrypted at rest with Fernet, never stored in
  plaintext. Setup returns the plaintext seed *once* as part of enrollment.
- The rate limits on enrollment, activation, credit authorization and login
  use the shared Redis limiter; if Redis is unavailable they must fail rather
  than bypass limits.
- TOTP validation follows RFC 6238 with a 30-second step and ±1-window
  clock tolerance. The last accepted step is persisted with row locking
  and cannot be used again.
- Setting up MFA requires the signed-in admin's password. There is no
  self-service removal/reset endpoint. For device loss, an authenticated,
  audited infrastructure-admin recovery procedure is required (document
  and review before production).
- Non-admins are denied by the backend UUID allowlist regardless of the UI.
- Read-only administrator reports still use normal admin authentication;
  sensitive credit changes require MFA step-up.
- Existing access tokens do not automatically grant credit-adjustment
  privileges after this migration.

## Limitations
- Still relies on password + TOTP rather than phishing-resistant WebAuthn,
  and the base UI JWT remains stored in localStorage. Migrate to hardened
  authentication and secure sessions before large-scale operations.
- No payment processor, withdrawal system, or real USD spending ledger.
- The three-minute authorization token is scoped to an idempotent request;
  while valid it can be replayed **only for that same request**, which never
  credits twice. A token cannot be used for another amount or recipient.
- A dedicated admin audit/lockout dashboard and key rotation remain future work.
