# Phase 10 — Recoverable video generation

- A failed generation can be retried as a **new video** using its frozen
  inputs. Partial scenes, assets, and old jobs are not replayed or overwritten.
- The original failed video is preserved for support and diagnosis.
- A user+source-scoped idempotency key prevents accidental double charging
  on repeated button clicks or network retries.
- Credits and concurrency are validated by the existing generation service.
  A retry is billable as a new generation when credit enforcement is active;
  clearly warn creators before retrying.
- The editor exposes Retry as new video on failed items.
- Owner-only `GET /videos/{id}/jobs` surfaces recent job statuses.
- Generic pipeline exception messages are redacted in user responses;
  exception types remain in server logs.

Limitations: no automatic retry for external AI providers, no durable worker
heartbeat or dead-letter automation. A stopped worker can still leave a job
queued/running; production operations should use the stuck-job runbook.

Requires Phase 9 merge and its migration before deploying this stacked PR.
No new database migration in Phase 10.
