"""
Mock video-clip provider. Real implementations (Runway, Pika, Luma, etc.)
would call an external generative-video API; this adapter instead signals
the render worker to compose the clip from the scene's still image + audio
using FFmpeg, keeping the pipeline runnable without any paid API key.
"""
from app.ai.providers.base import VideoGenerationResult, VideoProvider


class MockVideoProvider(VideoProvider):
    name = "mock"

    async def generate_clip(self, scene_spec: dict) -> VideoGenerationResult:
        # No bytes produced here — the render worker builds the clip locally
        # from the scene's image + narration audio via FFmpeg (see
        # app/services/render_service.py). This keeps local/CI runs free.
        return VideoGenerationResult(video_bytes=b"", format="mp4", duration_seconds=scene_spec.get("duration_seconds", 5), provider=self.name)
