# Phase 4 — creator interface reference implementation

The four visual references provided in the original review were image-search examples
(not pixel-exact source files). This phase delivers a coherent dark-theme adaptation
of their four patterns: creator dashboard, scene/timeline editor, subtitle editor,
and publishing analytics. It does **not** claim to reproduce proprietary assets.

## Backed by real app state
- `GET /api/v1/creator/overview` returns owner-scoped video/project counts,
  the most recent videos, latest recorded publishing metrics, platform totals,
  and a 14-day series of dated snapshot totals.
- Analytics graph figures are **recorded cumulative snapshots by day**, not
  a metric of new views per day. If a user's account has no publishing
  data, the dashboard shows zeros and an honest empty state.
- `GET /api/v1/videos/{id}/captions` reads caption text in scene order
  and approximate start/end times derived from saved scene durations.
- `PATCH /api/v1/videos/{id}/captions` accepts caption edits (including an
  intentionally empty caption) and safe caption styles: classic, bold,
  social, minimal. Only finished videos may be edited, and edits mark
  `needs_rerender` so the user can update the actual MP4.
- FFmpeg now burns selected safe caption presets and uses per-scene caption
  overrides; an all-empty caption track yields an uncaptioned video.

## Known limits
- Captions use evenly-spaced estimates within each scene, **not** forced
  word alignment or word-by-word animation.
- Analytics is populated only when genuine published-video snapshots exist;
  this PR does not add social OAuth or claim unpublished videos have reach.
- The creator pages require authentication; signed thumbnails/playback
  continue using the private asset endpoint.
- The editor changes text, captions and image prompts using existing
  APIs. No fake drag/drop timeline reordering, multitrack audio editing,
  or invented export targets are shown as working controls.

## Deployment
Run Alembic migration `0006_creator_caption_studio`, then deploy backend and frontend.
Review at mobile and desktop widths. CI tests migration, APIs,
mock render/re-render, frontend typecheck/lint/build and Docker images.
