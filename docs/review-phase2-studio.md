# Phase 2A: creator library and storyboard review

A new studio workflow for creator projects:
- GET /api/v1/projects/{project_id}/videos: authenticated, parent-owned, paginated, optional status filter.
- Each card links to video progress/playback and shows a thumbnail when one has been saved.
- Persist image assets for generated scenes and register finished-video thumbnails.
- Show scenes with narration, a visual preview, editable visual prompt, and manual image regeneration.
- Preview and regeneration operate on the saved storyboard only. They **do not** update an already rendered MP4.
- Map landscape generations to 16:9 rendering and keep vertical generations at 9:16.
- Sign browser-facing media requests against STORAGE_PUBLIC_BASE_URL. In local Docker, use localhost:9000; in production configure an actual public S3/MinIO endpoint.

## Deploy notes
1. Run Alembic migration 0003_video_thumbnails before upgrading the backend.
2. Set STORAGE_PUBLIC_BASE_URL to the browser-reachable storage API hostname (for Docker on the same machine, http://localhost:9000).
3. The old videos do not have persisted thumbnail or scene-image metadata. New videos do.
4. Run GitHub CI, including the mock generation smoke test. Verify media links and editor controls manually on a staging environment.

## Follow-up
- Implement a durable, asset-aware **re-render** workflow before claiming that storyboard changes update finished videos.
- Real voice/image/video providers, caption alignment, OAuth publishing, billing, provider quotas, and rendering retries remain separate projects.
