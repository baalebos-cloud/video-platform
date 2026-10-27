"""Production regression: Gemini must emit a renderable video plan, not just valid JSON."""
import json
from unittest.mock import patch

import httpx
import pytest

from app.ai.director.director import (
    PlanValidationError, create_plan, normalize_video_plan_payload, validate_video_plan,
)
from app.ai.providers.base import LLMResponse
from app.ai.providers.llm.gemini import GeminiLLMProvider
from app.ai.schemas.video_plan import GEMINI_VIDEO_PLAN_SCHEMA, VideoPlan


@pytest.mark.asyncio
async def test_gemini_json_request_carries_required_video_plan_schema():
    seen = []

    def reply(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={
            "candidates": [{"content": {"parts": [{"text": json.dumps({
                "title": "AI at Work", "hook": "AI is helping workers.",
                "script": "AI is helping workers.",
                "scenes": [{
                    "sequence": 1, "narration": "AI is helping workers.",
                    "visual_prompt": "People using laptops in a bright office",
                    "duration_seconds": 5,
                }],
            })}]}}]
        })

    provider = GeminiLLMProvider(
        api_key="unit-test-key",
        client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(reply)),
    )
    result = await provider.complete("director", "create a short video", json_mode=True)
    assert VideoPlan.model_validate_json(result.text).scenes[0].sequence == 1

    config = seen[0]["generationConfig"]
    assert config["responseMimeType"] == "application/json"
    schema = config["responseJsonSchema"]
    assert schema == GEMINI_VIDEO_PLAN_SCHEMA
    assert set(("title", "hook", "script", "scenes")).issubset(schema["required"])
    assert set(("sequence", "narration", "visual_prompt", "duration_seconds")).issubset(
        schema["properties"]["scenes"]["items"]["required"]
    )


@pytest.mark.asyncio
async def test_legacy_gemini_response_converts_scene_number_and_reuses_narration():
    # The exact shape that caused the production 7-field validation error.
    original = {
        "title": "How AI Actually Helps",
        "scenes": [
            {"scene_number": 1, "duration_seconds": 4, "narration": "AI helps people at work.",
             "visual_prompt": "Office workers using computers", "sound_effects": []},
            {"scene_number": 2, "duration_seconds": 4, "narration": "It saves time.",
             "visual_prompt": "An engineer watching a dashboard", "sound_effects": []},
        ],
    }

    class Provider:
        async def complete(self, system_prompt, user_prompt, *, json_mode=False):
            assert json_mode
            return LLMResponse(text=json.dumps(original), provider="gemini", model="test")

    with patch("app.ai.director.director.select_provider", return_value=Provider()):
        plan, metadata = await create_plan(topic="AI helping workers", duration=8)

    assert [scene.sequence for scene in plan.scenes] == [1, 2]
    assert plan.hook == "AI helps people at work."
    assert plan.script == "AI helps people at work. It saves time."
    assert metadata["prompt_version"] == "video-director-v3"
    assert "hook" not in original  # Input payload was not mutated.
    assert "sequence" not in original["scenes"][0]


@pytest.mark.asyncio
async def test_malformed_plan_reveals_only_invalid_field_names():
    raw = {"title": "Example", "scenes": [
        {"scene_number": "not-an-integer", "narration": "Safe narrated sentence.",
         "visual_prompt": "A location", "duration_seconds": 5},
    ]}

    class Provider:
        async def complete(self, *args, **kwargs):
            return LLMResponse(text=json.dumps(raw), provider="gemini", model="test")

    with patch("app.ai.director.director.select_provider", return_value=Provider()):
        with pytest.raises(PlanValidationError) as error:
            await create_plan(topic="A topic")
    assert "scenes.0.sequence" in str(error.value)
    assert "not-an-integer" not in str(error.value)
    assert "input_value" not in str(error.value)


def test_dont_fabricate_narration_for_incomplete_scenes():
    incomplete = {"title": "Video", "scenes": [
        {"scene_number": 1, "duration_seconds": 3, "visual_prompt": "Office workers"},
    ]}
    normalized = normalize_video_plan_payload(incomplete)
    assert "hook" not in normalized and "script" not in normalized
    with pytest.raises(PlanValidationError):
        validate_video_plan(VideoPlan(
            title="Video", hook="Hook", script="Text",
            scenes=normalized["scenes"],
        ))


def test_valid_plan_needs_usable_scenes_and_consecutive_order():
    with pytest.raises(PlanValidationError, match="no scenes"):
        validate_video_plan(VideoPlan(title="Video", hook="Hook", script="Text"))
    with pytest.raises(PlanValidationError, match="numbered consecutively"):
        validate_video_plan(VideoPlan(
            title="Video", hook="Hook", script="Text",
            scenes=[{"sequence": 2, "narration": "Speech", "visual_prompt": "Office", "duration_seconds": 3}],
        ))


@pytest.mark.asyncio
async def test_production_two_errors_hook_missing_and_script_list():
    """Screenshot regression: hook missing and script is an array of scenes."""
    original = {
        "title": "How AI is Transforming Cities",
        "script": [
            {"scene_number": 1, "duration_seconds": 3, "narration": "Artificial intelligence is changing cities."},
            {"scene_number": 2, "duration_seconds": 3, "narration": "It helps people move and work."},
        ],
        "scenes": [
            {"scene_number": 1, "duration_seconds": 3, "narration": "Artificial intelligence is changing cities.",
             "visual_prompt": "Sunrise over a real city skyline"},
            {"scene_number": 2, "duration_seconds": 3, "narration": "It helps people move and work.",
             "visual_prompt": "Busy city workers on a street"},
        ],
    }
    normalized = normalize_video_plan_payload(original)
    plan = VideoPlan.model_validate(normalized)
    validate_video_plan(plan)
    assert plan.hook == "Artificial intelligence is changing cities."
    assert plan.script == "Artificial intelligence is changing cities. It helps people move and work."
    assert [scene.sequence for scene in plan.scenes] == [1, 2]
    assert isinstance(original["script"], list)


def test_scene_narration_can_come_from_parallel_script_array():
    raw = {
        "title": "Narrated Footage",
        "script": [
            {"scene_number": 1, "voiceover": "Our cities are changing."},
            {"scene_number": 2, "dialogue": "Technology can help."},
        ],
        "scenes": [
            {"scene_number": 1, "visual_prompt": "A real crowded city", "duration_seconds": 4},
            {"scene_number": 2, "visual_prompt": "Engineer using a computer", "duration_seconds": 4},
        ],
    }
    plan = VideoPlan.model_validate(normalize_video_plan_payload(raw))
    validate_video_plan(plan)
    assert plan.scenes[0].narration == "Our cities are changing."
    assert plan.scenes[1].narration == "Technology can help."
    assert plan.script == "Our cities are changing. Technology can help."


def test_misaligned_script_entries_must_not_produce_invented_speech():
    raw = {
        "title": "Mismatch",
        "script": [{"scene_number": 22, "text": "This belongs elsewhere."}],
        "scenes": [{"scene_number": 1, "visual_prompt": "Office interior", "duration_seconds": 5}],
    }
    plan = VideoPlan.model_validate(normalize_video_plan_payload(raw))
    with pytest.raises(PlanValidationError, match="lacks narration"):
        validate_video_plan(plan)
    assert plan.scenes[0].narration == ""


def test_shot_direction_is_never_mistaken_for_spoken_dialogue():
    raw = {
        "title": "A Scene",
        "script": [{"transition": "Fade to black", "camera": "Fast pan"}],
        "scenes": [{"scene_number": 1, "visual_prompt": "Clouds moving", "duration_seconds": 5}],
    }
    normalized = normalize_video_plan_payload(raw)
    assert isinstance(normalized["script"], list)
    assert normalized.get("hook") is None
    with pytest.raises(Exception):
        VideoPlan.model_validate(normalized)
