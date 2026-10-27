"""Offline 3-minute generation contracts: no AI calls or rendering costs."""
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.ai.director.director import PlanValidationError, validate_long_form_plan, validate_video_plan
from app.ai.prompts.video_director_v4 import PROMPT_VERSION, build_user_prompt
from app.ai.schemas.video_plan import VideoPlan
from app.api.v1.videos import GenerateVideoRequest
from app.config.settings import Settings
from app.workers.tasks.pipeline_task import scene_runtime_floor
from app.workers.worker import WorkerSettings


def three_minute_plan(*, words_per_scene=33, duration_per_scene=15, count=12):
    scenes = []
    for index in range(count):
        speech = " ".join(["engineering"] * words_per_scene)
        scenes.append({
            "sequence": index + 1,
            "narration": speech,
            "visual_prompt": f"A real Nigerian engineer explaining step {index+1} at work",
            "duration_seconds": duration_per_scene,
        })
    return VideoPlan(title="Practical AI Engineering", hook="AI at work",
                     script=" ".join(s["narration"] for s in scenes), scenes=scenes)


def test_three_minute_request_is_valid_and_four_minutes_rejected():
    valid = GenerateVideoRequest(project_id=uuid4(), topic="Realistic AI engineering", duration_seconds=180)
    assert valid.duration_seconds == 180
    with pytest.raises(ValidationError):
        GenerateVideoRequest(project_id=uuid4(), topic="Realistic AI engineering", duration_seconds=181)
    assert Settings(_env_file=None).max_video_duration_seconds == 180


def test_long_form_director_prompt_explicitly_requests_real_narration():
    prompt = build_user_prompt(
        topic="How AI is changing production engineering", language="English",
        locale="en-US", audience="general", platform="youtube_landscape",
        duration=180, category="educational", voice_preferences={},
        visual_style="cinematic_realistic", brand_context={}, creativity="high", cta=None,
    )
    assert PROMPT_VERSION == "video-director-v4"
    assert "target_runtime_seconds=180" in prompt
    assert "narration_word_target=375" in prompt
    assert "recommended_scene_count=12" in prompt
    assert "maximum_scene_count=16" in prompt


def test_long_form_director_accepts_full_three_minute_storyboard():
    plan = three_minute_plan()
    validate_video_plan(plan)
    validate_long_form_plan(plan, 180)


def test_long_form_rejects_short_script_before_any_media_generation():
    with pytest.raises(PlanValidationError, match="too little spoken narration"):
        validate_long_form_plan(three_minute_plan(words_per_scene=7), 180)


def test_long_form_rejects_incorrect_total_scene_duration():
    with pytest.raises(PlanValidationError, match="do not cover"):
        validate_long_form_plan(three_minute_plan(duration_per_scene=5), 180)


def test_long_form_scene_count_is_bounded_to_protect_free_media_quota():
    with pytest.raises(PlanValidationError, match="9-16"):
        validate_long_form_plan(three_minute_plan(count=6, words_per_scene=65, duration_per_scene=30), 180)


def test_audio_shorter_than_plan_keeps_full_three_minute_runtime():
    scenes = [SimpleNamespace(id=uuid4(), duration_seconds=14.5) for _ in range(12)]
    floors = scene_runtime_floor(scenes, 180)
    assert len(floors) == 12
    assert sum(floors.values()) >= 180
    assert all(abs(seconds - 15) < 0.001 for seconds in floors.values())


def test_long_form_does_not_shorten_slow_narration():
    scenes = [SimpleNamespace(id=uuid4(), duration_seconds=15) for _ in range(12)]
    floors = scene_runtime_floor(scenes, 180)
    measured_voice = 18.0
    assert max(measured_voice, floors[str(scenes[0].id)]) == 18


def test_short_form_keeps_original_voice_duration_behavior():
    scenes = [SimpleNamespace(id=uuid4(), duration_seconds=10) for _ in range(6)]
    assert scene_runtime_floor(scenes, 60) == {}


def test_long_form_worker_has_sufficient_time_for_render():
    assert WorkerSettings.max_jobs == 1
    assert WorkerSettings.job_timeout >= 1800


@pytest.mark.asyncio
async def test_long_form_retries_underlength_plan_once_before_media():
    import json
    from unittest.mock import patch
    from app.ai.director.director import create_plan
    from app.ai.providers.base import LLMResponse

    short = three_minute_plan(words_per_scene=5)
    full = three_minute_plan()
    class Provider:
        calls = 0
        async def complete(self, system_prompt, user_prompt, *, json_mode=False):
            self.calls += 1
            assert json_mode
            if self.calls == 2:
                assert "failed the full-length constraint" in user_prompt
            plan = short if self.calls == 1 else full
            return LLMResponse(text=plan.model_dump_json(), model="fake", provider="gemini")

    provider = Provider()
    with patch("app.ai.director.director.select_provider", return_value=provider):
        plan, meta = await create_plan(topic="Practical AI", duration=180)
    assert provider.calls == 2
    assert meta["prompt_version"] == "video-director-v4"
    assert len(plan.scenes) == 12


@pytest.mark.asyncio
async def test_long_form_two_short_plans_fail_before_any_tts():
    from unittest.mock import patch
    from app.ai.director.director import create_plan
    from app.ai.providers.base import LLMResponse

    class Provider:
        calls = 0
        async def complete(self, *args, **kwargs):
            self.calls += 1
            return LLMResponse(
                text=three_minute_plan(words_per_scene=5).model_dump_json(),
                model="fake", provider="gemini",
            )

    provider = Provider()
    with patch("app.ai.director.director.select_provider", return_value=provider):
        with pytest.raises(PlanValidationError, match="too little spoken narration"):
            await create_plan(topic="Practical AI", duration=180)
    assert provider.calls == 2


def test_production_327_word_sixteen_scene_documentary_is_accepted():
    """Production screenshot: 327 words for 180 seconds is 109 WPM, not failure."""
    plan = three_minute_plan(words_per_scene=21, duration_per_scene=11.25, count=16)
    # Reproduce 327 words exactly while keeping 16 complete scenes.
    for scene in plan.scenes[:9]:
        scene.narration = " ".join(["engineering"] * 20)
    plan.script = " ".join(scene.narration for scene in plan.scenes)
    assert sum(len(scene.narration.split()) for scene in plan.scenes) == 327
    validate_video_plan(plan)
    validate_long_form_plan(plan, 180)


def test_long_form_rejects_less_than_one_hundred_words_per_minute():
    plan = three_minute_plan(words_per_scene=24, count=12)
    assert sum(len(scene.narration.split()) for scene in plan.scenes) == 288
    with pytest.raises(PlanValidationError, match="minimum 300"):
        validate_long_form_plan(plan, 180)


@pytest.mark.asyncio
async def test_natural_speaking_rate_needs_only_one_gemini_request():
    from unittest.mock import patch
    from app.ai.director.director import create_plan
    from app.ai.providers.base import LLMResponse

    plan = three_minute_plan(words_per_scene=21, duration_per_scene=11.25, count=16)
    for scene in plan.scenes[:9]:
        scene.narration = " ".join(["engineering"] * 20)
    plan.script = " ".join(scene.narration for scene in plan.scenes)
    class Provider:
        calls = 0
        async def complete(self, *args, **kwargs):
            self.calls += 1
            return LLMResponse(text=plan.model_dump_json(), model="test", provider="gemini")

    provider = Provider()
    with patch("app.ai.director.director.select_provider", return_value=provider):
        output, metadata = await create_plan(topic="Engineering documentary", duration=180)
    assert provider.calls == 1
    assert len(output.scenes) == 16
    assert metadata["prompt_version"] == "video-director-v4"
