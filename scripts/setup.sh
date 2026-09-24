#!/usr/bin/env bash
# One-shot local setup: copies .env, brings up the full stack, and runs
# migrations. Idempotent — safe to re-run.
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example — edit it if you want real provider keys."
fi

echo "Building and starting services..."
docker compose up --build -d postgres redis minio minio-init

echo "Waiting for Postgres to be healthy..."
until docker compose exec -T postgres pg_isready -U app > /dev/null 2>&1; do
  sleep 1
done

echo "Running database migrations..."
docker compose run --rm migrate

echo "Starting API, worker, and frontend..."
docker compose up --build -d api worker frontend

echo ""
echo "Done. API: http://localhost:8000/docs   Frontend: http://localhost:3000"
