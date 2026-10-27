"""
AI Video Director — converts creator intent into a structured,
schema-validated production plan (script + storyboard + voice
direction + metadata). This is the "control plane" described in
blueprint section 18.
"""
import json

from pydantic import ValidationError

from app.ai.prompts.video_director_v2 import PROMPT_VERSION, SYSTEM_PROMPT, build_user_prompt
from app.ai.providers.registry import select_provider
from app.ai.schemas.video_plan import VideoPlan
from app.config.logging import get_logger

logger = get_logger("ai.director")


class PlanValidationError(Exception):
    """Raised when the LLM's structured output fails schema validation."""


def normalize_video_plan_payload(raw: object) -> object:
    """Accept known field aliases without inventing narration or visual content.

    Older model output used scene_number rather than sequence and sometimes
    supplied scene narration without top-level script/hook. Re-use the
    model-authored narration in those cases; never synthesize missing scenes.
    """
    if not isinstance(raw, dict):
        return raw
    plan = dict(raw)
    scenes = raw.get("scenes")
    if not isinstance(scenes, list):
        return plan
    updated_scenes = []
    for scene in scenes:
        if not isinstance(scene, dict):
            updated_scenes.append(scene)
            continue
        item = dict(scene)
        if "sequence" not in item and "scene_number" in item:
            item["sequence"] = item.pop("scene_number")
        if not item.get("narration"):
            for alias in ("voiceover", "voice_over", "narration_text"):
                if isinstance(item.get(alias), str) and item[alias].strip():
                    item["narration"] = item[alias]
                    break
        if not item.get("visual_prompt"):
            for alias in ("visual_description", "visual"):
                if isinstance(item.get(alias), str) and item[alias].strip():
                    item["visual_prompt"] = item[alias]
                    break
        updated_scenes.append(item)
    plan["scenes"] = updated_scenes
    narrations = [
        scene["narration"].strip() for scene in updated_scenes
        if isinstance(scene, dict) and isinstance(scene.get("narration"), str)
        and scene["narration"].strip()
    ]
    if narrations:
        if not plan.get("script"):
            plan["script"] = " ".join(narrations)
        if not plan.get("hook"):
            plan["hook"] = narrations[0]
    return plan


def validate_video_plan(plan: VideoPlan) -> None:
    """Reject superficially valid JSON that cannot produce a useful video."""
    import math

    if not plan.title.strip() or not plan.hook.strip() or not plan.script.strip():
        raise PlanValidationError("AI director returned an empty title, hook or script.")
    if not plan.scenes:
        raise PlanValidationError("AI director returned no scenes.")
    for position, scene in enumerate(plan.scenes, start=1):
        if scene.sequence != position:
            raise PlanValidationError("AI director scenes must be numbered consecutively from 1.")
        if not scene.narration.strip() or not scene.visual_prompt.strip():
            raise PlanValidationError(f"AI director scene {position} lacks narration or visual direction.")
        if not math.isfinite(scene.duration_seconds) or scene.duration_seconds <= 0:
            raise PlanValidationError(f"AI director scene {position} has invalid duration.")


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
        plan = VideoPlan.model_validate(normalize_video_plan_payload(raw))
    except (json.JSONDecodeError, ValidationError) as exc:
        # Pydantic error strings include the model's raw values, which may
        # contain user-submitted content. Publish field names only.
        paths = []
        if isinstance(exc, ValidationError):
            paths = [
                ".".join(str(part) for part in issue["loc"])
                for issue in exc.errors()
            ]
        logger.error("director.plan_validation_failed", invalid_fields=paths[:10])
        fields = ", ".join(paths[:10]) if paths else "invalid JSON"
        raise PlanValidationError(f"AI director returned an invalid plan; fields: {fields}") from None
    validate_video_plan(plan)

    metadata = {
        "prompt_version": PROMPT_VERSION,
        "schema_version": "1.0",
        "llm_provider": response.provider,
        "llm_model": response.model,
    }
    logger.info("director.plan_created", title=plan.title, scenes=len(plan.scenes))
    return plan, metadata
