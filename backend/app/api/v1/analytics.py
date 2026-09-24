"""Aggregate performance data for a published video."""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models.analytics import AnalyticsSnapshot
from app.db.models.publishing import PublishedVideo
from app.db.models.user import User
from app.db.session import get_db

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("")
async def get_analytics(video_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(PublishedVideo).where(PublishedVideo.video_id == video_id))
    published = list(result.scalars().all())
    snapshots = []
    for pv in published:
        snap_result = await db.execute(
            select(AnalyticsSnapshot)
            .where(AnalyticsSnapshot.published_video_id == pv.id)
            .order_by(AnalyticsSnapshot.created_at.desc())
            .limit(1)
        )
        snap = snap_result.scalar_one_or_none()
        snapshots.append(
            {
                "platform": pv.platform,
                "status": pv.status.value,
                "views": snap.views if snap else 0,
                "likes": snap.likes if snap else 0,
                "shares": snap.shares if snap else 0,
                "comments": snap.comments if snap else 0,
            }
        )
    return {"video_id": str(video_id), "channels": snapshots}
