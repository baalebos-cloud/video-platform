# Phase 12 — YouTube and TikTok publishing connectors

## Available capabilities
- OAuth2 authorization via Google (youtube.upload scope) and TikTok
  (video.upload scope), single-use DB-stored 10-minute OAuth state,
  encrypted server-side refresh/access tokens, account ownership checks.
- YouTube upload via resumable protocol, always PRIVATE initially.
- TikTok `inbox/video/init` upload to the creator's TikTok inbox.
  **This is NOT an automatic public TikTok post**: the creator completes
  the final publishing action inside TikTok.
- Real uploading is strictly gated on platform credentials and an encrypted
  OAuth connection. Mock stays mock-only and refuses production.
- Guard 60 MB max media file size. Vendor API calls can fail or incur quota.
- New migration `0011_publishing_oauth`; no user media is made publicly
  visible automatically.

## REQUIRED before enabling
1. Merge #27 -> #28 -> #29 -> #30 in sequence; back up DB then migrate to
   `0011_publishing_oauth` before deploying backend workers.
2. Register apps and redirect URIs with Google + TikTok:
   `https://YOUR-RENDER-API/api/v1/publishing/oauth/youtube/callback`
   `https://YOUR-RENDER-API/api/v1/publishing/oauth/tiktok/callback`
3. Render/worker secrets: YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET,
   TIKTOK_CLIENT_ID, TIKTOK_CLIENT_SECRET, PUBLISHING_TOKEN_ENCRYPTION_KEY
   (new stable Fernet key separate from ADMIN_MFA_ENCRYPTION_KEY),
   API_URL set to the real Render HTTPS origin, APP_URL to
   `https://video.baalebo.xyz`.
4. Obtain vendor scope approval, audit/verification and quotas. TikTok
   upload requires approved video.upload and creator consent. TikTok
   direct publish (video.publish) is NOT implemented in this PR.
5. Publish only content you own and have rights to distribute. Validate
   format/creator eligibility in vendor dashboards.

## Current limitations
- Cross-service video uploads are currently capped at 60 MB and in-memory;
  adapt to streaming/chunked uploads before supporting longer videos.
- Token refresh is best-effort; expired/revoked vendor access may require
  reconnecting the account.
- No background status reconciliation/analytics synchronization.
- TikTok upload finishes in the creator inbox, not a public post.
- Account un-linking, creator-facing account picker, consent, and upload
  controls are available in Dashboard → Publishing. History shows stored states.
- The recent ready-video selector uses the latest creator overview (12 items),
  not a complete searchable archive.
