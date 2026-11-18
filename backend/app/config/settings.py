"""
Central application configuration.

All configuration is loaded from environment variables (see .env.example
at the repo root). Nothing here should contain a real secret — defaults
are safe-for-local-dev placeholders only.
"""
from functools import lru_cache
from typing import Literal
import uuid

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _is_public_https_url(url: str | None) -> bool:
    """Reject a URL that could redirect a server-side request at internal
    infrastructure (SSRF): only a plausibly-public https:// hostname passes.
    Shared by every setting that feeds an operator-configured outbound URL
    into an httpx call made from inside the backend/worker.
    """
    if not url:
        return False
    from ipaddress import ip_address
    from urllib.parse import urlsplit

    parsed = urlsplit(url)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not hostname or parsed.username or parsed.password or parsed.fragment:
        return False
    if hostname in {"localhost", "metadata.google.internal"} or hostname.endswith((".internal", ".local")):
        return False
    try:
        literal = ip_address(hostname)
    except ValueError:
        return True  # DNS hostname approved by operator; disable redirects in client.
    return literal.is_global


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Application ---
    app_env: Literal["development", "staging", "production", "test"] = "development"
    app_name: str = "AI Video Creator & Monetization Platform"
    app_url: str = "http://localhost:3000"
    api_url: str = "http://localhost:8000"
    debug: bool = False

    # --- Security ---
    jwt_secret: str = Field(default="replace_me_in_env", repr=False)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 14
    # Privileged user IDs are provisioned by the operator. NEVER grant
    # privileges based on an unverified signup email address.
    admin_user_ids_raw: str = ""
    # Generate with cryptography.fernet.Fernet.generate_key() and store
    # in the deployment secret manager. Changing this key invalidates MFA
    # enrollment unless the credentials are securely migrated.
    admin_mfa_encryption_key: str | None = Field(default=None, repr=False)
    # Optional transactional password reset email delivery (Resend HTTPS API).
    reset_email_api_key: str | None = Field(default=None, repr=False)
    reset_email_from: str | None = None

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
    storage_region: str = "auto"
    storage_access_key: str = "minioadmin"
    storage_secret_key: str = Field(default="minioadmin", repr=False)
    storage_public_base_url: str | None = None

    # --- AI providers (all optional — mock adapters are used when absent) ---
    llm_provider: Literal["mock", "baalebos_ai", "gemini"] = "mock"
    gemini_api_key: str | None = Field(default=None, repr=False)
    gemini_model: str = "gemini-3.5-flash-lite"
    llm_api_key: str | None = Field(default=None, repr=False)
    # Only used by the "baalebos_ai" LLM provider (a personal multi-provider
    # gateway) — the full webhook URL to POST {"prompt": "..."} to.
    llm_gateway_url: str | None = None
    
    voice_provider: Literal["mock", "openai", "cloudflare"] = "mock"
    # Shared for both optional media providers. Keep server-side only.
    openai_api_key: str | None = Field(default=None, repr=False)
    openai_tts_model: str = "gpt-4o-mini-tts"
    openai_tts_default_voice: str = "alloy"
    openai_image_model: str = "gpt-image-1.5"
    openai_image_quality: Literal["low", "medium", "high"] = "medium"
    google_cloud_project: str | None = None
    google_application_credentials: str | None = None

    image_provider: Literal["mock", "openai", "cloudflare"] = "mock"
    cloudflare_account_id: str | None = None
    cloudflare_api_token: str | None = Field(default=None, repr=False)
    cloudflare_image_model: str = "@cf/black-forest-labs/flux-1-schnell"
    cloudflare_tts_model: str = "@cf/myshell-ai/melotts"
    pixabay_api_key: str | None = Field(default=None, repr=False)
    pixabay_video_api_url: str = "https://pixabay.com/api/videos/"
    stock_footage_enabled: bool = False
    image_api_key: str | None = Field(default=None, repr=False)

    # "mock" composes a still image + Ken Burns motion (zero cost, always
    # available). "replicate" calls a real generative-video model — see
    # app/ai/providers/video/replicate.py for what REPLICATE_VIDEO_MODEL
    # must look like and why its input fields are configurable.
    video_provider: Literal["mock", "replicate"] = "mock"
    video_api_key: str | None = Field(default=None, repr=False)
    replicate_api_token: str | None = Field(default=None, repr=False)
    # "owner/model" as it appears in the model's Replicate URL, e.g.
    # "kwaivgi/kling-v1.6-standard" or "google/veo-3-fast". Pick a model
    # that supports image-conditioning if scene-to-scene visual continuity
    # matters (see docs/video-generation-upgrade.md).
    replicate_video_model: str = "kwaivgi/kling-v1.6-standard"
    replicate_video_prompt_field: str = "prompt"
    # Set to "" to disable passing the generated scene image as a
    # conditioning frame (e.g. for a pure text-to-video model).
    replicate_video_image_field: str = "image"
    # Extra static inputs the chosen model requires/accepts, as JSON, e.g.
    # '{"duration": 5, "aspect_ratio": "9:16"}'. Merged into every request.
    replicate_video_extra_input_raw: str = "{}"
    replicate_video_poll_timeout_seconds: int = Field(default=240, ge=30, le=900)

    @property
    def replicate_video_extra_input(self) -> dict:
        import json

        raw = self.replicate_video_extra_input_raw.strip()
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    # Private licensed inference is optional and OFF unless configured.
    # Never enable for a research-only model in a commercial product.
    voice_clone_endpoint: str | None = None
    voice_clone_token: str | None = Field(default=None, repr=False)
    voice_clone_license_approved: bool = False

    @property
    def voice_clone_enabled(self) -> bool:
        if not (self.voice_clone_license_approved and self.voice_clone_endpoint and self.voice_clone_token):
            return False
        return _is_public_https_url(self.voice_clone_endpoint)

    @property
    def llm_gateway_url_is_safe(self) -> bool:
        """llm_gateway_url is operator-configured but still an outbound URL
        the backend/worker POSTs user-derived prompt text to on every
        generation — apply the same SSRF guard as voice_clone_endpoint
        rather than trusting it just because it came from settings."""
        return _is_public_https_url(self.llm_gateway_url)

    # --- Publishing ---
    youtube_client_id: str | None = None
    youtube_client_secret: str | None = Field(default=None, repr=False)
    tiktok_client_id: str | None = None
    tiktok_client_secret: str | None = Field(default=None, repr=False)
    publishing_token_encryption_key: str | None = Field(default=None, repr=False)

    # --- Billing ---
    billing_provider: str | None = None
    billing_secret_key: str | None = Field(default=None, repr=False)

    # --- Cost / quota defaults ---
    default_plan_monthly_credits: int = 100  # reserved for future recurring plans (no automatic grant)
    credit_enforcement_enabled: bool = False
    signup_starter_credits: int = Field(default=0, ge=0, le=10000)
    credits_per_30_seconds: int = Field(default=10, ge=1, le=1000)
    scene_regeneration_credits: int = Field(default=2, ge=1, le=100)
    voice_preview_credits: int = Field(default=1, ge=1, le=100)
    # Global, daily circuit breaker across all live media calls. Not a USD budget.
    max_daily_live_media_calls: int = Field(default=100, ge=1, le=100000)
    max_concurrent_jobs_per_user: int = 3
    max_video_duration_seconds: int = 180

    # --- Worker topology ---
    # When true, the API process itself runs the arq worker loop as a
    # background asyncio task instead of relying on a separate worker
    # process/service. This exists specifically for free-tier hosting
    # (e.g. Render's free plan only offers a "Web Service" type; its
    # "Background Worker" type is paid-only) — one process does both
    # jobs, at the cost of the API and worker no longer scaling or
    # restarting independently. Prefer a real separate worker
    # (docker-compose's `worker` service, or a paid Background Worker)
    # once budget allows; this is an MVP-stage cost tradeoff, not the
    # long-term recommended topology.
    run_worker_in_process: bool = False

    # --- CORS ---
    # Kept as a raw string (not list[str]) because pydantic-settings
    # attempts strict json.loads() on any list-typed env var *before* any
    # field_validator runs — which rejects a plain comma-separated value.
    # A comma-separated string is far less error-prone to paste into
    # Render's/Vercel's single-line env var UI than a quoted JSON array,
    # so `cors_allowed_origins` (below) parses this instead.
    cors_allowed_origins_raw: str = "http://localhost:3000"

    @model_validator(mode="after")
    def require_secure_production_settings(self) -> "Settings":
        if (self.voice_provider == "openai" or self.image_provider == "openai") and not (
            self.openai_api_key and self.openai_api_key.strip()
        ):
            raise ValueError("OPENAI_API_KEY is required when VOICE_PROVIDER or IMAGE_PROVIDER is openai")
        if self.llm_provider == "gemini" and not self.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is required when LLM_PROVIDER=gemini")
        if self.image_provider == "cloudflare" or self.voice_provider == "cloudflare":
            if not self.cloudflare_account_id or not self.cloudflare_api_token:
                raise ValueError("CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN are required")
        if self.stock_footage_enabled and not self.pixabay_api_key:
            raise ValueError("PIXABAY_API_KEY is required when STOCK_FOOTAGE_ENABLED=true")
        if self.video_provider == "replicate":
            if not self.replicate_api_token:
                raise ValueError("REPLICATE_API_TOKEN is required when VIDEO_PROVIDER=replicate")
            if "/" not in self.replicate_video_model:
                raise ValueError("REPLICATE_VIDEO_MODEL must be 'owner/model' as shown on replicate.com")
        if self.pixabay_video_api_url != "https://pixabay.com/api/videos/":
            raise ValueError("PIXABAY_VIDEO_API_URL must use the official Pixabay video API")
        try:
            self.admin_user_ids
        except ValueError as exc:
            raise ValueError("ADMIN_USER_IDS_RAW must be comma-separated user UUIDs") from exc
        if self.app_env == "production":
            if bool(self.reset_email_api_key) != bool(self.reset_email_from):
                raise ValueError("RESET_EMAIL_API_KEY and RESET_EMAIL_FROM must be configured together")
            if self.reset_email_api_key and not self.app_url.startswith("https://"):
                raise ValueError("APP_URL must use https:// for production password reset links")
            if self.admin_user_ids:
                if not self.admin_mfa_encryption_key:
                    raise ValueError("ADMIN_MFA_ENCRYPTION_KEY is required when production administrators are configured")
                from cryptography.fernet import Fernet
                try:
                    Fernet(self.admin_mfa_encryption_key.encode("ascii"))
                except (ValueError, TypeError):
                    raise ValueError("ADMIN_MFA_ENCRYPTION_KEY must be a valid Fernet encryption key") from None
            if (self.voice_provider == "openai" or self.image_provider == "openai") and not self.credit_enforcement_enabled:
                raise ValueError("CREDIT_ENFORCEMENT_ENABLED must be true for live media in production")
            if len(self.jwt_secret) < 32 or self.jwt_secret.lower().startswith(("replace", "dev-", "test-")):
                raise ValueError("Production JWT_SECRET must be a strong, non-placeholder value (at least 32 characters)")
            if self.debug:
                raise ValueError("DEBUG must be disabled in production")
        return self

    @property
    def admin_user_ids(self) -> frozenset[uuid.UUID]:
        return frozenset(
            uuid.UUID(value.strip()) for value in self.admin_user_ids_raw.split(",") if value.strip()
        )

    @property
    def cors_allowed_origins(self) -> list[str]:
        raw = self.cors_allowed_origins_raw.strip()
        if raw.startswith("["):
            import json

            return json.loads(raw)
        return [origin.strip() for origin in raw.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
