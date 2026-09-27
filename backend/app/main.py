"""
FastAPI application entrypoint.

Run locally with:  uvicorn app.main:app --reload
(see infra/docker/backend.Dockerfile and docker-compose.yml for containerized usage)
"""
import asyncio
from contextlib import asynccontextmanager

from arq.worker import Worker
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.errors import http_exception_handler, unhandled_exception_handler, validation_exception_handler
from app.api.v1 import analytics, assets, auth, billing, jobs, projects, publishing, storyboards, users, videos, voices
from app.config.logging import configure_logging, get_logger
from app.config.settings import get_settings
from app.workers.worker import WorkerSettings

settings = get_settings()
configure_logging(settings.debug)
logger = get_logger("main")

_in_process_worker: Worker | None = None
_in_process_worker_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _in_process_worker, _in_process_worker_task

    logger.info("app.startup", env=settings.app_env)

    if settings.run_worker_in_process:
        # See Settings.run_worker_in_process for why this exists. Built
        # from arq's own Worker class (not the `arq` CLI) so it can run
        # as a background task inside uvicorn's event loop rather than
        # as a separate process — confirmed safe: Worker.async_run()
        # installs no signal handlers itself (that only happens in
        # arq's synchronous `run()` wrapper, which isn't used here), so
        # it doesn't fight with uvicorn's own shutdown handling.
        _in_process_worker = Worker(
            functions=WorkerSettings.functions,
            redis_settings=WorkerSettings.redis_settings,
            on_startup=WorkerSettings.on_startup,
            on_shutdown=WorkerSettings.on_shutdown,
            max_jobs=WorkerSettings.max_jobs,
            job_timeout=WorkerSettings.job_timeout,
        )
        _in_process_worker_task = asyncio.create_task(_in_process_worker.async_run())
        logger.info("app.in_process_worker_started")

    yield

    if _in_process_worker_task is not None:
        _in_process_worker_task.cancel()
        try:
            await _in_process_worker_task
        except asyncio.CancelledError:
            pass
    if _in_process_worker is not None:
        await _in_process_worker.close()

    logger.info("app.shutdown")


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="AI-assisted, provider-agnostic video creation and monetization platform.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

API_PREFIX = "/api/v1"
app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(users.router, prefix=API_PREFIX)
app.include_router(projects.router, prefix=API_PREFIX)
app.include_router(videos.router, prefix=API_PREFIX)
app.include_router(storyboards.router, prefix=API_PREFIX)
app.include_router(jobs.router, prefix=API_PREFIX)
app.include_router(voices.router, prefix=API_PREFIX)
app.include_router(assets.router, prefix=API_PREFIX)
app.include_router(publishing.router, prefix=API_PREFIX)
app.include_router(analytics.router, prefix=API_PREFIX)
app.include_router(billing.router, prefix=API_PREFIX)


@app.get("/health", tags=["ops"])
async def health() -> dict:
    """Liveness/readiness probe target for orchestrators and load balancers."""
    return {"status": "ok", "env": settings.app_env}
