# Runbook: Render failures

**Symptom:** `GenerationJob.error_code = "pipeline_error"` with an FFmpeg
error in `error_message`, typically during the `rendering` stage.

## Diagnose

1. Read the full FFmpeg stderr — `app/services/render_service.py` logs it
   via `logger.error("render.ffmpeg_failed", ...)` with up to 2000 chars.
2. Common causes:
   - A scene's generated image or audio asset is corrupt/empty (check the
     asset's `size_bytes` in the `assets` table).
   - FFmpeg isn't installed in the worker image (verify
     `infra/docker/worker.Dockerfile` installed it — the API image
     deliberately does *not* bundle FFmpeg to keep it lean).
   - Disk space exhausted in the worker's temp directory.

## Fix

- **Corrupt scene asset:** use `POST /videos/{id}/storyboard/scenes/{scene_id}/regenerate`
  to regenerate just that scene's visual, then retry the render stage
  (currently requires re-running the full pipeline — see "Prevent
  recurrence" below for the improvement that would allow a render-only
  retry).
- **Missing FFmpeg:** rebuild the worker image; `apt-get install ffmpeg`
  is in `infra/docker/worker.Dockerfile`.
- **Disk space:** the render pipeline uses `tempfile.TemporaryDirectory()`
  which cleans up automatically on success or exception — persistent disk
  pressure means either concurrent jobs are too high for the instance
  size, or a previous crash left orphaned temp files (check `/tmp` on the
  worker host/container).

## Prevent recurrence

Add a render-only retry endpoint that re-runs `render_task.run()` against
already-generated scene assets, instead of requiring a full pipeline
re-run — this is called out as a known gap, not yet implemented.
