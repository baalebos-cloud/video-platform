# Runbook: Database outage / recovery

**Symptom:** API returns 500s on every DB-backed endpoint;
`sqlalchemy.exc.OperationalError` / connection refused in logs.

## Diagnose

1. Confirm Postgres is actually down vs. a connection-pool exhaustion:
   `docker compose ps postgres` / check your managed Postgres console.
2. Check active connection count against `max_connections` if the
   instance is up but rejecting new connections.

## Fix

- **Postgres down:** restart it (`docker compose restart postgres` locally;
  follow your managed provider's failover process in production). The API
  will start succeeding again on its next request — no manual API restart
  needed, since `app/db/session.py` creates a fresh connection per
  request via the pool.
- **Connection pool exhausted:** the API fails fast rather than queuing
  indefinitely. Increase Postgres's `max_connections`, or add
  PgBouncer in front of it, before scaling the API's replica count
  further.
- **Data corruption / need to restore from backup:** restore the most
  recent backup, then replay `alembic upgrade head` if the backup
  predates a migration. Because `credit_ledger`, `generation_jobs`, and
  `assets.storage_key` are the source of truth for money and files
  respectively, prioritize verifying those tables after any restore.

## Prevent recurrence

Set up automated backups and **test restoration periodically** — an
untested backup is not a recovery plan. Not yet automated in this
codebase; add it to your infrastructure-as-code before production.
