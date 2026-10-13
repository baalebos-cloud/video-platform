"""Enforce globally unique, user-namespaced retry key hashes.

Revision ID: 0002_idempotency_uniqueness
Revises: 0001_initial_schema
"""
from alembic import op

revision = "0002_idempotency_uniqueness"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Older parallel requests may have inserted duplicate keys. Keep the
    # first record, and clear retry keys on duplicates before adding uniqueness.
    op.execute("""
        WITH ranked AS (
            SELECT id,
                   row_number() OVER (
                       PARTITION BY idempotency_key ORDER BY created_at, id
                   ) AS position
            FROM generation_jobs
            WHERE idempotency_key IS NOT NULL
        )
        UPDATE generation_jobs AS job
        SET idempotency_key = NULL
        FROM ranked
        WHERE job.id = ranked.id AND ranked.position > 1
    """)
    op.drop_index("ix_generation_jobs_idempotency_key", table_name="generation_jobs")
    op.create_index(
        "ix_generation_jobs_idempotency_key",
        "generation_jobs",
        ["idempotency_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_generation_jobs_idempotency_key", table_name="generation_jobs")
    op.create_index("ix_generation_jobs_idempotency_key", "generation_jobs", ["idempotency_key"])
