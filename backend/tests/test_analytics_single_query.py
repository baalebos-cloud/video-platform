"""Regression test for the analytics N+1 fix: fetching a video's channel
analytics must issue exactly one query (a windowed join), never one query
per published channel."""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.api.v1 import analytics
from app.db.models.publishing import PublishStatus


@pytest.mark.asyncio
async def test_get_analytics_issues_a_single_query_for_any_number_of_channels():
    video_id = uuid.uuid4()
    user = SimpleNamespace(id=uuid.uuid4())
    db = AsyncMock()

    pv_youtube = SimpleNamespace(id=uuid.uuid4(), platform="youtube", status=PublishStatus.PUBLISHED)
    pv_tiktok = SimpleNamespace(id=uuid.uuid4(), platform="tiktok", status=PublishStatus.PUBLISHED)
    snap_youtube = SimpleNamespace(views=1000, likes=50, shares=5, comments=2)
    # TikTok channel has no snapshot yet -> outer join yields None for it.
    rows = [(pv_youtube, snap_youtube), (pv_tiktok, None)]

    execute_result = SimpleNamespace(all=lambda: rows)
    db.execute.return_value = execute_result

    with patch.object(analytics, "require_video_owner", new_callable=AsyncMock):
        response = await analytics.get_analytics(video_id, user=user, db=db)

    # The whole point of the fix: one DB round-trip, regardless of how many
    # published channels the video has.
    assert db.execute.await_count == 1

    assert response["video_id"] == str(video_id)
    channels = {c["platform"]: c for c in response["channels"]}
    assert channels["youtube"] == {
        "platform": "youtube", "status": "published",
        "views": 1000, "likes": 50, "shares": 5, "comments": 2,
    }
    assert channels["tiktok"] == {
        "platform": "tiktok", "status": "published",
        "views": 0, "likes": 0, "shares": 0, "comments": 0,
    }
