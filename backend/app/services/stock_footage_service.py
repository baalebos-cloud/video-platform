"""Licensed stock footage for user-requested video generation.

One bounded Pixabay search per scene, 24-hour Redis search caching, and no
permanent Pixabay hotlinks. Videos are stored privately in the user's existing
object storage. Search failures are allowed to fall back to generated images.
"""
import asyncio
import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx
from redis.exceptions import RedisError

from app.config.settings import get_settings
from app.security.rate_limit import get_redis

PIXABAY_API_URL = "https://pixabay.com/api/videos/"
MAX_VIDEO_BYTES = 18 * 1024 * 1024
CACHE_TTL_SECONDS = 86400


@dataclass(frozen=True)
class StockClip:
    video_bytes: bytes
    source_page_url: str


def search_terms(text: str) -> str:
    """Convert a cinematic shot description into a short footage search query."""
    ignored = {"cinematic", "shot", "wide", "close", "up", "lighting", "high", "detail",
               "realistic", "camera", "photorealistic", "dramatic", "scene", "beautiful",
               "no", "text", "slow", "motion", "show", "with", "and", "the", "of", "in"}
    words = [word for word in re.findall(r"[a-zA-Z0-9]+", text.lower())
             if len(word) > 2 and word not in ignored]
    return " ".join(words[:5])[:100]


def _safe_pixabay_cdn_url(url: str) -> bool:
    parts = urlsplit(url)
    return (parts.scheme == "https" and parts.hostname == "cdn.pixabay.com"
            and parts.port in (None, 443) and parts.path.endswith(".mp4")
            and not parts.username and not parts.password)


async def find_stock_clip(prompt: str) -> StockClip | None:
    settings = get_settings()
    if not settings.stock_footage_enabled or not settings.pixabay_api_key:
        return None
    q = search_terms(prompt)
    if len(q) < 3:
        return None
    cache_key = "stock:pixabay:query:v1:" + hashlib.sha256(q.encode()).hexdigest()
    cached = None
    try:
        cached = await get_redis().get(cache_key)
    except (RedisError, OSError):
        pass
    if cached:
        try:
            document = json.loads(cached)
        except (ValueError, TypeError):
            document = {}
    else:
        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
                response = await client.get(PIXABAY_API_URL, params={
                    "key": settings.pixabay_api_key, "q": q, "per_page": 3,
                    "safesearch": "true",
                })
            if response.status_code != 200:
                return None
            document = response.json()
            try:
                await get_redis().set(cache_key, json.dumps(document), ex=CACHE_TTL_SECONDS)
            except (RedisError, OSError):
                pass
        except (httpx.HTTPError, ValueError):
            return None
    hits = document.get("hits", []) if isinstance(document, dict) else []
    if not isinstance(hits, list):
        return None
    for hit in hits[:3]:
        try:
            medium = hit["videos"]["medium"]
            url, size = medium["url"], int(medium["size"])
            page_url = hit["pageURL"]
            if (not isinstance(url, str) or not _safe_pixabay_cdn_url(url)
                or not isinstance(page_url, str) or not page_url.startswith("https://pixabay.com/")
                or not 0 < size <= MAX_VIDEO_BYTES):
                continue
            data = bytearray()
            async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
                async with client.stream("GET", url) as response:
                    if response.status_code != 200:
                        continue
                    async for chunk in response.aiter_bytes():
                        data.extend(chunk)
                        if len(data) > MAX_VIDEO_BYTES:
                            break
            if 10000 <= len(data) <= MAX_VIDEO_BYTES:
                return StockClip(video_bytes=bytes(data), source_page_url=page_url)
        except (KeyError, TypeError, ValueError, httpx.HTTPError):
            continue
    return None


def frame_from_video(video_bytes: bytes) -> bytes:
    """Generate preview PNG from the licensed MP4; no arbitrary remote inputs."""
    if not 10000 <= len(video_bytes) <= MAX_VIDEO_BYTES:
        raise ValueError("Invalid stock video size")
    result = subprocess.run(
        ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
         "-i", "pipe:0", "-frames:v", "1", "-vf", "scale=480:-2",
         "-f", "image2pipe", "-vcodec", "png", "pipe:1"],
        input=video_bytes, capture_output=True, timeout=30, check=True,
    )
    if not result.stdout.startswith(b"\x89PNG\r\n\x1a\n") or len(result.stdout) > 8 * 1024 * 1024:
        raise ValueError("Pixabay thumbnail was invalid")
    return result.stdout
