# Phase 3A — optional live AI voice and image providers

This phase keeps the existing provider abstraction, saves PNG and WAV media compatible with
FFmpeg, and enables OpenAI image and speech endpoints as an *explicit opt-in* for real
AI-generated media. Neither the AI video clip API nor a timeline editor is included here.
The output remains a sequence of still images and narration rendered into an MP4.

## Deploy configuration

Set these variables on **both API and worker services**:

```dotenv
VOICE_PROVIDER=openai
IMAGE_PROVIDER=openai
OPENAI_API_KEY=<insert a valid OpenAI API key in your secret manager>
OPENAI_TTS_MODEL=gpt-4o-mini-tts
OPENAI_TTS_DEFAULT_VOICE=alloy
OPENAI_IMAGE_MODEL=gpt-image-1.5
OPENAI_IMAGE_QUALITY=medium
```

- You may enable one provider while leaving the other as `mock`. For the cost-free
  local/CI pipeline, leave both providers as `mock` (the defaults).
- A selected live provider without an API key fails settings validation at startup.
- Actual usage requires billing, provider account access, and an internet-reachable worker.
- API failures / invalid responses are reported as failures, **not** replaced by mock output.
- OpenAI speech response is requested as WAV. Its duration is measured from the returned WAV
  frames rather than guessed from text length. This duration drives video rendering.
- Images are requested as PNG, at 1024×1536 portrait or 1536×1024 landscape, with FFmpeg
  scaling and padding to final video size.
- Voice preview API is authenticated, limited to five requests per minute, and capped at
  240 sample-text characters. Generation and scene regeneration have existing rate limits.
- Newly created assets register provider and model metadata. This does not make old mock
  media 'real': old assets remain unchanged.
- These requests can cost money per scene; credit ledger deductions and hard provider
  spend caps are **not yet implemented**. Limit access and API key budgets before rollout.
- Synthetic narration must be disclosed where appropriate, and language/voice quality
  should be checked by native speakers (particularly for non-English languages).

## Integration references

- [OpenAI speech API](https://developers.openai.com/api/reference/resources/audio/subresources/speech/methods/create)
- [OpenAI image API](https://developers.openai.com/api/reference/resources/images/methods/generate)

## Validation

```sh
cd backend && python -m pytest tests/ -v
cd ../frontend && npm run typecheck && npm run lint && npm run build
```

All tests run via mocked HTTP transport (no OpenAI API charges). GitHub CI also performs
the existing mock-provider FFmpeg generation + re-render smoke test.

## Known limitations and next steps

1. The current slideshow render architecture does not yet generate motion/video clips.
2. Fixed-size image generation cannot exactly match 9:16 / 16:9: the existing renderer pads.
3. Audio input is limited to 4096 characters per scene, mirroring the speech endpoint.
4. Provider request error responses are sanitized; support teams must diagnose failures
   through HTTP status and their provider dashboard, not leaked raw secrets.
5. No cost accounting or subscription checkout, no automatic provider retries, no user
   self-service per-project provider choice, and no live-account integration test.
