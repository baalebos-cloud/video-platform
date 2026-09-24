"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-09-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255)),
        sa.Column("status", sa.Enum("active", "suspended", "deleted", name="user_status"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column(
            "type",
            sa.Enum("image", "video", "audio", "caption", "thumbnail", "final_video", name="asset_type"),
            nullable=False,
        ),
        sa.Column("storage_key", sa.String(1024), nullable=False),
        sa.Column("mime_type", sa.String(128), nullable=False, server_default="application/octet-stream"),
        sa.Column("checksum", sa.String(128)),
        sa.Column("size_bytes", sa.BigInteger()),
        sa.Column("provider_metadata", postgresql.JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_assets_owner_id", "assets", ["owner_id"])

    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("niche", sa.String(255)),
        sa.Column("brand_context", postgresql.JSONB, server_default="{}"),
        sa.Column("description", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_projects_user_id", "projects", ["user_id"])

    op.create_table(
        "videos",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE")),
        sa.Column(
            "status",
            sa.Enum(
                "draft", "queued", "planning", "scripting", "storyboarding",
                "generating_assets", "rendering", "ready", "failed", "cancelled",
                name="video_status",
            ),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("topic", sa.String(1024), nullable=False),
        sa.Column("language", sa.String(64), server_default="English"),
        sa.Column("locale", sa.String(16), server_default="en-US"),
        sa.Column("duration_seconds", sa.Integer(), server_default="60"),
        sa.Column("platform", sa.String(64), server_default="youtube_shorts"),
        sa.Column("aspect_ratio", sa.String(16), server_default="9:16"),
        sa.Column("visual_style", sa.String(64), server_default="cinematic_realistic"),
        sa.Column("creativity", sa.String(32), server_default="high"),
        sa.Column("voice_preferences", postgresql.JSONB, server_default="{}"),
        sa.Column("progress", sa.Integer(), server_default="0"),
        sa.Column("current_stage", sa.String(64)),
        sa.Column("output_asset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("assets.id", ondelete="SET NULL")),
        sa.Column("error_message", sa.String(2048)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_videos_project_id", "videos", ["project_id"])
    op.create_index("ix_videos_status", "videos", ["status"])

    op.create_table(
        "scripts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("video_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("videos.id", ondelete="CASCADE")),
        sa.Column("version", sa.Integer(), server_default="1"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("language", sa.String(64), server_default="English"),
        sa.Column("status", sa.Enum("draft", "approved", "superseded", name="script_status"), server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_scripts_video_id", "scripts", ["video_id"])

    op.create_table(
        "scenes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("video_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("videos.id", ondelete="CASCADE")),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("narration", sa.Text(), server_default=""),
        sa.Column("visual_prompt", sa.Text(), server_default=""),
        sa.Column("duration_seconds", sa.Float(), server_default="5.0"),
        sa.Column("camera", sa.String(255)),
        sa.Column("lighting", sa.String(255)),
        sa.Column("on_screen_text", sa.String(512)),
        sa.Column("continuity_reference_ids", postgresql.ARRAY(sa.String()), server_default="{}"),
        sa.Column("negative_constraints", postgresql.ARRAY(sa.String()), server_default="{}"),
        sa.Column("metadata_json", postgresql.JSONB, server_default="{}"),
        sa.Column("visual_asset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("assets.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_scenes_video_id", "scenes", ["video_id"])

    op.create_table(
        "generation_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("video_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("videos.id", ondelete="CASCADE")),
        sa.Column(
            "type",
            sa.Enum(
                "script", "storyboard", "voice", "visual", "caption", "render", "publish", "video_generation",
                name="job_type",
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("queued", "running", "retrying", "succeeded", "failed", "cancelled", name="job_status"),
            server_default="queued",
        ),
        sa.Column("provider", sa.String(64)),
        sa.Column("model", sa.String(128)),
        sa.Column("attempts", sa.Integer(), server_default="0"),
        sa.Column("input_hash", sa.String(128)),
        sa.Column("cost_estimate", sa.Numeric(10, 4)),
        sa.Column("error_code", sa.String(64)),
        sa.Column("error_message", sa.String(2048)),
        sa.Column("output_asset_ids", postgresql.JSONB, server_default="[]"),
        sa.Column("idempotency_key", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_generation_jobs_video_id", "generation_jobs", ["video_id"])
    op.create_index("ix_generation_jobs_status", "generation_jobs", ["status"])
    op.create_index("ix_generation_jobs_idempotency_key", "generation_jobs", ["idempotency_key"])

    op.create_table(
        "voices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("voice_id", sa.String(128), nullable=False),
        sa.Column("locale", sa.String(16), nullable=False),
        sa.Column("gender", sa.String(32)),
        sa.Column("voice_metadata", postgresql.JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_voices_locale", "voices", ["locale"])

    op.create_table(
        "publishing_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("platform", sa.String(64), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("token_ref", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_publishing_accounts_user_id", "publishing_accounts", ["user_id"])

    op.create_table(
        "published_videos",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("video_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("videos.id", ondelete="CASCADE")),
        sa.Column(
            "publishing_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("publishing_accounts.id", ondelete="CASCADE"),
        ),
        sa.Column("platform", sa.String(64), nullable=False),
        sa.Column("external_post_id", sa.String(255)),
        sa.Column(
            "status",
            sa.Enum("draft", "ready", "uploading", "published", "publish_failed", "retrying", name="publish_status"),
            server_default="draft",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_published_videos_video_id", "published_videos", ["video_id"])

    op.create_table(
        "analytics_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "published_video_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("published_videos.id", ondelete="CASCADE"),
        ),
        sa.Column("views", sa.Integer(), server_default="0"),
        sa.Column("likes", sa.Integer(), server_default="0"),
        sa.Column("shares", sa.Integer(), server_default="0"),
        sa.Column("comments", sa.Integer(), server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_analytics_snapshots_published_video_id", "analytics_snapshots", ["published_video_id"])

    op.create_table(
        "credit_ledger",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column(
            "entry_type",
            sa.Enum("purchase", "debit", "refund", "adjustment", name="ledger_entry_type"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.String(8), server_default="USD"),
        sa.Column("reference_type", sa.String(64)),
        sa.Column("reference_id", sa.String(128)),
        sa.Column("entry_metadata", postgresql.JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_credit_ledger_user_id", "credit_ledger", ["user_id"])

    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("resource", sa.String(128), nullable=False),
        sa.Column("resource_id", sa.String(128)),
        sa.Column("audit_metadata", postgresql.JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("credit_ledger")
    op.drop_table("analytics_snapshots")
    op.drop_table("published_videos")
    op.drop_table("publishing_accounts")
    op.drop_table("voices")
    op.drop_table("generation_jobs")
    op.drop_table("scenes")
    op.drop_table("scripts")
    op.drop_table("videos")
    op.drop_table("projects")
    op.drop_table("assets")
    op.drop_table("users")
    for enum_name in [
        "user_status", "asset_type", "video_status", "script_status",
        "job_type", "job_status", "publish_status", "ledger_entry_type",
    ]:
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
