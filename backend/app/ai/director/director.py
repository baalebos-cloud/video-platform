"""
AI Video Director — converts creator intent into a structured,
schema-validated production plan (script + storyboard + voice
direction + metadata). This is the "control plane" described in
blueprint section 18.
"""
import json

from pydantic import ValidationError

from app.ai.prompts.video_director_v1 import PROMPT_VERSION, SYSTEM_PROMPT, build_user_prompt
from app.ai.providers.registry import select_provider
from app.ai.schemas.video_plan import VideoPlan
from app.config.logging import get_logger

logger = get_logger("ai.director")


class PlanValidationError(Exception):
    """Raised when the LLM's structured output fails schema validation."""


async def create_plan(
    *,
    topic: str,
    language: str = "English",
    locale: str = "en-US",
    audience: str = "general",
    platform: str = "youtube_shorts",
    duration: int = 60,
    category: str = "general",
    voice_preferences: dict | None = None,
    visual_style: str = "cinematic_realistic",
    brand_context: dict | None = None,
    creativity: str = "high",
    cta: str | None = None,
) -> tuple[VideoPlan, dict]:
    """
    Returns (validated_plan, generation_metadata). Raises PlanValidationError
    if the provider's output cannot be validated — callers must not proceed
    to expensive asset generation in that case.
    """
    provider = select_provider("llm")
    user_prompt = build_user_prompt(
        topic=topic,
        language=language,
        locale=locale,
        audience=audience,
        platform=platform,
        duration=duration,
        category=category,
        voice_preferences=voice_preferences or {},
        visual_style=visual_style,
        brand_context=brand_context or {},
        creativity=creativity,
        cta=cta,
    )

    response = await provider.complete(SYSTEM_PROMPT, user_prompt, json_mode=True)

    try:
        raw = json.loads(response.text)
        plan = VideoPlan.model_validate(raw)
    except (json.JSONDecodeError, ValidationError) as exc:
        logger.error("director.plan_validation_failed", error=str(exc))
        raise PlanValidationError(f"AI director output failed validation: {exc}") from exc

    metadata = {
        "prompt_version": PROMPT_VERSION,
        "schema_version": "1.0",
        "llm_provider": response.provider,
        "llm_model": response.model,
    }
    logger.info("director.plan_created", title=plan.title, scenes=len(plan.scenes))
    return plan, metadata
