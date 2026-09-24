# Runbook: Stuck generation job

**Symptom:** `GenerationJob.status` stays `running` far longer than expected
(no progress on `Video.progress` / `current_stage` for >10 minutes on a
normal-length video).

## Diagnose

1. Check the worker process is alive: `docker compose ps worker` (or your
   orchestrator's equivalent). If it's not running, the job's `RUNNING`
   status is stale from a crashed worker.
2. Check worker logs for the job's `video_id` (structured logs include it
   on every line via `app.workers.tasks.pipeline_task`).
3. Check Redis: `redis-cli -u $REDIS_URL LLEN arq:queue` — a large queue
   depth means the worker pool is under-provisioned, not that a specific
   job is broken.
4. Check FFmpeg isn't hung on a malformed asset: `docker compose exec
   worker ps aux | grep ffmpeg`.

## Fix

- **Worker crashed mid-job:** the job is safely stuck at `RUNNING` (no
  automatic requeue is implemented yet — this is the improvement to make
  before production: add an arq/Redis lease-timeout requeue). For now,
  manually mark the job `FAILED` and let the user retry:
  ```sql
  UPDATE generation_jobs SET status = 'failed', error_code = 'worker_timeout'
  WHERE id = '<job_id>';
  UPDATE videos SET status = 'failed' WHERE id = '<video_id>';
  ```
- **Queue backlog:** scale the `worker` service horizontally
  (`docker compose up --scale worker=3` or your orchestrator's equivalent).
- **Hung FFmpeg process:** kill the process; the pipeline's top-level
  exception handler will mark the job `FAILED` on the next attempt, or
  do it manually as above if the process was killed out-of-band.

## Prevent recurrence

If this becomes frequent, the durable fix is a job lease/heartbeat with
automatic requeue (see `docs/architecture.md`, "Failure Handling" in the
original blueprint) — not yet implemented in this codebase.
