# YouTube OAuth connection: channel lookup and safe diagnostics

The OAuth callback exchanges a Google authorization code for an offline token,
then verifies the account's actual YouTube channel using `channels.list(mine=true)`.
That lookup requires its own read permission in addition to video uploads.
Google consent now requests both YouTube `youtube.upload` and `youtube.readonly`.

If Google returns an HTTP error (OAuth exchange or channel lookup), the
backend surfaces an actionable HTTP 502/503 without leaking access tokens,
refresh tokens, one-time codes, secrets, or upstream response bodies.
Unexpected server failures continue returning the generic error, but server
logs now record only exception type and URL path (without OAuth query strings).

## Release steps
1. Enable **YouTube Data API v3** in the Google Cloud project associated with
   Render `YOUTUBE_CLIENT_ID`.
2. Under Google Auth Platform → Data Access, configure both requested YouTube
   OAuth scopes when Google requires that registration.
3. Keep the approved OAuth testing email in Google Auth Platform → Audience →
   Test users until production verification.
4. Confirm the exact redirect URI is registered:
   `https://video-platform-jtng.onrender.com/api/v1/publishing/oauth/youtube/callback`
5. Review CI, merge this PR, deploy Render, then restart **Connect YouTube**
   from the dashboard. Old Google OAuth codes cannot be reused.
6. If still failing, inspect the **Render Logs** at the callback timestamp.
   Logs show status and phase, not Google response bodies or credentials.

Do not rotate `JWT_SECRET`, `ADMIN_MFA_ENCRYPTION_KEY` or existing
`PUBLISHING_TOKEN_ENCRYPTION_KEY` to troubleshoot this error.
No database migration is required.
