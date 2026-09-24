# Security

## Principles

- **Server-side secrets only.** No AI provider key, storage credential,
  or publishing token ever reaches the browser. The frontend calls the
  FastAPI backend; the backend calls providers.
- **Object-level authorization.** Every project/video-scoped endpoint
  calls `require_project_owner` / `require_video_owner`
  (`app/security/permissions.py`) before acting, returning 404 (not 403)
  for resources the caller doesn't own, to avoid confirming existence.
- **Short-lived signed URLs** for private media (`app/services/storage_service.get_signed_url`,
  15-minute default) rather than public bucket access.
- **Idempotency keys** on `POST /videos/generate` prevent duplicate
  expensive generations from retried client requests.
- **Rate limiting** on expensive endpoints via a Redis-backed fixed-window
  limiter (`app/security/rate_limit.py`).
- **Stable error codes**, never raw stack traces, in API responses.

## Authentication

JWT access tokens (`app/security/auth.py`), bcrypt-hashed passwords via
passlib. Access tokens are short-lived (60 min default); a separate
refresh token has a longer lifetime. Rotate `JWT_SECRET` by deploying a
grace-period dual-secret verification if you need zero-downtime rotation
— the current implementation assumes a single active secret, which is
adequate pre-scale but should be revisited before a security review.

## Prompt injection

Creator-supplied text (topic, brand context) is treated as **untrusted
input data**, not instructions, inside the AI Video Director's system
prompt (`app/ai/prompts/video_director_v1.py`). The director's output is
schema-validated (`app/ai/schemas/video_plan.py`) before any expensive
asset generation is triggered — a malformed or injected response simply
fails validation and the job is marked `FAILED`.

## Threat model (summary)

| Threat | Mitigation |
|---|---|
| API key leakage | Server-side secrets only; add secret scanning to CI before production |
| Account takeover | bcrypt hashing, short-lived JWTs; add MFA before production |
| Unauthorized project access | Object-level authorization on every scoped route |
| Malicious upload | Validate MIME/size before processing (extend `assets.py` as upload flows are added) |
| Prompt injection | Untrusted-input framing + strict schema validation before expensive work |
| Runaway generation cost | Quotas, concurrent-job limits, idempotency (`app/services/quota_service.py`) |
| Webhook spoofing | Verify signatures per provider's documented method once real publishing OAuth is added |
| Data exposure | Least-privilege storage credentials, signed URLs, encrypted transport (terminate TLS at the load balancer/ingress) |

## Before production

This scaffold ships with reasonable defaults but is **not** a completed
security review. Before handling real user data or spend:

- Add secret scanning to CI (e.g. gitleaks) — not yet wired into `ci.yml`.
- Add MFA and account-lockout / brute-force protection to `/auth/login`.
- Rotate `JWT_SECRET` and all provider keys out of `.env` into a secret
  manager (AWS Secrets Manager, GCP Secret Manager, Vault).
- Add file-upload validation once user uploads (not just AI-generated
  assets) are supported.
- Restrict CORS (`Settings.cors_allowed_origins`) to the real production
  frontend origin(s).
