# AI Video Creator & Monetization Platform

A production-grade platform that turns a creator's idea into a polished,
multilingual short-form video: AI-assisted scripting, voice synthesis,
visual generation, editing, publishing and performance intelligence.

This repository is a complete, runnable implementation of the
architecture blueprint: a FastAPI backend with provider-agnostic AI
orchestration, an async render pipeline (FFmpeg), a Next.js frontend, and
full Docker/CI wiring. **The full pipeline runs end-to-end with zero
external API keys** via mock AI provider adapters that produce real,
valid audio/image/video bytes — this was verified during development by
running a complete generation (script → storyboard → voice → visuals →
render) against a real Postgres database and producing an actual MP4.

## Quick start

```bash
cp .env.example .env
docker compose up --build
```

- API: http://localhost:8000 (interactive docs at `/docs`)
- Frontend: http://localhost:3000

Sign up, create a project, and generate a video — it will complete using
the mock AI providers with no configuration required. Swap in real
providers by setting `LLM_PROVIDER` / `VOICE_PROVIDER` / `IMAGE_PROVIDER`
/ `VIDEO_PROVIDER` and their API keys in `.env` once you're ready for
production-quality generation (see `docs/architecture.md`).

## Repository layout

```
ai-video-platform/
├── backend/          FastAPI API + async worker (see backend/README below)
├── frontend/         Next.js 14 + TypeScript + Tailwind
├── infra/
│   └── docker/       Dockerfiles for api, worker, frontend
├── docs/             Architecture, API reference, security, deployment, runbooks
├── docker-compose.yml
└── .github/workflows/ci.yml
```

### Backend (`backend/`)

```
app/
├── main.py                FastAPI app assembly
├── config/                 Settings (env-driven) + structured logging
├── api/v1/                 HTTP routers (auth, projects, videos, jobs, voices, assets, publishing, analytics, billing)
├── domain/                 Extension points for framework-independent business entities
├── services/                content, voice, visual, caption, render, storage, publishing, quota
├── ai/
│   ├── director/            AI Video Director — plans script + storyboard
│   ├── providers/            LLM / TTS / image / video adapters behind shared interfaces (mock adapters ship by default)
│   ├── prompts/               Versioned system prompts
│   └── schemas/                 Pydantic schemas the director's output is validated against
├── workers/                Async pipeline (arq) — the actual generation work
├── db/                     SQLAlchemy models + Alembic migrations
├── security/               JWT auth, object-level permissions, rate limiting
└── tests/                  pytest suite (unit + schema + regression tests)
```

Run the backend's own test suite and the same end-to-end smoke test used
during development:

```bash
cd backend
pip install -r requirements.txt
export DATABASE_URL=postgresql+asyncpg://app:password@localhost:5432/aivideo
export JWT_SECRET=dev-secret
alembic upgrade head
pytest tests/ -v
pip install moto[s3] && python scripts/smoke_test.py
```

### Frontend (`frontend/`)

Next.js App Router: landing page, auth (login/signup/reset), a dashboard
(projects, analytics, billing, settings), and a studio flow (create video
→ poll generation progress). Talks to the backend via a small typed fetch
client (`lib/api/client.ts`) — no heavier HTTP library needed yet.

```bash
cd frontend
npm install
npm run dev        # http://localhost:3000
npm run typecheck  # tsc --noEmit
npm run lint
npm run build
```

## Documentation

- [`docs/architecture.md`](docs/architecture.md) — system design, the
  generation pipeline, and the reasoning behind key tradeoffs
- [`docs/api.md`](docs/api.md) — endpoint reference
- [`docs/security.md`](docs/security.md) — security posture and what to
  harden before a production launch
- [`docs/deployment.md`](docs/deployment.md) — local, Docker, and
  production deployment guidance
- [`docs/runbooks/`](docs/runbooks/) — stuck jobs, failed renders,
  provider outages, database recovery

## Known gaps (honest, not hidden)

This is a complete, working MVP scaffold — not a finished, audited
production system. Called out explicitly (also noted inline in the
relevant runbooks/docs) rather than left for you to discover:

- No automatic job retry/requeue on worker crash (jobs fail cleanly
  instead — see `docs/runbooks/stuck-job.md`).
- No render-only retry (a failure after asset generation currently
  requires re-running the full pipeline).
- Publishing providers (YouTube/TikTok/etc.) are mocked — real OAuth
  + upload flows are the next real adapters to write against the
  existing `PublishingProvider` interface.
- No MFA / brute-force protection on login yet.
- CI does not yet include secret scanning.

Each of these is a deliberate, documented scope cut for an MVP, not an
oversight — the interfaces (`PublishingProvider`, job status model,
auth layer) are already shaped to support them without a rewrite.
