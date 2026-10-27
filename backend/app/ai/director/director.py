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


def _spoken_text(value: object) -> str | None:
    """Only extract actual speech text, never technical shot descriptions."""
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, dict):
        for key in ("narration", "voiceover", "voice_over", "narration_text",
                    "spoken_text", "dialogue", "speech", "text"):
            text = value.get(key)
            if isinstance(text, str) and text.strip():
                return text.strip()
    return None


def normalize_video_plan_payload(raw: object) -> object:
    """Normalize known Gemini variants without synthesizing original content.

    Gemini can return a scene-indexed script array instead of a top-level
    string, and older models use `scene_number` rather than `sequence`.
    Use existing spoken text; do not substitute descriptions for narration.
    """
    if not isinstance(raw, dict):
        return raw

    plan = dict(raw)
    scenes = raw.get("scenes")
    if not isinstance(scenes, list):
        return plan

    script_entries = raw.get("script")
    # Only use a parallel array to fill missing narration when the array
    # has the same number of scenes and entries have matching scene numbers
    # when explicitly supplied. This avoids assigning speech to wrong shots.
    script_items = script_entries if isinstance(script_entries, list) else []
    align_script = len(script_items) == len(scenes)
    updated_scenes = []
    for index, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            updated_scenes.append(scene)
            continue
        item = dict(scene)
        if "sequence" not in item and "scene_number" in item:
            item["sequence"] = item.pop("scene_number")

        spoken = _spoken_text(item)
        if not spoken and align_script:
            entry = script_items[index]
            if isinstance(entry, dict):
                entry_seq = entry.get("sequence", entry.get("scene_number"))
                try:
                    same_scene = entry_seq is None or int(entry_seq) == int(item.get("sequence"))
                except (ValueError, TypeError):
                    same_scene = False
            else:
                same_scene = True
            if same_scene:
                spoken = _spoken_text(entry)
        if spoken and not isinstance(item.get("narration"), str):
            item["narration"] = spoken
        elif spoken and not item.get("narration"):
            item["narration"] = spoken

        if not item.get("visual_prompt"):
            for alias in ("visual_description", "visual", "visuals", "shot_description"):
                if isinstance(item.get(alias), str) and item[alias].strip():
                    item["visual_prompt"] = item[alias].strip()
                    break
        updated_scenes.append(item)
    plan["scenes"] = updated_scenes

    narrations = [
        scene["narration"].strip() for scene in updated_scenes
        if isinstance(scene, dict) and isinstance(scene.get("narration"), str)
        and scene["narration"].strip()
    ]
    # A script list isn't accepted by VideoPlan. Prefer complete scene
    # narration as canonical (what the renderer actually speaks).
    if isinstance(script_entries, list):
        if len(narrations) == len(updated_scenes) and narrations:
            plan["script"] = " ".join(narrations)
        else:
            fragments = [_spoken_text(entry) for entry in script_entries]
            if fragments and all(fragments):
                plan["script"] = " ".join(fragments)
            # Otherwise leave the invalid value for Pydantic to reject.
    elif not plan.get("script") and len(narrations) == len(updated_scenes) and narrations:
        plan["script"] = " ".join(narrations)

    if not plan.get("hook"):
        for alias in ("opening_hook", "opening_line", "intro"):
            text = _spoken_text(plan.get(alias))
            if text:
                plan["hook"] = text
                break
        if not plan.get("hook"):
            plan["hook"] = narrations[0] if narrations else _spoken_text(plan.get("script"))
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
