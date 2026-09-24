# Architecture

## Overview

The platform turns a creator's topic into a rendered, multilingual short-form
video: script → storyboard → voice → visuals → captions → timeline → render →
publish. It is built as a modular monolith (one FastAPI codebase) with
async workers, rather than microservices, because at MVP scale a single
well-layered codebase is faster to build and reason about, while the
service/provider boundaries keep it easy to split out a service later if a
component (e.g. rendering) needs independent scaling sooner than the rest.

```
 WEB/MOBILE UI  →  API LAYER  →  APPLICATION CORE (services, AI adapters)
                                        │              │
                                  PostgreSQL      Redis / Queue
                                        │              │
                                        └──────┬───────┘
                                               ▼
                          AI/Voice/Visual Providers · Render Workers (FFmpeg)
                                               │
                                        Object Storage (S3-compatible)
                                               │
                                  Publishing Providers · Analytics
```

## Layers

| Layer | Location | Responsibility |
|---|---|---|
| API | `backend/app/api/` | HTTP validation, auth dependencies, response mapping |
| Domain | `backend/app/domain/` | Extension point for framework-independent business entities (see its docstrings) |
| Services | `backend/app/services/` | Application workflows: content, voice, visual, render, publishing, storage, quota |
| AI adapters | `backend/app/ai/providers/` | Provider-specific requests/responses behind shared interfaces |
| Workers | `backend/app/workers/` | Async execution of the generation pipeline, with retries |
| DB | `backend/app/db/` | SQLAlchemy models + Alembic migrations |

This mirrors the "Separation of concerns" table in the original blueprint:
API code never imports a provider SDK directly, and provider adapters never
contain product business rules.

## Provider-agnostic AI orchestration

Every AI capability (LLM, TTS, image, video) is defined as an abstract
interface in `app/ai/providers/base.py`. Concrete adapters live under
`app/ai/providers/{llm,tts,image,video}/`. Only mock adapters ship by
default — they produce real, valid bytes (a WAV tone, a placeholder PNG,
a JSON script) so the **entire pipeline runs end-to-end with zero API
keys**, which is what makes local development and CI possible without
paid credentials.

`app/ai/providers/registry.py` is the single place that decides which
provider serves a given task, based on `Settings.llm_provider` /
`voice_provider` / etc. Adding a real provider means writing one adapter
class and registering it — no other code changes.

## The generation pipeline

`POST /api/v1/videos/generate` does the minimum synchronous work (creates
`Video` + `GenerationJob` rows, enforces quota/idempotency, enqueues a job)
and returns immediately. The actual work happens in
`app/workers/tasks/pipeline_task.py`, which is what an arq worker process
runs:

1. **Plan** — `AI Video Director` (`app/ai/director/`) turns topic + preferences
   into a schema-validated `VideoPlan` (script, scenes, voice direction,
   metadata). Validation happens *before* any expensive generation.
2. **Storyboard** — the plan is persisted as `Script` + `Scene` rows.
3. **Per-scene assets** — narration audio (TTS) and a scene image are
   generated and uploaded to object storage.
4. **Render** — FFmpeg composes each scene into a clip, concatenates them,
   burns in captions, and extracts a thumbnail.
5. **Finalize** — the rendered MP4 is registered as an `Asset` and linked to
   the `Video`.

Every stage updates `Video.progress` / `current_stage` and
`GenerationJob.status`, so the frontend can poll `GET /videos/{id}` for
live progress. A failure at any stage marks the job `FAILED` with a stable
`error_code` rather than crashing the worker.

## Versioning & reproducibility

The director's system prompt is versioned (`app/ai/prompts/video_director_v1.py`,
`PROMPT_VERSION`). Never edit a prompt file in place once it has been used
for a real generation — add `_v2` and switch the director to reference it,
so past generations remain reproducible from their stored
`prompt_version` / `schema_version` / provider / model metadata.

## Cost & quota controls

`app/services/quota_service.py` enforces `max_video_duration_seconds` and
`max_concurrent_jobs_per_user` before a job is ever queued, and
`app/db/models/billing.py` (`credit_ledger`) is an append-only ledger —
balances are always computed by summing entries, never mutated in place,
so the balance is auditable.

## Why these specific tradeoffs

- **Modular monolith over microservices**: fewer moving parts to operate
  at MVP scale; the service-layer boundaries make a future split
  low-risk.
- **FFmpeg-based rendering over a generative "text-to-video" model as the
  only path**: keeps cost and latency predictable, and lets a
  `VideoProvider` adapter (generative video) slot in later per scene
  without changing the render pipeline's contract.
- **arq over Celery**: async-native, smaller dependency footprint, and a
  natural fit for an already-async FastAPI codebase.
