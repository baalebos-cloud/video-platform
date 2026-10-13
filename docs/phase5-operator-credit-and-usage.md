# Phase 5 — operator credit management and AI media usage reporting

Adds operator-controlled CRD adjustments without granting privilege based on
unverified emails. Does not implement payment checkout, bank transfers,
webhooks, or provider dollar charges.

## Provision operators
1. Sign in to a trusted account and obtain its `id` from `GET /api/v1/users/me`.
2. Set `ADMIN_USER_IDS_RAW` on the **backend** to a comma-separated list of
   those UUIDs. Only operators who manage deployment configuration can add
   administrators. Restart the API after changing this setting.
3. Operators see the **Administration** navigation item in the creator
   dashboard. Backend routes independently enforce the UUID allowlist.
4. Keep deployment environment access restricted. Never use emails, web
   forms or public signup for admin provisioning.

## Credit management
- `GET /api/v1/admin/users/lookup?email=...`: exact-email account lookup.
- `POST /api/v1/admin/credits/adjust`: body includes target `user_id`,
  signed integer `amount` (between -1000 and 1000, excluding 0), unique
  `request_id` UUID, and meaningful `reason`.
- Positive adjustments grant CRD, negative ones debit a balance but never
  leave a negative balance. Self-adjustments are prohibited.
- The target's user record is locked before balance checks and updates, so
  concurrent requests across workers are serialized.
- An operation reference and a unique index from migration 0005 make
  identical retries idempotent; a mismatched retry returns HTTP 409.
- Both ledger and audit log entries are saved in the same transaction.
  Existing `audit_logs` and `credit_ledger` tables are reused.
- Existing accounts can now receive controlled grants without a public
  top-up endpoint or new database migration.

## AI usage reporting
- `GET /api/v1/admin/usage?days=30` is admin-only.
- Aggregates **saved AUDIO / IMAGE assets** by provider, model and type.
  This is recorded successful output volume, **not** per-call requests
  (especially if a provider succeeds and storage upload fails).
- **No actual model token counts, attempted/failed provider requests or
  billable USD amounts** are reported. The existing Redis limiter is a
  request-count circuit breaker, not an organization-level money budget.
- Provider invoices and spend alerts must still be managed separately.

## Operational checks
- Install no new frontend libraries or mandatory external services.
- Run backend pytest suite, Next.js lint/typecheck/build and all existing
  smoke tests. CI covers both Docker builds and the admin permission tests.
- Check operator account access and a separate ordinary creator account in
  staging; verify non-admin HTTP 403 on every /admin endpoint.
- Production authorization by UUID has no MFA yet. Limit operator accounts
  and deploy stronger authentication before large financial operations.
