# Baalebos voice studio: deployment, privacy, testing

## What works without another paid provider

- Choose English, Nigerian Pidgin or Yoruba during video creation.
- In **My own recorded voice** mode, the generated storyboard begins with silent
  placeholders. The creator selects each clip, records narration, reviews and
  trims start/end, and saves a private WAV. Re-rendering replaces placeholders
  with saved narration. Export is rejected server-side until every narration
  is complete and the updated MP4 has finished rendering.
- The recording studio shows a scene timer, microphone-level meter, retakes
  and exact 0.1-second in/out trim fields.
- References in **My AI Voice** are private, owner-linked, consent-required
  WAV assets. Creators can revoke and delete them.

## Automatic cloned narration: opt-in only

The platform **does not ship or activate a free voice-cloning model**. An
operator must separately establish a license and inference endpoint capable
of commercial synthesis of Yoruba, Nigerian Pidgin, and Nigerian English.
The current WazobiaVoice model weights are non-commercial without a commercial
license; its high memory requirements also make Railway's small CPU worker
unsuitable for running it directly. Google's Chirp Instant Custom Voice is
allowlisted and does not advertise all three requested languages.

For a **separately approved licensed service**, set these environment
variables on **both** Railway API and worker, never on the public frontend:

    VOICE_CLONE_API_URL=https://your-authorized-tts.example/v1/synthesize
    VOICE_CLONE_API_TOKEN=<server-side secret>
    VOICE_CLONE_LICENSE_CONFIRMED=true

The service must accept exactly:

    POST application/json
    Authorization: Bearer <token>
    {"text":"...","language":"yo|pcm|en","reference_wav_base64":"..."}

and return audio/wav (HTTP 200). The reference is private and never
delivered to a public browser as a model key. API request preflight checks
the license flag and owner. Worker checks the same profile ownership/consent
and consumes the global media-call quota before inference. No automatic
cloning UI option appears until API configuration is complete.

Do not set the commercial license flag without **actual written permission**
for your exact model/provider deployment, and verify the endpoint's per-call
cost and deletion/retention policy before enabling.

## Production verification

1. Merge after backend/frontend/FFmpeg/Docker CI passes. Deploy a matching
   commit to Railway API, Railway worker and Vercel production.
2. Confirm the browser creation form displays the three-language dropdown,
   the actual recording studio, and the private reference library.
3. Create a short recorded-voice Pidgin or Yoruba test project.
4. Verify an attempt to export before recording every scene is rejected.
5. Record one scene (or upload a file), trim it and save. Check duration,
   retry after microphone denial, and verify unauthorized access is rejected.
6. Complete all scenes, re-render, download MP4 and inspect it using ffprobe.
   Listen to each scene boundary for correct narration, clipping and fades.
7. Enroll a 5–20-second reference with explicit consent, list it, revoke it,
   then confirm the original private storage object is deleted and an old
   profile ID cannot be used to generate new scenes.
8. Run automated clone synthesis tests only using a provider you have
   explicitly licensed and enabled, with a **small request quota**.

## Known limitations and operational follow-up

- Microphone recording is supported over HTTPS in browsers implementing
  MediaRecorder; browser-specific recording formats vary. A user may instead
  upload a supported audio file.
- Current in/out trimming is non-destructive to the local source take, but
  the saved WAV includes only the selected sample range. Retakes replace a
  scene's saved audio asset pointer.
- Live browser-to-MP4 verification requires a signed-in creator account
  and cannot be inferred from CI or a READY deployment alone.
- Automatic cloned inference requires independently purchased/provisioned
  GPU capacity or a commercial API contract. No new paid service is launched
  by this PR.
- A deleted profile is revoked in PostgreSQL before storage deletion. Failed
  S3 deletion may require an operational retry; object-store backups may
  have separate retention schedules.
- Future hardening: explicit recorded consent statements, provider retention
  verification, speech-level/phoneme timing QA, and per-scene voice previews.
