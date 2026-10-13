# Phase 9 — HttpOnly session BFF and refresh rotation

- Next.js same-origin BFF stores access+refresh JWTs in secure HttpOnly,
  SameSite=Lax cookies. No bearer token reaches frontend JS.
- Mutating requests require exact Origin match (CSRF defense).
- New DB `user_sessions` persists only digests of random refresh JTIs.
- Refresh rotates the stored JTI atomically under a row lock; replay fails.
- Sign out revokes current refresh token; change password/reset and sign-out-
  everywhere invalidate access via session_version.
- Session listing and single-session revocation require a logged-in user;
  per-user ownership checked in SQL. New access JWTs include a session id,
  so single-session revocation immediately invalidates access as well as refresh.
  Creator Settings displays sessions with a current-device marker.
- Proxy passes through JSON and binary but never forwards upstream Set-Cookie.
- Existing legacy localStorage tokens will be cleared and users must sign
  in again. Direct API JWT consumers are still supported if they use login.
- Unsuccessful concurrent refresh attempts may cause one tab to log out.
  Cross-tab synchronization is a future enhancement.

Deployment order: merge PR, back up Neon PostgreSQL, run
`alembic upgrade head` to `0010_rotating_sessions`, then deploy Render
and Vercel. Existing JWT_SECRET and ADMIN_MFA_ENCRYPTION_KEY must be
preserved. Vercel NEXT_PUBLIC_API_URL should still end in /api/v1 and point
to Render; optionally use server-only API_INTERNAL_URL for BFF.
Ensure APP_URL is https://video.baalebo.xyz. Test login, session cookie
HttpOnly, refresh expiry, logout, MFA, password reset, and CORS.
