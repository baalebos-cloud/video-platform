# Phase 7 — Authenticator device replacement and operator audit history

## Overview

After Phase 6 an administrator could enroll only once, with no safe way
to move to a new phone. This phase adds a **two-stage rotation** that
keeps the current authenticator active until the replacement is verified,
plus a paginated, allowlisted audit activity viewer.

## Deployment

1. Merge the PR and deploy the backend/frontend together.
2. Back up the production Postgres database, then run
   `alembic upgrade head` to apply `0008_admin_mfa_rotation_audit`.
3. Preserve the **existing** `ADMIN_MFA_ENCRYPTION_KEY`. Do NOT regenerate it.
4. Keep Redis available: rotation endpoints fail closed when rate limiting
   cannot be applied.
5. Log in as an allowlisted administrator and verify the audit history.

## Rotating to a different authenticator device

1. In Administration, select **Replace authenticator**.
2. Confirm the current admin password and a **fresh code from the existing device**.
3. The API stores the replacement seed encrypted, with a 10-minute expiry.
   The existing authenticator remains active during this stage.
4. Add the replacement seed on the *new* device as a separate entry.
   **Do not delete the old entry yet**; confirm a code from the new device.
5. On successful confirmation the new seed replaces the old one atomically.
   Previously accepted TOTP codes cannot be replayed.
6. If the attempt expires or errors, the original authenticator still works.
   Start another rotation using the old device.

Endpoints:
- `POST /api/v1/admin/mfa/rotation/start` with `{password, code}`;
  returns `secret`, `otpauth_uri`, `expires_in_seconds`.
- `POST /api/v1/admin/mfa/rotation/confirm` with `{code}`;
  returns `{enabled: true, rotated: true}`.
- Both endpoints require normal admin authentication and Redis-backed
  rate limiting. Start additionally requires password + existing TOTP.

## Operator audit activity

`GET /api/v1/admin/audit?limit=20&cursor=<cursor>` returns chronological
activity, a stable cursor, and only allowlisted operator actions/fields.
Each entry includes timestamp, actor UUID, event name, resource and a
minimal subset of safe metadata. Nothing returns plaintext credentials,
OTP seeds, codes, or adjustment-authorization tokens.

The audit log is **read-only**, restricted to admin UUIDs. The report
records credit adjustment attempts that were successfully authorized or
applied and MFA lifecycle transitions; it is **not** a full access log,
nor proof that no failed attempts occurred. Further security monitoring
should track failed attempts separately, without logging secrets.

## Limitations

- **Lost old device**: self-service rotation is deliberately prohibited.
  Recover under a reviewed, audited infrastructure-admin procedure.
- Password+TOTP remains phishable; consider WebAuthn, recovery codes,
  secure httpOnly sessions, and enterprise monitoring in future phases.
- There is no secret-reveal endpoint after start; restart rotation if
  setup information is lost. Old device stays working throughout.
