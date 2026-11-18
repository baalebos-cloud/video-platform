"""Real opt-in YouTube upload / TikTok inbox upload; mock remains local-only.

Uploads stream from object storage in fixed-size ranged chunks rather than
loading the whole file into process memory first. That matters more now
that the render pipeline can produce a CMAF master well past the old
60MB in-memory cap (see docs/video-generation-upgrade.md / the ABR ladder
work) — a worker process shouldn't need gigabytes of RAM just to publish
a video it already rendered.
"""
import asyncio
import math
from collections.abc import AsyncIterator

import httpx

from app.config.settings import get_settings
from app.config.logging import get_logger
from app.services import storage_service

logger = get_logger("services.publishing")

# A sane ceiling against a corrupted/runaway render, not a memory limit —
# chunked streaming means publish cost no longer scales with this number.
MAX_PUBLISH_BYTES = 2 * 1024 * 1024 * 1024  # 2 GiB
CHUNK_SIZE = 8 * 1024 * 1024  # 8 MiB, per the platform APIs' own chunking guidance


class MockPublishingProvider:
    name = "mock"
    async def publish(self, asset_ref: str, metadata: dict, *, access_token: str | None = None) -> dict:
        logger.info("publishing.mock_publish")
        return {"external_post_id":f"mock-post-{asset_ref[-8:]}", "status":"published"}
    async def get_status(self, external_post_id: str) -> dict:
        return {"external_post_id":external_post_id, "status":"published"}
    async def fetch_analytics(self, external_post_id: str) -> dict:
        return {"views":0,"likes":0,"shares":0,"comments":0}


async def _object_size(storage_key: str) -> int:
    # Publishing workers read from trusted storage, never arbitrary user URLs.
    size = await asyncio.to_thread(storage_service.get_object_size, storage_key)
    if size <= 0 or size > MAX_PUBLISH_BYTES:
        raise ValueError("Video file is empty or exceeds the current publish size limit")
    return size


async def _iter_chunks(storage_key: str, total_size: int) -> AsyncIterator[tuple[int, int, bytes]]:
    """Yields (range_start, range_end_inclusive, chunk_bytes) covering the whole object."""
    start = 0
    while start < total_size:
        end = min(start + CHUNK_SIZE, total_size) - 1
        chunk = await asyncio.to_thread(storage_service.get_object_range_bytes, storage_key, start, end)
        if not chunk:
            raise ValueError("Storage returned an empty chunk while streaming the publish upload")
        yield start, end, chunk
        start = end + 1


class YouTubePublishingProvider:
    name = "youtube"
    async def publish(self, asset_ref: str, metadata: dict, *, access_token: str | None = None) -> dict:
        if not access_token: raise ValueError("Missing YouTube OAuth authorization")
        total_size = await _object_size(asset_ref)
        # Default to PRIVATE; never make a user's new video public without
        # review and an explicit opt-in in a future creator-facing UI.
        payload = {"snippet":{"title":metadata["title"][:100],
                              "description":metadata.get("description","")[:5000]},
                   "status":{"privacyStatus":"private","selfDeclaredMadeForKids":False}}
        async with httpx.AsyncClient(timeout=120, follow_redirects=False) as client:
            init = await client.post(
                "https://www.googleapis.com/upload/youtube/v3/videos",
                params={"uploadType":"resumable","part":"snippet,status"},
                headers={"Authorization":f"Bearer {access_token}","X-Upload-Content-Type":"video/mp4",
                         "X-Upload-Content-Length":str(total_size)}, json=payload)
            init.raise_for_status()
            url = init.headers.get("location","")
            if not url.startswith("https://www.googleapis.com/"):
                raise ValueError("YouTube did not supply a valid upload location")

            video_id = None
            async for start, end, chunk in _iter_chunks(asset_ref, total_size):
                response = await client.put(
                    url, content=chunk,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "video/mp4",
                        "Content-Length": str(len(chunk)),
                        "Content-Range": f"bytes {start}-{end}/{total_size}",
                    },
                )
                if response.status_code == 308:
                    # Resumable-upload "keep going"; the Range header it
                    # returns should match what we just sent — the GCS/
                    # YouTube resumable protocol doesn't require resending
                    # on a clean sequential upload, so just continue.
                    continue
                if response.status_code in (200, 201):
                    video_id = response.json().get("id")
                    break
                response.raise_for_status()

            if not video_id:
                raise ValueError("YouTube upload did not return video ID")
            return {"external_post_id":video_id,"status":"published"}


class TikTokInboxPublishingProvider:
    name = "tiktok"
    async def publish(self, asset_ref: str, metadata: dict, *, access_token: str | None = None) -> dict:
        if not access_token: raise ValueError("Missing TikTok OAuth authorization")
        total_size = await _object_size(asset_ref)
        total_chunk_count = max(1, math.ceil(total_size / CHUNK_SIZE))
        # Inbox upload requires user to open TikTok and explicitly complete
        # the final post there; do not falsely report as published.
        async with httpx.AsyncClient(timeout=120, follow_redirects=False) as client:
            init = await client.post(
                "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/",
                headers={"Authorization":f"Bearer {access_token}"},
                json={"source_info":{"source":"FILE_UPLOAD","video_size":total_size,
                                     "chunk_size":min(CHUNK_SIZE, total_size),
                                     "total_chunk_count":total_chunk_count}})
            init.raise_for_status()
            body = init.json()
            if body.get("error",{}).get("code") not in ("ok",None):
                raise ValueError("TikTok refused to initialize the upload")
            info = body.get("data",{})
            upload_url = info.get("upload_url","")
            publish_id = info.get("publish_id")
            if not upload_url.startswith("https://open-upload.tiktokapis.com/") or not publish_id:
                raise ValueError("TikTok did not supply a valid upload target")

            last_response = None
            async for start, end, chunk in _iter_chunks(asset_ref, total_size):
                last_response = await client.put(
                    upload_url, content=chunk,
                    headers={
                        "Content-Type": "video/mp4",
                        "Content-Length": str(len(chunk)),
                        "Content-Range": f"bytes {start}-{end}/{total_size}",
                    },
                )
                # Per TikTok's chunked-upload contract, every chunk but the
                # last returns a non-2xx "partial content received" status;
                # only the final chunk's response is a real success/failure.
                if end + 1 < total_size:
                    continue
                last_response.raise_for_status()

            if last_response is None:
                raise ValueError("TikTok upload sent no data")
            return {"external_post_id":publish_id,"status":"awaiting_creator_action"}


def get_publishing_provider(platform: str):
    s = get_settings()
    if platform == "mock":
        return MockPublishingProvider()
    if platform == "youtube" and s.youtube_client_id and s.youtube_client_secret and s.publishing_token_encryption_key:
        return YouTubePublishingProvider()
    if platform == "tiktok" and s.tiktok_client_id and s.tiktok_client_secret and s.publishing_token_encryption_key:
        return TikTokInboxPublishingProvider()
    raise ValueError(f"Publishing provider is not configured: {platform}")
