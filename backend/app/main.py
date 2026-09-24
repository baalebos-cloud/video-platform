"""
FastAPI application entrypoint.

Run locally with:  uvicorn app.main:app --reload
(see infra/docker/backend.Dockerfile and docker-compose.yml for containerized usage)
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.errors import http_exception_handler, unhandled_exception_handler, validation_exception_handler
from app.api.v1 import analytics, assets, auth, billing, jobs, projects, publishing, storyboards, users, videos, voices
from app.config.logging import configure_logging, get_logger
from app.config.settings import get_settings

settings = get_settings()
configure_logging(settings.debug)
logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("app.startup", env=settings.app_env)
    yield
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
