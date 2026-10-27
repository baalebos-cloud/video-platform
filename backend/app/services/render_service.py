"""
Render engine — combines scene images, narration audio, captions and
transitions into a final MP4 using FFmpeg (blueprint section 19).

The worker treats every input as a timeline asset: each scene contributes
one still image + one narration audio clip; FFmpeg composes them into a
per-scene clip with optional restrained Ken Burns motion and concatenates
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


def scene_fade_filters(
    video_filters: str, duration_seconds: float, *, fade_in: bool, fade_out: bool,
) -> tuple[str, str]:
    """Hard-cut or true fade through black; no free-form FFmpeg input from users."""
    audio_filters = "apad"
    fade_seconds = min(0.25, duration_seconds / 2)
    if fade_in:
        video_filters += f",fade=t=in:st=0:d={fade_seconds:.3f}"
        audio_filters += f",afade=t=in:st=0:d={fade_seconds:.3f}"
    if fade_out:
        fade_start = max(0.0, duration_seconds - fade_seconds)
        video_filters += f",fade=t=out:st={fade_start:.3f}:d={fade_seconds:.3f}"
        audio_filters += f",afade=t=out:st={fade_start:.3f}:d={fade_seconds:.3f}"
    return video_filters, audio_filters


def render_scene_clip(
    image_path: Path, audio_path: Path, duration_seconds: float, output_path: Path,
    *, aspect_ratio: str = "9:16", cinematic_motion: bool = False,
    fade_in: bool = False, fade_out: bool = False,
) -> None:
    """Render a full-bleed H.264/AAC scene; optionally add subtle photo motion."""
    if aspect_ratio not in {"9:16", "16:9", "1:1"}:
        raise RenderError("Unsupported aspect ratio")
    if duration_seconds <= 0:
        raise RenderError("Scene duration must be positive")
    width, height = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080)}[aspect_ratio]
    # Fit and center-crop instead of letterboxing with a dark underlay.
    filters = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}"
    if cinematic_motion:
        filters += (
            f",zoompan=z='min(zoom+0.0005,1.06)'"
            f":x='iw/2-(iw/zoom/2)'"
            f":y='ih/2-(ih/zoom/2)'"
            f":d=1:s={width}x{height}:fps=24"
        )
    filters += ",setsar=1,format=yuv420p"
    filters, audio_filters = scene_fade_filters(
        filters, duration_seconds, fade_in=fade_in, fade_out=fade_out,
    )
    _run([
        "ffmpeg", "-y", "-framerate", "24", "-loop", "1", "-i", str(image_path),
        "-i", str(audio_path),
        "-vf", filters, "-r", "24", "-t", str(duration_seconds),
        "-af", audio_filters,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-profile:v", "high", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart",
        str(output_path),
    ])


def concatenate_clips(clip_paths: list[Path], output_path: Path) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        for clip in clip_paths:
            f.write(f"file '{clip}'\n")
        concat_list = f.name
    try:
        _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list, "-c", "copy",
              "-movflags", "+faststart", str(output_path)])
    finally:
        Path(concat_list).unlink(missing_ok=True)


# Explicit, server-owned caption presets; never interpolate free-form FFmpeg filters.
CAPTION_STYLES = {
    "classic": "Fontsize=24,Alignment=2,MarginV=80,Outline=2,PrimaryColour=&H00FFFFFF",
    "bold": "Fontsize=34,Bold=1,Alignment=2,MarginV=96,Outline=3,PrimaryColour=&H00FFFFFF",
    "social": "Fontsize=32,Bold=1,Alignment=2,MarginV=110,Outline=3,PrimaryColour=&H0000FFFF",
    "minimal": "Fontsize=21,Alignment=2,MarginV=70,Outline=1,PrimaryColour=&H00FFFFFF",
}


def burn_in_captions(
    video_path: Path, srt_path: Path, output_path: Path, *, style: str = "classic"
) -> None:
    if style not in CAPTION_STYLES:
        raise RenderError("Unsupported caption style")
    _run(
        [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vf", f"subtitles={srt_path}:force_style='{CAPTION_STYLES[style]}'",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart",
            str(output_path),
        ]
    )


def generate_thumbnail(video_path: Path, output_path: Path, at_seconds: float = 0.5) -> None:
    _run(["ffmpeg", "-y", "-ss", str(at_seconds), "-i", str(video_path), "-frames:v", "1", str(output_path)])


def render_stock_clip(
    footage_path: Path, audio_path: Path, duration_seconds: float,
    output_path: Path, *, aspect_ratio: str = "9:16",
    fade_in: bool = False, fade_out: bool = False,
) -> None:
    """Render real licensed footage (repeated if short), cropped for the destination platform."""
    if aspect_ratio not in {"9:16", "16:9", "1:1"}:
        raise RenderError("Unsupported aspect ratio")
    if duration_seconds <= 0:
        raise RenderError("Scene duration must be positive")
    width, height = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080)}[aspect_ratio]
    filters = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},fps=24,setsar=1,format=yuv420p"
    )
    filters, audio_filters = scene_fade_filters(
        filters, duration_seconds, fade_in=fade_in, fade_out=fade_out,
    )
    _run([
        "ffmpeg", "-y", "-stream_loop", "-1", "-i", str(footage_path),
        "-i", str(audio_path), "-map", "0:v:0", "-map", "1:a:0",
        "-vf", filters, "-af", audio_filters, "-t", str(duration_seconds),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
        "-profile:v", "high", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart", str(output_path),
    ])
