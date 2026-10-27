# Baalebos Personal Voice Studio: production operating contract

## Scope
The creator can select **English**, **Nigerian Pidgin**, and **Yoruba**. Recording
mode uses the creator's microphone or their own audio file for each scene.
It never creates an artificial clone and requires no extra TTS API.

The studio supports recording timers, browser playback, retakes, start/end
trimming with FFmpeg, private audio uploads, a scene completion checklist,
and an owner-only re-render guard that refuses unfinished silent scenes.

## Voice profiles
The creator can separately enroll at most three reusable voice references,
each **5–30 seconds** of their own recorded voice. A voice profile is a
private object-store WAV file plus owner-scoped database metadata, **not**
a trained model. It can be permanently deleted through the account's voice
profile controls. Previous generated MP4s and independent scene recordings
are separate assets and are not deleted by deleting the reference.

Enrollment explicitly requires self-voice consent. Do not upload public
figures' voices or another speaker's voice. Voice references must never
be sent to Gemini, Tavily, Bimpe, Cloudflare TTS or any provider without
an explicit licensed integration.

## Automatic cloning gate
Automatic personal-voice synthesis is **OFF by default**. The UI only
exposes it if the API reports actual operator-supplied capabilities.

Enable it **only after** provisioning your own authenticated,
commercially licensed HTTPS inference endpoint with proven quality in
all three supported languages. Railway free CPU is not a suitable host
for a ~2B-parameter neural TTS model.

Required Railway variables, only on API and worker as appropriate:
- `VOICE_CLONE_ENDPOINT=https://<operator-controlled licensed service>/synthesize`
- `VOICE_CLONE_TOKEN=<private bearer token>`
- `VOICE_CLONE_LICENSE_APPROVED=true`

The feature gate requires all three. The endpoint is **not** chosen by
users. Check that the provider has commercial rights to all weights,
datasets and voice data before enabling it. Do not configure WazobiaVoice
research-only checkpoints on a commercial SaaS without a separate
commercial license. OpenVoice V2 has a permissive license but does not
natively list Yoruba or Nigerian Pidgin; switching to it is not proof
of speech quality.

### Endpoint contract
Authenticated `POST` JSON:
```json
{
  "text": "Spoken scene narration",
  "locale": "yo-NG",
  "reference_audio_wav_base64": "<base64 PCM WAV>"
}
```

Successful JSON:
```json
{"audio_wav_base64": "<base64 24kHz mono PCM WAV>"}
```

Requests are capped at 2,800 text characters and scene duration.
The provider must not store, log, publish, or train on raw reference
audio and must prevent voice-impersonation misuse. Output is validated,
normalized and owned by the requesting user. Any inference usage must
honor the existing global daily media-call circuit breaker.

In production, verify backend `/api/v1/voice-profiles/capabilities`
reports `automatic_cloning=false` until a licensed inference deployment
is ready. Never advertise it as live merely because a voice profile exists.

## Acceptance checks (no paid calls for recorded mode)
1. Deploy identical commit to Railway API, worker and Vercel production.
2. Create a 15-second Yoruba or Pidgin video in recorded mode.
3. Record and upload its first scene through the authenticated frontend
   (WebM/MP4/MP3/WAV/OGG; max 3 MB). Trim, play back, replace and save it.
4. Re-render must reject the video while any other scene is pending.
5. Complete all scenes, re-render and download; use ffprobe and headphones
   to validate the voice is audible and correct in the exported MP4.
6. Enroll a private 5–30-second voice reference, verify list isolation,
   then delete it and confirm the storage object was deleted.
7. Confirm `/voice-profiles/capabilities` returns automatic cloning OFF.
8. Turn on cloning only in a private licensed test environment, validate
   the exact 3-language synthesis contract, quota and deletion controls,
   and independently compare pronunciation and speaker similarity.
9. Check against direct API access by a second account, oversized audio,
   invalid consent, invalid trim data and expired signed URLs.

## Known limitations
- No guaranteed AI voice clone on the free production hosting plan.
- No automatic ASR word-level subtitle alignment.
- Browser-level microphone and audio pipeline must be manually tested;
  CI can validate code, not microphone permissions or live sound quality.
- Existing generated renders are immutable until an authorized re-render.
- External inference services may incur compute/infrastructure fees even
  without buying a third-party API subscription.
