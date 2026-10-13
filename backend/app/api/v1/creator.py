"""Creator home and analytics from owned projects and recorded publishing snapshots.

This endpoint never fabricates stats; empty accounts receive zero-value metrics.
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models.analytics import AnalyticsSnapshot
from app.db.models.project import Project
from app.db.models.publishing import PublishedVideo, PublishStatus
from app.db.models.user import User
from app.db.models.video import Video, VideoStatus
from app.db.session import get_db

router = APIRouter(prefix="/creator", tags=["creator"])


def latest_snapshot_by_post(rows) -> dict:
    latest = {}
    for snapshot in rows:
        # Input is ordered by snapshot timestamp descending.
        if snapshot.published_video_id not in latest:
            latest[snapshot.published_video_id] = snapshot
    return latest


def aggregate_platforms(posts, latest) -> list[dict]:
    totals = defaultdict(lambda: {
        "posts": 0, "views": 0, "likes": 0, "shares": 0, "comments": 0,
    })
    for post in posts:
        row = totals[post.platform]
        row["posts"] += 1
        snap = latest.get(post.id)
        if snap:
            for key in ("views", "likes", "shares", "comments"):
                row[key] += max(0, getattr(snap, key) or 0)
    return [{"platform": name, **metrics} for name, metrics in sorted(totals.items())]


@router.get("/overview")
async def creator_overview(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    project_count = await db.scalar(
        select(func.count(Project.id)).where(Project.user_id == user.id)
    )
    video_count = await db.scalar(
        select(func.count(Video.id)).join(Project).where(Project.user_id == user.id)
    )
    ready_count = await db.scalar(
        select(func.count(Video.id)).join(Project).where(
            Project.user_id == user.id, Video.status == VideoStatus.READY,
        )
    )
    projects_result = await db.execute(
        select(Project).where(Project.user_id == user.id)
        .order_by(Project.created_at.desc()).limit(8)
    )
    projects = list(projects_result.scalars().all())
    recent_result = await db.execute(
        select(Video).join(Project).where(Project.user_id == user.id)
        .order_by(Video.created_at.desc(), Video.id.desc()).limit(12)
    )
    recent = list(recent_result.scalars().all())
    published_result = await db.execute(
        select(PublishedVideo).join(Video).join(Project)
        .where(Project.user_id == user.id, PublishedVideo.status == PublishStatus.PUBLISHED)
    )
    published = list(published_result.scalars().all())

    # Only the latest stored snapshot of each published post contributes
    # to lifetime totals. Older snapshots must not be double counted.
    latest = {}
    history = []
    if published:
        post_ids = [post.id for post in published]
        snapshots_result = await db.execute(
            select(AnalyticsSnapshot)
            .where(AnalyticsSnapshot.published_video_id.in_(post_ids))
            .order_by(AnalyticsSnapshot.created_at.desc(), AnalyticsSnapshot.id.desc())
        )
        history = list(snapshots_result.scalars().all())
        latest = latest_snapshot_by_post(history)

    platforms = aggregate_platforms(published, latest)
    metrics = {
        key: sum(platform[key] for platform in platforms)
        for key in ("views", "likes", "shares", "comments")
    }
    # Trend represents sums of recorded, cumulative snapshots on each day;
    # it is intentionally not labelled as per-day new traffic.
    today = datetime.now(timezone.utc).date()
    trend = []
    by_day = defaultdict(dict)
    for snap in history:
        day = snap.created_at.date()
        if day < today - timedelta(days=13) or day > today:
            continue
        if snap.published_video_id not in by_day[day]:
            by_day[day][snap.published_video_id] = snap
    for index in range(13, -1, -1):
        day = today - timedelta(days=index)
        snaps = by_day[day].values()
        trend.append({
            "date": day.isoformat(),
            "views": sum(max(0, s.views or 0) for s in snaps),
            "engagement": sum(max(0, (s.likes or 0) + (s.shares or 0) + (s.comments or 0)) for s in snaps),
        })
    return {
        "stats": {
            "projects": project_count or 0, "total_videos": video_count or 0,
            "ready_videos": ready_count or 0, "published_posts": len(published),
            **metrics,
        },
        "projects": [
            {"id": str(p.id), "name": p.name, "niche": p.niche}
            for p in projects
        ],
        "recent_videos": [
            {
                "id": str(v.id), "project_id": str(v.project_id),
                "topic": v.topic, "status": v.status.value,
                "progress": v.progress, "platform": v.platform,
                "duration_seconds": v.duration_seconds,
                "thumbnail_asset_id": str(v.thumbnail_asset_id) if v.thumbnail_asset_id else None,
                "created_at": v.created_at.isoformat(),
            }
            for v in recent
        ],
        "platforms": platforms,
        "trend": trend,
        "trend_description": "Sum of stored cumulative snapshots on each date; not daily new views.",
    }
