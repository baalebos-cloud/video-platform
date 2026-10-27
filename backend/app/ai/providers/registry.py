"""
Provider selection / capability discovery.

Mirrors blueprint section 18.1: selection considers task type and
configuration rather than hard-coding one model for every request.
Optional OpenAI voice/image adapters are registered only when selected;
the mock adapters remain the default for local development and CI.
"""
from functools import lru_cache
from typing import Literal

from app.ai.providers.base import ImageProvider, LLMProvider, VideoProvider, VoiceProvider
from app.ai.providers.image.mock import MockImageProvider
from app.ai.providers.image.openai import OpenAIImageProvider
from app.ai.providers.llm.baalebos_gateway import BaalebosGatewayLLMProvider
from app.ai.providers.llm.mock import MockLLMProvider
from app.ai.providers.llm.gemini import GeminiLLMProvider
from app.ai.providers.image.cloudflare import CloudflareImageProvider
from app.ai.providers.tts.cloudflare import CloudflareVoiceProvider
from app.ai.providers.tts.mock import MockVoiceProvider
from app.ai.providers.tts.openai import OpenAIVoiceProvider
from app.ai.providers.video.mock import MockVideoProvider
from app.config.settings import get_settings

TaskType = Literal["llm", "voice", "image", "video"]


@lru_cache
def _llm_registry() -> dict[str, LLMProvider]:
    settings = get_settings()
    providers: dict[str, LLMProvider] = {
        "mock": MockLLMProvider(),
        "baalebos_ai": BaalebosGatewayLLMProvider(),
    }
    if settings.llm_provider == "gemini":
        providers["gemini"] = GeminiLLMProvider(
            api_key=settings.gemini_api_key or "", model=settings.gemini_model,
        )
    return providers
    # Register further real adapters here, e.g.:
    # "openai": OpenAILLMProvider(api_key=settings.llm_api_key)


@lru_cache
def _voice_registry() -> dict[str, VoiceProvider]:
    settings = get_settings()
    providers: dict[str, VoiceProvider] = {"mock": MockVoiceProvider()}
    if settings.voice_provider == "openai":
        providers["openai"] = OpenAIVoiceProvider(
            api_key=settings.openai_api_key or "",
            model=settings.openai_tts_model,
            default_voice=settings.openai_tts_default_voice,
        )
    if settings.voice_provider == "cloudflare":
        providers["cloudflare"] = CloudflareVoiceProvider(
            account_id=settings.cloudflare_account_id or "",
            api_token=settings.cloudflare_api_token or "",
            model=settings.cloudflare_tts_model,
        )
    return providers


@lru_cache
def _image_registry() -> dict[str, ImageProvider]:
    settings = get_settings()
    providers: dict[str, ImageProvider] = {"mock": MockImageProvider()}
    if settings.image_provider == "openai":
        providers["openai"] = OpenAIImageProvider(
            api_key=settings.openai_api_key or "",
            model=settings.openai_image_model,
            quality=settings.openai_image_quality,
        )
    if settings.image_provider == "cloudflare":
        providers["cloudflare"] = CloudflareImageProvider(
            account_id=settings.cloudflare_account_id or "",
            api_token=settings.cloudflare_api_token or "",
            model=settings.cloudflare_image_model,
        )
    return providers


@lru_cache
def _video_registry() -> dict[str, VideoProvider]:
    return {"mock": MockVideoProvider()}


def select_provider(task: TaskType, **_capability_hints) -> LLMProvider | VoiceProvider | ImageProvider | VideoProvider:
    """
    Selects a provider for the given task.

    `_capability_hints` (locale, quality, max_cost, duration_seconds, etc.)
    is accepted so this signature matches the blueprint's
    `select_provider(task=..., locale=..., quality=..., max_cost=...)`
    call pattern. The current implementation is configuration-driven
    (one active provider per task type); extend with real scoring logic
    (latency, cost, quality tier) as more providers are registered.
    """
    settings = get_settings()
    if task == "llm":
        return _llm_registry()[settings.llm_provider]
    if task == "voice":
        return _voice_registry()[settings.voice_provider]
    if task == "image":
        return _image_registry()[settings.image_provider]
    if task == "video":
        return _video_registry()[settings.video_provider]
    raise ValueError(f"Unknown provider task type: {task}")
