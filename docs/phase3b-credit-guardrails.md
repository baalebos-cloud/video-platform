# Phase 3B — internal credits and provider-volume circuit breaker

This PR adds **opt-in** generation credit reservation, failure refunds,
and a global Redis-backed daily live-media call limit. This is **not**
a payment integration, actual per-model USD pricing system, or provider
spend guarantee. The OpenAI organization should still have an actual
billing budget and alert configured separately.

## Configuration

```dotenv
CREDIT_ENFORCEMENT_ENABLED=true
SIGNUP_STARTER_CREDITS=100
CREDITS_PER_30_SECONDS=10
SCENE_REGENERATION_CREDITS=2
VOICE_PREVIEW_CREDITS=1
MAX_DAILY_LIVE_MEDIA_CALLS=100
```

- Internal ledger entries use **CRD**. Existing USD entries are excluded
  from CRD balances and history. No USD amount maps automatically to CRD.
- A generation charges `ceil(duration/30s) * CREDITS_PER_30_SECONDS`,
  before queue dispatch. The debit is written in the same DB transaction
  as the GenerationJob/Video.
- Failed generation and failed queue dispatch are credited back once,
  using operation-specific references. Refunds are internal-credit
  policy: real third-party provider charges may not be reversed.
- Preview and scene regeneration charge a small number of CRD only if
  their configured provider is live and accounting is enabled. API
  failures result in a refund; successful provider responses count.
- Non-AI re-renders reuse saved assets and have no AI-credit debit.
- Users signing up **after activation** receive a one-time configurable
  starter grant. Existing users receive no retroactive or recurring
  grants. There is no user-writable adjustment/top-up endpoint.
- Without a grant/purchase provider existing accounts will have no CRD;
  the owner must implement a securely authorized adjustment workflow
  before opening to existing customers.
- Redis atomic daily counter shared by API and workers limits the number
  of *attempted* paid media calls, including failed provider calls.
  If Redis is unavailable, live requests fail closed. It does not count
  provider token totals or enforce a fixed USD budget.
- In production, selecting a live OpenAI media provider requires
  CREDIT_ENFORCEMENT_ENABLED=true, independent of the default mock
  configuration. Do not enable real providers without a separate
  provider-account spend ceiling.
- `DEFAULT_PLAN_MONTHLY_CREDITS` is reserved but **not** an automatic
  monthly grant. No renewal cron/scheduler is installed.

## Database
Apply migration `0005_credit_ledger_uniqueness`. It adds a partial
unique reference index for CRD debits/refunds/adjustments to guard
against duplicate events without affecting the historical USD ledger.

## Remaining gaps
- Real payment settlement and provider USD amount reconciliation.
- A durable transactional outbox / worker crash recovery and
  persistent per-provider request usage analytics.
- Multi-tenant quotas by plan and large-media storage cost accounting.
- Admin-authorized adjustment/audit controls.
