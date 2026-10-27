"""Self-recorded scene narration, no voice cloning or external TTS inference.

Audio remains in private user-owned object storage. Incoming bytes are
fully decoded and resampled before use by FFmpeg; client MIME is not trusted.
"""
import io
import math
import subprocess
import wave

MAX_UPLOAD_BYTES = 3 * 1024 * 1024
MAX_SCENE_SECONDS = 60.0
SUPPORTED_CONTENT_TYPES = {
    "audio/wav", "audio/x-wav", "audio/wave", "audio/mpeg", "audio/mp3",
    "audio/webm", "audio/mp4", "audio/x-m4a", "audio/ogg",
}


class PersonalVoiceError(ValueError):
    pass


def empty_narration(seconds: float = 0.5) -> bytes:
    """Generate a short silent WAV placeholder for the manual narration path."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(b"\x00\x00" * round(24000 * seconds))
    return buffer.getvalue()


def normalize_recording(\n    data: bytes, mime_type: str, max_seconds: float,\n    *, trim_start: float = 0.0, trim_end: float | None = None,\n) -> tuple[bytes, float]:
    """Decode a browser or uploaded recording to safe mono 24k PCM WAV.

    Reject overlong voice clips rather than quietly chopping off the speaker.
    """
    if mime_type.split(";", 1)[0].strip().lower() not in SUPPORTED_CONTENT_TYPES:
        raise PersonalVoiceError("Use a WAV, MP3, WebM, OGG or M4A audio recording")
    if not data or len(data) > MAX_UPLOAD_BYTES:
        raise PersonalVoiceError("Recording must be non-empty and at most 3 MB")
    if not 0.5 <= max_seconds <= MAX_SCENE_SECONDS:
        raise PersonalVoiceError("Invalid scene duration")
    if not math.isfinite(trim_start) or trim_start < 0 or trim_start > MAX_SCENE_SECONDS:
        raise PersonalVoiceError("Invalid audio trim start")
    if trim_end is not None and (
        not math.isfinite(trim_end) or trim_end <= trim_start + 0.4
        or trim_end > MAX_SCENE_SECONDS + 2
    ):
        raise PersonalVoiceError("Invalid audio trim end")
    requested_length = (
        trim_end - trim_start if trim_end is not None else MAX_SCENE_SECONDS + 2
    )
    if trim_end is not None and requested_length > max_seconds + 0.25:
        raise PersonalVoiceError("Trimmed audio must fit within the scene duration")
    try:
        proc = subprocess.run(
            ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
             "-i", "pipe:0", "-ss", str(trim_start), "-vn",
             "-t", str(requested_length),
             "-f", "s16le", "-acodec", "pcm_s16le", "-ac", "1",
             "-ar", "24000", "pipe:1"],
            input=data, capture_output=True, timeout=35, check=True,
        )
    except (subprocess.SubprocessError, OSError):
        raise PersonalVoiceError("Audio could not be decoded") from None
    pcm = proc.stdout
    duration = len(pcm) / (24000 * 2)
    if not 0.4 <= duration <= max_seconds + 0.25:
        raise PersonalVoiceError(
            "Recording must fit within this scene's duration; shorten the audio or adjust the clip"
        )
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(pcm)
    return output.getvalue(), duration
