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


# Gemini v1beta uses generationConfig.responseMimeType alongside
# generationConfig.responseJsonSchema to constrain actual output keys.
# Keep the generation schema deliberately small: the rest of VideoPlan has
# safe defaults, and a complicated schema can be rejected by Gemini.
# All required fields are used by the renderer and stored in PostgreSQL.
GEMINI_VIDEO_PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "Specific title for the video"},
        "hook": {"type": "string", "description": "Opening line that hooks viewers"},
        "script": {"type": "string", "description": "Entire narrated script matching all scenes"},
        "scenes": {
            "type": "array",
            "minItems": 1,
            "description": "Ordered narration and visuals for each scene",
            "items": {
                "type": "object",
                "properties": {
                    "sequence": {"type": "integer", "description": "One-based scene order: 1, 2, 3..."},
                    "narration": {"type": "string", "description": "Speakable voiceover for this scene"},
                    "visual_prompt": {"type": "string", "description": "Detailed concrete cinematic shot"},
                    "duration_seconds": {"type": "number", "minimum": 1},
                    "camera": {"type": "string"},
                    "lighting": {"type": "string"},
                },
                "required": ["sequence", "narration", "visual_prompt", "duration_seconds"],
                "additionalProperties": False,
            },
        },
        "description": {"type": "string"},
        "cta": {"type": "string"},
        "hashtags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "hook", "script", "scenes"],
    "additionalProperties": False,
}
