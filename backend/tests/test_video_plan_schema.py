"""Unit tests for the AI Director's structured-output schema validation."""
from app.ai.schemas.video_plan import VideoPlan


def test_video_plan_accepts_minimal_valid_payload():
    plan = VideoPlan(title="t", hook="h", script="s")
    assert plan.scenes == []
    assert plan.voice_direction.pace == 1.0


def test_video_plan_parses_full_payload():
    payload = {
        "title": "Five Discoveries",
        "hook": "You won't believe it",
        "script": "Full narration text",
        "voice_direction": {"personality": "confident", "pace": 0.96},
        "scenes": [{"sequence": 1, "narration": "n", "visual_prompt": "v", "duration_seconds": 5}],
        "hashtags": ["#shorts"],
    }
    plan = VideoPlan.model_validate(payload)
    assert plan.scenes[0].sequence == 1
    assert plan.voice_direction.pace == 0.96
