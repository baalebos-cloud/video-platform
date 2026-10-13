"""Phase 12: OAuth encryption, provider gating, metadata validation."""
import uuid
from unittest.mock import patch
import pytest
from fastapi import HTTPException
from cryptography.fernet import Fernet
from app.config.settings import Settings
from app.services import publishing_oauth, publishing_service

def test_encrypted_vendor_credentials_never_stored_as_plaintext():
    key = Fernet.generate_key().decode()
    settings = Settings(_env_file=None, publishing_token_encryption_key=key)
    with patch.object(publishing_oauth,"get_settings",return_value=settings):
        sealed = publishing_oauth.encrypt_tokens({"access_token":"super-sensitive-token","expires_at":"2027-01-01T00:00:00+00:00"})
        assert "super-sensitive-token" not in sealed
        assert publishing_oauth.decrypt_tokens(sealed)["access_token"]=="super-sensitive-token"

def test_unconfigured_real_publishing_fails_closed():
    with patch.object(publishing_service,"get_settings",return_value=Settings(
        _env_file=None,youtube_client_id=None,tiktok_client_id=None)):
        with pytest.raises(ValueError):
            publishing_service.get_publishing_provider("youtube")
        with pytest.raises(ValueError):
            publishing_service.get_publishing_provider("tiktok")
        assert publishing_service.get_publishing_provider("mock").name=="mock"

def test_oauth_needs_server_config_and_rejects_unknown_platform():
    with patch.object(publishing_oauth,"get_settings",return_value=Settings(
        _env_file=None,youtube_client_id=None,tiktok_client_id=None)):
        with pytest.raises(HTTPException):
            publishing_oauth.oauth_settings("youtube")
        with pytest.raises(HTTPException):
            publishing_oauth.oauth_settings("unknown")

def test_real_providers_fail_without_oauth_token_before_io():
    import asyncio
    with pytest.raises(ValueError, match="OAuth"):
        asyncio.run(publishing_service.YouTubePublishingProvider().publish("any.mp4",{"title":"x"}))
    with pytest.raises(ValueError, match="OAuth"):
        asyncio.run(publishing_service.TikTokInboxPublishingProvider().publish("any.mp4",{"title":"x"}))
