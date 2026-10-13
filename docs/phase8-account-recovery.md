# Phase 8 — Account recovery and session revocation

## Features
- Real reset-link request endpoint with constant response content for unknown,
  inactive, and existing accounts; IP + hashed-address Redis throttling.
- Cryptographically unpredictable single-use reset tokens; only SHA-256 hashes
  are saved in PostgreSQL, expire after **30 minutes**, and previous links
  for a user are invalidated when a new reset is issued.
- Password reset and signed-in password change increment a per-user
  `session_version`, revoking previously issued access/refresh tokens.
- User-triggered **Sign out everywhere**, confirmed with password, also
  increments session version. Existing JWTs lacking `sv` are treated as 0
  for compatibility until the first revocation.
- Completed recovery, password changes, and revocations write audit records
  without passwords, tokens, or full reset URLs.
- Password recovery mail sent using Resend's HTTPS email API; no key in source
  control. Failed provider delivery **does not claim that an email was sent**:
  the public response is intentionally identical to avoid email enumeration;
  the undelivered token is removed best-effort. Configure provider monitoring.

## Deployment
1. Merge backend + frontend.
2. Back up production PostgreSQL and apply `alembic upgrade head` to reach
   `0009_account_recovery`. This adds `users.session_version` and
   `password_reset_tokens`; existing user sessions default to version 0.
3. Set **APP_URL** to the deployed frontend origin, e.g.
   `https://your-frontend.example`. Never use an arbitrary request Host.
4. Configure `RESET_EMAIL_API_KEY` and `RESET_EMAIL_FROM` **together** on
   the backend using a verified Resend sender domain; keep them server-side.
   When unconfigured, reset requests respond with 503, not a pretend success.
5. Redeploy backend + frontend. Test request, delivery, 30-minute expiry,
   one-time use, revocation of old access tokens, and sign in with new password.
6. Preserve `JWT_SECRET`, `ADMIN_MFA_ENCRYPTION_KEY`, `ADMIN_USER_IDS_RAW`
   and other production configuration.

## API
- `POST /api/v1/auth/password-reset/request`: `{email}` → 202
- `POST /api/v1/auth/password-reset/confirm`: `{token,new_password}` → 204
- `POST /api/v1/auth/password/change` (bearer): `{current_password,new_password}` → 204
- `POST /api/v1/auth/sessions/revoke-all` (bearer): `{password}` → 204

## Operational/security notes
- Recovery link URL contains an opaque bearer credential. Never share it or
  capture it in analytics, browser history exports, screenshots, or server logs.
  Frontend removes the query parameter on first load.
- Identity enumeration is resisted by uniform response body/status for account
  existence and email-provider send failures (when configured).
- Changing a password signs out all devices, including the current one.
- JWTs are still stored in browser localStorage in this phase, not httpOnly
  secure cookies. No device-by-device session inventory or refresh rotation.
- Repeated reset requests from one address per hour are throttled via Redis.
  Add provider-level alerts/quotas for distributed abuse in production.
- Lost admin MFA still requires controlled infrastructure recovery;
  password reset must **not** disable MFA or change the MFA encryption key.
