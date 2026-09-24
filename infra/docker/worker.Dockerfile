# Worker image — same codebase as the API, running the arq worker
# process instead of uvicorn. Kept as a separate image (not just a
# separate command on the API image) so worker and API can be scaled,
# deployed and resourced independently, per docs/architecture.md.
FROM python:3.12-slim AS base

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .

CMD ["arq", "app.workers.worker.WorkerSettings"]
