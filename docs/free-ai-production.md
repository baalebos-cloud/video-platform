# Baalebos free-provider production rollout

This configuration uses only providers you explicitly activated. No OpenAI fallback is configured. API credentials must remain on Railway; never expose them in Vercel's NEXT_PUBLIC variables.

## API and Worker variables (both Railway services)

```env
APP_ENV=production
LLM_PROVIDER=gemini
GEMINI_MODEL=gemini-2.5-flash
GEMINI_API_KEY=<your Google AI Studio key>

IMAGE_PROVIDER=cloudflare
VOICE_PROVIDER=cloudflare
CLOUDFLARE_ACCOUNT_ID=<your Cloudflare account ID>
CLOUDFLARE_API_TOKEN=<your Workers AI API token>
CLOUDFLARE_IMAGE_MODEL=@cf/black-forest-labs/flux-1-schnell
CLOUDFLARE_TTS_MODEL=@cf/myshell-ai/melotts

PIXABAY_API_KEY=<your Pixabay key>
PIXABAY_VIDEO_API_URL=https://pixabay.com/api/videos/
STOCK_FOOTAGE_ENABLED=true

CREDIT_ENFORCEMENT_ENABLED=false
MAX_DAILY_LIVE_MEDIA_CALLS=60
```

Preserve the existing `DATABASE_URL`, `REDIS_URL`, JWT secret, object storage credentials, YouTube encryption key, and public API configuration. Keep paid API billing disabled or on free-tier projects as appropriate. The quota guard limits media calls but does not inspect the billing plan and cannot guarantee zero charges on a paid Cloudflare plan.

## How the generation runs

1. Gemini receives the topic and returns a JSON-validated VideoPlan. Invalid or quota-limited requests stop rather than switching to mock plans.
2. Each scene uses Cloudflare MeloTTS to generate spoken audio. The worker transcodes returned MP3 to a valid PCM WAV with FFmpeg.
3. The worker looks up Pixabay stock footage from the scene description, caching Pixabay search JSON in Redis for 24 hours. If a suitable small licensed clip is found, the media is copied to private object storage with a thumbnail and provenance. Otherwise Cloudflare FLUX supplies a PNG still image.
4. FFmpeg crops/mixes stock footage or moving stills to the selected platform aspect ratio, with voice and optional burned-in subtitles, then exports H.264/AAC MP4.
5. The editor offers Download MP4 using an expiring authenticated link.

## Operational constraints

- Availability, search relevance, duration and quality vary by free provider and scene. No guarantee every video will use stock footage.
- Pixabay access is for human-triggered videos; do not bulk-scrape, auto-download catalogs or permanently hotlink stock footage.
- Only Pixabay `cdn.pixabay.com` HTTPS MP4s are accepted, with an 18MB upper limit per scene.
- Pixabay search results are cached for 24 hours; media is stored in existing private object storage. Individual footage source URLs are preserved in scene metadata.
- Cloudflare free quota and Gemini free quota reset on provider-defined schedules. Free services can throttle or reject usage.
- Re-rendering reuses saved footage and audio; regeneration of a scene image invalidates its stock reference.
- These adapters require the Railway worker image with FFmpeg. Never run the worker inside the Vercel frontend.

## Smoke test

Use an existing project and create a 10-15 second video with:

> A cinematic story of a futuristic city at sunrise, people using new technology, and a hopeful future.

Select English voice, cinematic visuals, 9:16 aspect ratio and clean captions. Inspect the generation history and Railway worker logs; then download MP4, confirm H.264/AAC and listen to the narration. Validate a second video with an uncommon topic to exercise Cloudflare image fallback.

If generation fails, first check configured provider names, missing credentials, free-tier usage limits, and Pixabay connectivity. Check the error without pasting credentials in chat or logs.
