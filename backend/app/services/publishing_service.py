"""Real opt-in YouTube upload / TikTok inbox upload; mock remains local-only."""
import asyncio
import httpx
from app.config.settings import get_settings
from app.config.logging import get_logger
from app.services.storage_service import get_publishable_object_bytes

logger = get_logger("services.publishing")
MAX_PUBLISH_BYTES = 60 * 1024 * 1024

class MockPublishingProvider:
    name = "mock"
    async def publish(self, asset_ref: str, metadata: dict, *, access_token: str | None = None) -> dict:
        logger.info("publishing.mock_publish")
        return {"external_post_id":f"mock-post-{asset_ref[-8:]}", "status":"published"}
    async def get_status(self, external_post_id: str) -> dict:
        return {"external_post_id":external_post_id, "status":"published"}
    async def fetch_analytics(self, external_post_id: str) -> dict:
        return {"views":0,"likes":0,"shares":0,"comments":0}

async def _load_media(storage_key: str) -> bytes:
    # Publishing workers read from trusted storage, never arbitrary user URLs.
    data = await asyncio.to_thread(get_publishable_object_bytes, storage_key, MAX_PUBLISH_BYTES)
    if not data or len(data) > MAX_PUBLISH_BYTES:
        raise ValueError("MP4 is empty or exceeds current 60 MB publish limit")
    return data

class YouTubePublishingProvider:
    name = "youtube"
    async def publish(self, asset_ref: str, metadata: dict, *, access_token: str | None = None) -> dict:
        if not access_token: raise ValueError("Missing YouTube OAuth authorization")
        data = await _load_media(asset_ref)
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
                         "X-Upload-Content-Length":str(len(data))}, json=payload)
            init.raise_for_status()
            url = init.headers.get("location","")
            if not url.startswith("https://www.googleapis.com/"):
                raise ValueError("YouTube did not supply a valid upload location")
            uploaded = await client.put(url, content=data,
                headers={"Authorization":f"Bearer {access_token}","Content-Type":"video/mp4",
                         "Content-Length":str(len(data))})
            uploaded.raise_for_status()
            video_id = uploaded.json().get("id")
            if not video_id: raise ValueError("YouTube upload did not return video ID")
            return {"external_post_id":video_id,"status":"published"}

class TikTokInboxPublishingProvider:
    name = "tiktok"
    async def publish(self, asset_ref: str, metadata: dict, *, access_token: str | None = None) -> dict:
        if not access_token: raise ValueError("Missing TikTok OAuth authorization")
        data = await _load_media(asset_ref)
        # Inbox upload requires user to open TikTok and explicitly complete
        # the final post there; do not falsely report as published.
        size = len(data)
        async with httpx.AsyncClient(timeout=120, follow_redirects=False) as client:
            init = await client.post(
                "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/",
                headers={"Authorization":f"Bearer {access_token}"},
                json={"source_info":{"source":"FILE_UPLOAD","video_size":size,
                                     "chunk_size":size,"total_chunk_count":1}})
            init.raise_for_status()
            body = init.json()
            if body.get("error",{}).get("code") not in ("ok",None):
                raise ValueError("TikTok refused to initialize the upload")
            info = body.get("data",{})
            upload_url = info.get("upload_url","")
            publish_id = info.get("publish_id")
            if not upload_url.startswith("https://open-upload.tiktokapis.com/") or not publish_id:
                raise ValueError("TikTok did not supply a valid upload target")
            uploaded = await client.put(upload_url, content=data,
                headers={"Content-Type":"video/mp4",
                         "Content-Length":str(size),
                         "Content-Range":f"bytes 0-{size-1}/{size}"})
            uploaded.raise_for_status()
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
