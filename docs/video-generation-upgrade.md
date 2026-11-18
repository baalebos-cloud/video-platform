# Real generative video + the "like this example" question

## What was added (this change)

1. **`REPLICATE_VIDEO_PROVIDER`** (`app/ai/providers/video/replicate.py`) — a
   real `VideoProvider` adapter. One Replicate API token gives access to
   most of the hosted generative-video models (Kling, Luma Ray, Veo,
   Runway, Seedance, Hunyuan, etc.) without a separate account/billing
   relationship per vendor. The scene's already-generated still image is
   passed as an image-conditioning frame when the chosen model supports
   it, so motion stays anchored to what the director planned instead of
   drifting to something unrelated.
2. **`visual_task.py`** now calls the configured `VideoProvider` for every
   scene once `VIDEO_PROVIDER` is set to anything other than `mock`,
   falling back to the existing Ken Burns still-image path if the call
   fails (quota, outage, bad model config) — a creator's video still
   finishes, just with a less dynamic scene, rather than failing outright.
3. **Director prompt v5** (`app/ai/prompts/video_director_v5.py`) — the
   `visual_prompt` the LLM writes per scene is now written as a real shot
   description (framing, consistent subject description, motion, setting)
   instead of a one-line caption, because it is now sent straight to a
   real video-generation model rather than only an image model. The
   `camera` / `lighting` fields (already in the schema, previously mostly
   unused) are now explicitly filled every scene.

Turning it on is one `.env` change: `VIDEO_PROVIDER=replicate`,
`REPLICATE_API_TOKEN=...`, and a `REPLICATE_VIDEO_MODEL` you've picked and
checked the input schema for on replicate.com. Nothing else in the
pipeline, render path, or rerender path needed to change — `render_task.py`
already had a real-video-clip path (it was built for licensed stock
footage) and now carries AI-generated clips through the same path.

## What this does *not* yet close: matching the attached reference clip exactly

The attached example (a toddler and a talk-show host in conversation,
66 seconds, vertical) is a *lip-synced, identity-consistent AI avatar*
production: the same two faces recur across many cuts, their mouths
track synthesized speech, and the shots are directed like a real
multi-camera interview. That is a different, harder capability than
"generate a video clip from a prompt," and no amount of prompt-writing
closes that gap by itself — it needs a different kind of model in the
pipeline. Concretely, three things would need to be added on top of
what shipped in this change:

1. **A fixed character reference carried across every scene.** Today each
   scene's image (and therefore its video clip) is generated
   independently; v5's prompt asks the LLM to *describe* a recurring
   character identically in every scene, which is a reasonable
   approximation for style consistency but will not produce the literal
   same face Replicate's image models the way a face-locked pipeline
   (a fixed reference image fed to every generation, or a provider with
   native identity-lock) would.
2. **Lip-synced dialogue**, not narration-over-video. The render pipeline
   dubs TTS narration over whatever visual plays; it does not make an
   on-screen mouth match generated speech. That needs either (a) an
   avatar/talking-head provider built for this specifically — HeyGen,
   Synthesia, Hedra, Kling's avatar mode, D-ID — or (b) a separate
   lip-sync pass (e.g. Sync Labs) applied after a generated clip.
3. **Multi-shot direction of one continuous scene** (cutting between a
   consistent two-shot, a close-up on each speaker, reaction shots) rather
   than one independent clip per storyboard scene.

None of this is a rewrite of what exists — the provider-adapter pattern
this codebase already uses (`VideoProvider`, `select_provider`) is exactly
the right shape to add an `AvatarVideoProvider` for an interview/avatar
format alongside the general-purpose `VideoProvider` added here. It is
real additional scope, though: an avatar provider is its own account,
its own cost per minute (materially higher than per-clip generation),
and its own adapter and director-prompt branch for "interview format."
Flagging it here rather than quietly shipping something that looks
similar but isn't.

## Recommended order if the interview/avatar format is wanted next

1. Ship this change (general motion, works for any topic) and confirm it
   renders real motion end-to-end with a real Replicate token.
2. Pick one avatar provider (HeyGen and Synthesia both have per-minute
   APIs with consistent-character "avatars" and built-in lip sync; Kling's
   own avatar mode is an option if staying on one vendor matters more than
   features).
3. Add `AvatarVideoProvider` + a director prompt variant that outputs
   dialogue lines with speaker turns instead of narration-per-scene, since
   an interview format's script shape is different from a documentary
   voiceover's.
