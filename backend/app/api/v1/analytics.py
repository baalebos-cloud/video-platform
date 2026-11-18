"""Aggregate performance data for a published video."""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.deps import get_current_user
from app.db.models.analytics import AnalyticsSnapshot
from app.db.models.publishing import PublishedVideo
from app.db.models.user import User
from app.security.permissions import require_video_owner
from app.db.session import get_db

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("")
async def get_analytics(video_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await require_video_owner(db, video_id, user.id)

    # One query for every published channel's latest snapshot, instead of the
    # previous N+1 (one SELECT per PublishedVideo row). A window function
    # ranks each published_video_id's snapshots by recency so the DB does the
    # "latest per group" work, and a single outer join carries channels that
    # have no snapshot yet (rn == 1 match is simply absent, not NULL rows).
    ranked_snapshots = (
        select(
            AnalyticsSnapshot,
            func.row_number()
            .over(
                partition_by=AnalyticsSnapshot.published_video_id,
                order_by=AnalyticsSnapshot.created_at.desc(),
            )
            .label("rn"),
        )
        .subquery()
    )
    LatestSnapshot = aliased(AnalyticsSnapshot, ranked_snapshots)

    result = await db.execute(
        select(PublishedVideo, LatestSnapshot)
        .outerjoin(
            ranked_snapshots,
            and_(
                ranked_snapshots.c.published_video_id == PublishedVideo.id,
                ranked_snapshots.c.rn == 1,
            ),
        )
        .where(PublishedVideo.video_id == video_id)
    )

    channels = [
        {
            "platform": pv.platform,
            "status": pv.status.value,
            "views": snap.views if snap else 0,
            "likes": snap.likes if snap else 0,
            "shares": snap.shares if snap else 0,
            "comments": snap.comments if snap else 0,
        }
        for pv, snap in result.all()
    ]
    return {"video_id": str(video_id), "channels": channels}
