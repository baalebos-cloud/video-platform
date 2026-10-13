"""Publishes an approved, rendered video to a target platform (arq task)."""
import uuid

from app.config.logging import get_logger
from app.db.models.publishing import PublishedVideo, PublishStatus, PublishingAccount
from app.services.publishing_oauth import usable_token
from app.db.models.video import Video
from app.db.session import session_scope
from app.services.publishing_service import get_publishing_provider


logger = get_logger("workers.publish")


async def publish_task(ctx, payload: dict) -> None:
    video_id = uuid.UUID(payload["video_id"])
    platform = payload["platform"]
    metadata = payload.get("metadata", {})

    async with session_scope() as db:
        video = await db.get(Video, video_id)
        if video is None or video.output_asset_id is None:
            logger.error("publish.missing_video_or_asset", video_id=str(video_id))
            return

        account = await db.get(PublishingAccount, uuid.UUID(payload["publishing_account_id"]))
        if account is None or account.platform != platform:
            logger.error("publish.missing_connection", platform=platform)
            return
        published = PublishedVideo(
            video_id=video.id,
            publishing_account_id=payload["publishing_account_id"],
            platform=platform,
            status=PublishStatus.UPLOADING,
        )
        db.add(published)
        await db.flush()

        provider = get_publishing_provider(platform)
        try:
            token = await usable_token(db, account) if platform != "mock" else None
            result = await provider.publish(payload["asset_storage_key"], metadata, access_token=token)
            published.external_post_id = result["external_post_id"]
            # TikTok inbox requires the creator to finish posting in TikTok.
            published.status = (PublishStatus.PUBLISHED if result["status"] == "published"
                                else PublishStatus.READY)
            logger.info("publish.succeeded", video_id=str(video_id), platform=platform)
        except Exception as exc:  # noqa: BLE001 — publishing adapters raise heterogeneous errors
            published.status = PublishStatus.PUBLISH_FAILED
            logger.error("publish.failed", video_id=str(video_id), error_type=type(exc).__name__)
