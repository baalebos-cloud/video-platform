"""
Provider-agnostic interfaces. Every concrete provider (OpenAI, Anthropic,
Google TTS, Runway, etc.) implements one of these ABCs. Product/domain
code never imports a concrete provider directly — it goes through
app.ai.providers.registry.select_provider so providers stay swappable
per the blueprint's "AI providers must be replaceable through adapters"
principle.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LLMResponse:
    text: str
    raw: dict[str, Any] = field(default_factory=dict)
    model: str = "unknown"
    provider: str = "unknown"


class LLMProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def complete(self, system_prompt: str, user_prompt: str, *, json_mode: bool = False) -> LLMResponse:
        ...


@dataclass
class VoiceSynthesisResult:
    audio_bytes: bytes
    format: str
    duration_seconds: float
    provider: str = "unknown"
    voice_id: str = "unknown"


class VoiceProvider(ABC):
    """Mirrors the VoiceProvider abstraction described in the architecture blueprint (section 9)."""

    name: str = "base"

    @abstractmethod
    async def list_voices(self, locale: str | None = None) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    async def synthesize(self, request: dict[str, Any]) -> VoiceSynthesisResult:
        ...

    @abstractmethod
    async def preview(self, request: dict[str, Any]) -> VoiceSynthesisResult:
        ...

    @abstractmethod
    def supports(self, locale: str) -> bool:
        ...


@dataclass
class ImageGenerationResult:
    image_bytes: bytes
    format: str
    provider: str = "unknown"


class ImageProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def generate(self, prompt: str, *, aspect_ratio: str = "9:16") -> ImageGenerationResult:
        ...


@dataclass
class VideoGenerationResult:
    video_bytes: bytes
    format: str
    duration_seconds: float
    provider: str = "unknown"


class VideoProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def generate_clip(self, scene_spec: dict[str, Any]) -> VideoGenerationResult:
        ...


class PublishingProvider(ABC):
    """Mirrors the PublishingProvider interface described in the architecture blueprint (section 13)."""

    name: str = "base"

    @abstractmethod
    async def authenticate(self, auth_code: str) -> dict[str, Any]:
        ...

    @abstractmethod
    async def refresh_credentials(self, token_ref: str) -> dict[str, Any]:
        ...

    @abstractmethod
    async def validate_video(self, asset_ref: str) -> bool:
        ...

    @abstractmethod
    async def publish(self, asset_ref: str, metadata: dict[str, Any]) -> dict[str, Any]:
        ...

    @abstractmethod
    async def get_status(self, external_post_id: str) -> dict[str, Any]:
        ...

    @abstractmethod
    async def fetch_analytics(self, external_post_id: str) -> dict[str, Any]:
        ...
