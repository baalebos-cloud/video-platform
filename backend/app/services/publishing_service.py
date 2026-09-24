"""
Publishing orchestrator — routes to the configured PublishingProvider
adapter per platform (blueprint section 13). Real OAuth + upload flows
for YouTube/TikTok/etc. are implemented as adapters under
app/ai/providers (or a dedicated app/publishing/providers package as the
platform list grows); only a mock adapter ships by default.
"""
from app.config.logging import get_logger

logger = get_logger("services.publishing")


class MockPublishingProvider:
    """Stand-in publishing adapter — logs the action instead of calling a real platform API."""

    name = "mock"

    async def publish(self, asset_ref: str, metadata: dict) -> dict:
        logger.info("publishing.mock_publish", asset_ref=asset_ref, title=metadata.get("title"))
        return {"external_post_id": f"mock-post-{asset_ref[-8:]}", "status": "published"}

    async def get_status(self, external_post_id: str) -> dict:
        return {"external_post_id": external_post_id, "status": "published"}

    async def fetch_analytics(self, external_post_id: str) -> dict:
        return {"views": 0, "likes": 0, "shares": 0, "comments": 0}


_PROVIDERS = {"mock": MockPublishingProvider()}


def get_publishing_provider(platform: str):
    # Real platforms (youtube, tiktok, facebook...) register their adapter
    # here once OAuth credentials are configured; unconfigured platforms
    # fall back to the mock adapter so the publish flow is still testable.
    return _PROVIDERS.get(platform, _PROVIDERS["mock"])
