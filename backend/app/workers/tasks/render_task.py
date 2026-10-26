"""
Composes all scene assets into the final MP4: per-scene clips, captions,
concatenation, and thumbnail extraction (blueprint section 19.2).
"""
import asyncio
import shutil
import tempfile
from pathlib import Path

from app.db.models.scene import Scene
from app.db.models.video import Video
from app.services import render_service, storage_service
from app.services.caption_service import CaptionCue, generate_captions, to_srt


async def run(video: Video, scenes: list[Scene], scene_assets: dict[str, dict]) -> dict:
    # Everything below is blocking (boto3 + FFmpeg subprocesses), so run it
    # in a worker thread to keep the event loop — and, when the worker is
    # embedded in the API process, the API itself — responsive.
    return await asyncio.to_thread(_render_sync, video, scenes, scene_assets)


def _render_sync(video: Video, scenes: list[Scene], scene_assets: dict[str, dict]) -> dict:
    """
    scene_assets: {scene_id: {"image_key": str, "audio_key": str, "duration": float}}
    Returns dict with storage keys for the final video and thumbnail, plus total duration.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        clip_paths: list[Path] = []
        caption_cues: list[CaptionCue] = []
        total_duration = 0.0

        for scene in sorted(scenes, key=lambda s: s.sequence):
            assets = scene_assets[str(scene.id)]
            image_bytes = storage_service.get_object_bytes(assets["image_key"])
            audio_bytes = storage_service.get_object_bytes(assets["audio_key"])
            duration = assets["duration"]

            image_path = tmp_path / f"scene_{scene.sequence}.png"
            audio_path = tmp_path / f"scene_{scene.sequence}.wav"
            clip_path = tmp_path / f"clip_{scene.sequence}.mp4"
            image_path.write_bytes(image_bytes)
            audio_path.write_bytes(audio_bytes)

            render_service.render_scene_clip(
                image_path, audio_path, duration, clip_path,
                aspect_ratio=video.aspect_ratio,
                cinematic_motion=video.visual_style == "cinematic_realistic",
            )
            clip_paths.append(clip_path)
            # The caption edit is scoped to its own scene; timings remain an
            # approximation of narration duration until ASR alignment ships.
            caption_text = scene.caption_text if scene.caption_text is not None else scene.narration
            if video.caption_style != "none":
                for cue in generate_captions(caption_text, duration):
                    caption_cues.append(CaptionCue(
                        start_seconds=round(total_duration + cue.start_seconds, 2),
                        end_seconds=round(total_duration + cue.end_seconds, 2),
                        text=cue.text,
                    ))
            total_duration += duration

        concatenated_path = tmp_path / "concatenated.mp4"
        render_service.concatenate_clips(clip_paths, concatenated_path)

        final_path = tmp_path / "final.mp4"
        if caption_cues:
            srt_path = tmp_path / "captions.srt"
            srt_path.write_text(to_srt(caption_cues), encoding="utf-8")
            render_service.burn_in_captions(
                concatenated_path, srt_path, final_path,
                style=video.caption_style or "classic",
            )
        else:
            shutil.copyfile(concatenated_path, final_path)

        thumbnail_path = tmp_path / "thumbnail.png"
        render_service.generate_thumbnail(final_path, thumbnail_path)

        final_key, _c1, _s1 = storage_service.put_object(
            final_path.read_bytes(), content_type="video/mp4", prefix=f"videos/{video.id}/final"
        )
        thumb_key, _c2, _s2 = storage_service.put_object(
            thumbnail_path.read_bytes(), content_type="image/png", prefix=f"videos/{video.id}/thumbnail"
        )

        return {"final_video_key": final_key, "thumbnail_key": thumb_key, "duration_seconds": total_duration}
