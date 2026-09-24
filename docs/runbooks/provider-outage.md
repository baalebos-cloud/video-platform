# Runbook: AI provider outage

**Symptom:** A spike in jobs failing at the `scripting` (LLM),
`generating_assets` (voice/image), stage with provider-specific error
messages (timeouts, 5xx from the provider).

## Diagnose

1. Check the provider's public status page.
2. Check `job_type` breakdown of recent failures — if only one provider
   type (e.g. voice) is failing, the LLM and image paths are likely fine.
3. Confirm it's not a local misconfiguration: verify the relevant
   `*_API_KEY` env var is set and the provider adapter is registered in
   `app/ai/providers/registry.py`.

## Fix

- **Short outage:** no action needed if the outage resolves within your
  retry window — extend `GenerationJob.attempts`-based retry logic in
  `pipeline_task.py` if this becomes frequent (not yet implemented:
  currently a failure marks the job `FAILED` immediately rather than
  retrying automatically).
- **Extended outage:** temporarily switch `LLM_PROVIDER` / `VOICE_PROVIDER`
  / etc. to `mock` in `.env` and redeploy, so new generations don't pile
  up as failures while a fix is in progress (this degrades quality but
  keeps the product usable) — or switch to a secondary registered
  provider if one is configured.

## Prevent recurrence

This is exactly what `select_provider()`'s capability-based selection
(blueprint section 18.1) is designed to eventually automate: score
providers by live latency/error-rate and fail over automatically. Only
single-provider-per-task selection is implemented today.
