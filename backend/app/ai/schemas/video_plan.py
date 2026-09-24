"""
Structured-output schema for the AI Video Director.

The LLM response is validated against this schema *before* any
expensive downstream asset generation is triggered (blueprint
principle: "Validate structured output before creating expensive
assets").
"""
from pydantic import BaseModel, Field


class SceneSpec(BaseModel):
    sequence: int
    narration: str = ""
    visual_prompt: str = ""
    duration_seconds: float = 5.0
    camera: str | None = None
    lighting: str | None = None
    on_screen_text: str | None = None
    continuity_reference_ids: list[str] = Field(default_factory=list)
    negative_constraints: list[str] = Field(default_factory=list)


class VoiceDirection(BaseModel):
    personality: str | None = None
    emotion: str | None = None
    energy: str | None = None
    pace: float = 1.0
    pitch: str | None = None


class VideoPlan(BaseModel):
    title: str
    hook: str
    script: str
    voice_direction: VoiceDirection = Field(default_factory=VoiceDirection)
    scenes: list[SceneSpec] = Field(default_factory=list)
    captions: dict = Field(default_factory=dict)
    music: dict = Field(default_factory=dict)
    sfx: list[str] = Field(default_factory=list)
    thumbnail_prompt: str = ""
    description: str = ""
    hashtags: list[str] = Field(default_factory=list)
    cta: str = ""
    monetization_angles: list[str] = Field(default_factory=list)
    quality_checks: list[str] = Field(default_factory=list)
