# Phase 11 — Caption workflow and portable subtitles

- Studio caption editor gains a multi-scene bulk edit mode, with atomic
  owner-checked server updates and duplicate/foreign scene prevention.
- Export deterministic SRT (.srt) subtitles with scene timestamps derived
  from measured scene duration; SRT is separate from MP4 and can be edited
  in external subtitle tools.
- Caption modifications mark `needs_rerender` until video is rendered again.
- Subtitles use existing four style presets and do not affect narration.
- No schema migration; requires Phase 9 browser proxy and Phase 10 PR merge.
- Timings are scene-aligned, not phoneme or word alignment. Import from SRT
  and timeline trim/drag editing are not yet implemented.
