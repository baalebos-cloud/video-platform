"""Recorded successful AI media assets, not actual provider invoice costs.

This intentionally counts persisted media artifacts only. Failed / rate-limited
requests do not produce artifacts, so their true provider spend is unknown.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.asset import Asset, AssetType

_TRACKED = (AssetType.IMAGE, AssetType.AUDIO)
_PROVIDER = Asset.provider_metadata["provider"].astext
_MODEL = Asset.provider_metadata["model"].astext


async def media_usage(db: AsyncSession, *, owner_id=None, days: int = 30) -> dict:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    query = (
        select(
            _PROVIDER.label("provider"),
            _MODEL.label("model"),
            Asset.type,
            func.count(Asset.id).label("outputs"),
        )
        .where(
            Asset.created_at >= since,
            Asset.type.in_(_TRACKED),
            _PROVIDER.is_not(None),
        )
        .group_by(_PROVIDER, _MODEL, Asset.type)
        .order_by(_PROVIDER, _MODEL, Asset.type)
    )
    if owner_id is not None:
        query = query.where(Asset.owner_id == owner_id)
    rows = (await db.execute(query)).all()
    breakdown = [
        {
            "provider": row.provider,
            "model": row.model or "unknown",
            "type": row.type.value if hasattr(row.type, "value") else row.type,
            "outputs": row.outputs,
        }
        for row in rows
    ]
    return {
        "period_days": days,
        "recorded_outputs": sum(row["outputs"] for row in breakdown),
        "breakdown": breakdown,
        "metric_note": (
            "Counts saved image/audio assets by provider. Does not include failed calls, "
            "token usage, provider invoice totals or actual USD spending."
        ),
    }
