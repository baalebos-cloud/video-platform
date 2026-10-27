"""Self-recorded scene narration, no voice cloning or external TTS inference.

Audio remains in private user-owned object storage. Incoming bytes are
fully decoded and resampled before use by FFmpeg; client MIME is not trusted.
"""
import io
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


def normalize_recording(data: bytes, mime_type: str, max_seconds: float, *, trim_start: float = 0, trim_end: float | None = None) -> tuple[bytes, float]:
    """Decode a browser or uploaded recording to safe mono 24k PCM WAV.

    Reject overlong voice clips rather than quietly chopping off the speaker.
    """
    if mime_type.split(";", 1)[0].strip().lower() not in SUPPORTED_CONTENT_TYPES:
        raise PersonalVoiceError("Use a WAV, MP3, WebM, OGG or M4A audio recording")
    if not data or len(data) > MAX_UPLOAD_BYTES:
        raise PersonalVoiceError("Recording must be non-empty and at most 3 MB")
    if not 0.5 <= max_seconds <= MAX_SCENE_SECONDS:
        raise PersonalVoiceError("Invalid scene duration")
    if not 0 <= trim_start <= MAX_SCENE_SECONDS:
        raise PersonalVoiceError("Invalid trim start")
    if trim_end is not None and not trim_start + 0.4 <= trim_end <= MAX_SCENE_SECONDS + 2:
        raise PersonalVoiceError("Invalid trim end")
    try:
        proc = subprocess.run(
            ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
             "-i", "pipe:0", "-vn", "-t", str(MAX_SCENE_SECONDS + 2),
             "-f", "s16le", "-acodec", "pcm_s16le", "-ac", "1",
             "-ar", "24000", "pipe:1"],
            input=data, capture_output=True, timeout=35, check=True,
        )
    except (subprocess.SubprocessError, OSError):
        raise PersonalVoiceError("Audio could not be decoded") from None
    pcm = proc.stdout
    # Cut decoded mono PCM at 24 kHz. No unrequested silence or tempo change.
    start_byte = round(trim_start * 24000) * 2
    end_byte = round(trim_end * 24000) * 2 if trim_end is not None else len(pcm)
    if start_byte >= len(pcm) or end_byte > len(pcm) + 2400:
        raise PersonalVoiceError("Trim range exceeds the recorded audio")
    pcm = pcm[start_byte:min(end_byte, len(pcm))]
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
