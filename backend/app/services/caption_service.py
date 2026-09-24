"""
Caption generation — derives mobile-friendly caption cues from narration
text and measured audio duration. A production implementation would call
a forced-alignment / ASR provider for word-level timing; this
implementation performs a reasonable even-split approximation so the
render pipeline has real timed captions to burn in.
"""
from dataclasses import dataclass


@dataclass
class CaptionCue:
    start_seconds: float
    end_seconds: float
    text: str


def generate_captions(narration: str, duration_seconds: float, max_words_per_cue: int = 6) -> list[CaptionCue]:
    words = narration.split()
    if not words:
        return []
    chunks = [words[i : i + max_words_per_cue] for i in range(0, len(words), max_words_per_cue)]
    per_chunk = duration_seconds / len(chunks)
    cues = []
    for i, chunk in enumerate(chunks):
        cues.append(
            CaptionCue(
                start_seconds=round(i * per_chunk, 2),
                end_seconds=round((i + 1) * per_chunk, 2),
                text=" ".join(chunk),
            )
        )
    return cues


def to_srt(cues: list[CaptionCue]) -> str:
    def _ts(seconds: float) -> str:
        h, rem = divmod(seconds, 3600)
        m, s = divmod(rem, 60)
        ms = int((s - int(s)) * 1000)
        return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{ms:03d}"

    lines = []
    for i, cue in enumerate(cues, start=1):
        lines.append(str(i))
        lines.append(f"{_ts(cue.start_seconds)} --> {_ts(cue.end_seconds)}")
        lines.append(cue.text)
        lines.append("")
    return "\n".join(lines)
