# Phase 2B: saved-asset re-render

## Workflow
1. Initial generation now persists scene narration as AUDIO assets and attaches audio_asset_id to each scene.
2. Regenerating a storyboard image marks the video as `needs_rerender`. Prompt edits alone do not mark it dirty, because the rendered image did not change.
3. Studio video page shows an explicit **Re-render video** action when scenes have changed.
4. POST /api/v1/videos/{id}/rerender checks ownership, accepts only a completed video with saved audio and images, and atomically marks the video RENDERING while queuing a RENDER job.
5. arq `rerender_video` loads only the persisted scene image/audio storage keys. It uses the existing FFmpeg render task, creates fresh MP4/thumbnail assets, and swaps their pointers only after success.
6. On error, the original MP4 remains downloadable; the job is marked FAILED, while the video returns to READY with needs_rerender=true.

## Deployment
- Apply Alembic migration 0004_scene_audio_and_rerender prior to deploying the new worker.
- Old videos have no saved audio_asset_id (the original pipeline previously only stored the key transiently); they cannot be re-rendered through this saved-asset path. Make a new video after deployment.
- Re-renders still consume CPU/storage, and are subject to the three-per-minute user/IP rate limit and concurrent-job policy, but credit debits are not yet implemented. Add billing safeguards before enabling high-volume public usage.
- Existing media is not garbage-collected; retention policies are a follow-on.
- The in-process Redis worker must be restarted after deployment so it registers rerender_video.

## Verification
- `pytest tests/ -v`
- `python scripts/smoke_test.py` now also tests a second FFmpeg render with persisted assets.
- `npm run typecheck && npm run lint && npm run build`
- Verify failure-mode UX and private media storage on staging.

## Remaining production risks
- No durable transactional outbox / crash recovery: if a worker dies mid-render, it can remain stuck.
- No separate render-only retry/resume at scene level or billing settlement.
- Modifying a scene image during render is guarded at the API level, but database mutations outside that API could invalidate a render.
- Already published social posts are not replaced automatically by re-rendering.
