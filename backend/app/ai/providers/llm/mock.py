"""
Deterministic mock LLM provider.

Used automatically when LLM_PROVIDER=mock (the default), so the full
pipeline runs end-to-end in local/dev/CI without any provider API key.
Swap in app/ai/providers/llm/openai_provider.py or similar for production.
"""
import json

from app.ai.providers.base import LLMProvider, LLMResponse


class MockLLMProvider(LLMProvider):
    name = "mock"

    async def complete(self, system_prompt: str, user_prompt: str, *, json_mode: bool = False) -> LLMResponse:
        if json_mode:
            payload = {
                "title": "Five Unbelievable Discoveries",
                "hook": "You won't believe what scientists just found.",
                "script": (
                    "Here are five discoveries that changed everything we thought we knew. "
                    "Number one will surprise you."
                ),
                "voice_direction": {"personality": "confident", "emotion": "curious", "pace": 1.0},
                "scenes": [
                    {
                        "sequence": 1,
                        "narration": "Discovery number one begins here.",
                        "visual_prompt": "cinematic wide shot, dramatic lighting, mysterious atmosphere",
                        "duration_seconds": 5,
                    },
                    {
                        "sequence": 2,
                        "narration": "Discovery number two takes it further.",
                        "visual_prompt": "close-up shot, natural light, high detail",
                        "duration_seconds": 5,
                    },
                ],
                "captions": {"style": "bold_mobile", "position": "center"},
                "music": {"mood": "cinematic", "tempo": "medium"},
                "sfx": [],
                "thumbnail_prompt": "high-contrast cinematic thumbnail with bold text overlay",
                "description": "An exploration of five remarkable discoveries.",
                "hashtags": ["#shorts", "#discovery", "#facts"],
                "cta": "Follow for more discoveries like this.",
                "monetization_angles": ["ad_revenue", "affiliate"],
                "quality_checks": ["no_unverified_claims", "no_fabricated_statistics"],
            }
            return LLMResponse(text=json.dumps(payload), raw=payload, model="mock-director-v1", provider=self.name)

        return LLMResponse(
            text=f"[mock completion for prompt: {user_prompt[:80]}...]",
            model="mock-llm-v1",
            provider=self.name,
        )
