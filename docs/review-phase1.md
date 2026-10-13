# Phase 1: tenant security and video delivery

This change set is the initial security/reliability response to the October 2026 repository review.

## Included

- Enforce video ownership on analytics queries and scene-to-video ownership on regeneration.
- Require account ownership and platform matching before queueing publication.
- Disallow silent real-platform publishing through the mock provider.
- Block suspended/deleted users from authenticating with still-valid access tokens.
- Validate production JWT settings on startup.
- Scope idempotency keys to a user and payload; enforce uniqueness via Alembic migration.
- Mark queue dispatch failures as FAILED rather than leaving stuck QUEUED jobs.
- Commit each pipeline stage transition so polling clients can observe progress.
- Expose the final asset ID to a user's video status response; load signed playback/download links in the studio.

## Verification

Run `cd backend && python -m alembic upgrade head && pytest tests/ -v`,
then `cd frontend && npm ci && npm run typecheck && npm run lint && npm run build`.
The GitHub workflow also runs the mock-provider end-to-end rendering smoke test.

## Not yet addressed

- An atomic DB-to-queue outbox and crash recovery for interrupted workers.
- Full MFA, password resets, refresh-token rotation, and cookie-based web auth.
- Real publishing/OAuth integrations and payment settlement.
- Real video/image/TTS generation providers and editing timeline.
- Content and media storage cleanup after failures or deletion.
- Production observability and provider-cost enforcement.
