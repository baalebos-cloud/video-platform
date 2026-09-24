from app.services.caption_service import generate_captions, to_srt


def test_generate_captions_splits_into_cues():
    cues = generate_captions("one two three four five six seven eight", duration_seconds=8.0, max_words_per_cue=4)
    assert len(cues) == 2
    assert cues[0].start_seconds == 0.0
    assert cues[-1].end_seconds == 8.0


def test_to_srt_produces_valid_format():
    cues = generate_captions("hello world", duration_seconds=2.0)
    srt = to_srt(cues)
    assert "-->" in srt
