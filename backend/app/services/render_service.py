"""
Render engine — combines scene images, narration audio, captions and
transitions into a final MP4 using FFmpeg (blueprint section 19).

The worker treats every input as a timeline asset: each scene contributes
one still image + one narration audio clip; FFmpeg composes them into a
per-scene clip (ken-burns-free, static-image baseline) and concatenates
all scene clips, then burns in the SRT caption track.

This runs entirely locally (no external render-farm dependency), which
keeps local dev and CI cost-free. Swap in a distributed render worker
pool for production-scale throughput.
"""
import subprocess
import tempfile
from pathlib import Path

from app.config.logging import get_logger

logger = get_logger("services.render")


class RenderError(Exception):
    pass


def _run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error("render.ffmpeg_failed", cmd=" ".join(cmd), stderr=result.stderr[-2000:])
        raise RenderError(result.stderr[-2000:])


def render_scene_clip(image_path: Path, audio_path: Path, duration_seconds: float, output_path: Path) -> None:
    """Composes one scene: a static image held for `duration_seconds`, with narration audio."""
    _run(
        [
            "ffmpeg", "-y",
            "-loop", "1", "-i", str(image_path),
            "-i", str(audio_path),
            "-c:v", "libx264", "-tune", "stillimage",
            "-c:a", "aac", "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            "-t", str(duration_seconds),
            "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
            str(output_path),
        ]
    )


def concatenate_clips(clip_paths: list[Path], output_path: Path) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        for clip in clip_paths:
            f.write(f"file '{clip}'\n")
        concat_list = f.name
    try:
        _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list, "-c", "copy", str(output_path)])
    finally:
        Path(concat_list).unlink(missing_ok=True)


def burn_in_captions(video_path: Path, srt_path: Path, output_path: Path) -> None:
    _run(
        [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vf", f"subtitles={srt_path}:force_style='Fontsize=24,Alignment=2,MarginV=80'",
            "-c:a", "copy",
            str(output_path),
        ]
    )


def generate_thumbnail(video_path: Path, output_path: Path, at_seconds: float = 0.5) -> None:
    _run(["ffmpeg", "-y", "-ss", str(at_seconds), "-i", str(video_path), "-frames:v", "1", str(output_path)])
