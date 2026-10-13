"""Transactional recovery emails; does not log passwords or reset tokens."""
from urllib.parse import quote

import httpx

from app.config.settings import get_settings


def mail_delivery_configured() -> bool:
    settings = get_settings()
    return bool(settings.reset_email_api_key and settings.reset_email_from)


async def send_password_reset_email(recipient: str, token: str) -> None:
    settings = get_settings()
    if not mail_delivery_configured():
        raise RuntimeError("Recovery email is unconfigured")
    # APP_URL is operator-configured, never derived from Host or request headers.
    reset_url = f"{settings.app_url.rstrip('/')}/reset-password?token={quote(token, safe='')}"
    message = (
        "A password reset was requested for your Baalebos Creator Studio account.\n\n"
        f"Use this link within 30 minutes:\n{reset_url}\n\n"
        "If you did not request this, ignore this email. Anyone with this link can reset your password."
    )
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
        response = await client.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {settings.reset_email_api_key}",
                "Content-Type": "application/json",
                "User-Agent": "Baalebos-Creator-Studio/1.0",
            },
            json={
                "from": settings.reset_email_from,
                "to": [recipient],
                "subject": "Reset your Baalebos password",
                "text": message,
            },
        )
        response.raise_for_status()
