# Deployment

## Local development

```bash
cp .env.example .env
docker compose up --build
```

This starts Postgres, Redis, MinIO (+ bucket auto-creation), runs Alembic
migrations, and starts the API (`:8000`), worker, and frontend (`:3000`).
Everything works with the default `LLM_PROVIDER=mock` / etc. settings —
no API keys required to see the full pipeline run.

## Without Docker

Backend:
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=postgresql+asyncpg://app:password@localhost:5432/aivideo
export JWT_SECRET=dev-secret
alembic upgrade head
uvicorn app.main:app --reload
```

Worker (separate terminal, same env vars):
```bash
arq app.workers.worker.WorkerSettings
```

Frontend:
```bash
cd frontend
npm install
npm run dev
```

## Production principles

- Separate `.env` per environment (dev/staging/prod); never share secrets
  across them.
- Run `alembic upgrade head` as an explicit, controlled deployment step
  (the `migrate` service in `docker-compose.yml` models this — run it as
  a one-off job/init-container in your orchestrator, not as a sidecar).
- `GET /health` is the liveness/readiness probe target for the API.
- Scale the `worker` service independently from `api` — generation and
  rendering are the compute-heavy part of this system.
- Set explicit CPU/memory limits on worker containers (FFmpeg rendering
  is CPU-intensive and bursty).
- Use a real S3/R2/GCS bucket in production instead of the bundled MinIO
  (set `STORAGE_ENDPOINT` accordingly, or leave blank for AWS S3).
- Put the frontend behind a CDN; it's a standard Next.js standalone
  server (`infra/docker/frontend.Dockerfile`) and works on any
  container platform.
- Track provider spend against `credit_ledger` so cost anomalies are
  visible before they become a bill.

## CI/CD

`.github/workflows/ci.yml` runs, on every push/PR:
1. Backend: install deps, byte-compile, run Alembic against a throwaway
   Postgres service, run pytest, then run the full end-to-end pipeline
   smoke test (`backend/scripts/smoke_test.py`) with a mocked S3 backend
   — this is the same test used to validate this codebase during
   development, so a regression in the pipeline fails CI, not a
   customer's generation.
2. Frontend: install deps, `tsc --noEmit`, `next lint`, `next build`.
3. Docker: build all three images to catch Dockerfile rot early.

Extend this with a deploy job once a target platform (ECS, Cloud Run,
Fly.io, etc.) is chosen.
