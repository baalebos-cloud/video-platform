"""
Central application configuration.

All configuration is loaded from environment variables (see .env.example
at the repo root). Nothing here should contain a real secret — defaults
are safe-for-local-dev placeholders only.
"""
from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Application ---
    app_env: Literal["development", "staging", "production", "test"] = "development"
    app_name: str = "AI Video Creator & Monetization Platform"
    app_url: str = "http://localhost:3000"
    api_url: str = "http://localhost:8000"
    debug: bool = True

    # --- Security ---
    jwt_secret: str = Field(default="replace_me_in_env", repr=False)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 14

    # --- Database ---
    database_url: str = "postgresql+asyncpg://app:password@localhost:5432/aivideo"

    # --- Redis / Queue ---
    redis_url: str = "redis://localhost:6379/0"

    # --- Object storage (S3-compatible) ---
    # Leave storage_endpoint empty to use real AWS S3; set it to point at
    # MinIO/R2/other S3-compatible endpoints (docker-compose sets this to
    # the bundled MinIO service).
    storage_endpoint: str = ""
    storage_bucket: str = "aivideo-assets"
    storage_access_key: str = "minioadmin"
    storage_secret_key: str = Field(default="minioadmin", repr=False)
    storage_public_base_url: str | None = None

    # --- AI providers (all optional — mock adapters are used when absent) ---
    llm_provider: str = "mock"
    llm_api_key: str | None = Field(default=None, repr=False)

    voice_provider: str = "mock"
    google_cloud_project: str | None = None
    google_application_credentials: str | None = None

    image_provider: str = "mock"
    image_api_key: str | None = Field(default=None, repr=False)

    video_provider: str = "mock"
    video_api_key: str | None = Field(default=None, repr=False)

    # --- Publishing ---
    youtube_client_id: str | None = None
    youtube_client_secret: str | None = Field(default=None, repr=False)
    tiktok_client_id: str | None = None
    tiktok_client_secret: str | None = Field(default=None, repr=False)

    # --- Billing ---
    billing_provider: str | None = None
    billing_secret_key: str | None = Field(default=None, repr=False)

    # --- Cost / quota defaults ---
    default_plan_monthly_credits: int = 100
    max_concurrent_jobs_per_user: int = 3
    max_video_duration_seconds: int = 180

    # --- CORS ---
    cors_allowed_origins: list[str] = ["https://vercel.app"]

@lru_cache
def get_settings() -> Settings:
    return Settings()
