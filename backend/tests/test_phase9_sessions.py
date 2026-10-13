"""Regression checks for database-bound, rotating refresh sessions."""
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request

from app.db.models.user import UserStatus
from app.security.auth import decode_token
from app.services import user_sessions
from app.api.deps import get_current_user

def user():
    return SimpleNamespace(id=uuid.uuid4(), status=UserStatus.ACTIVE, session_version=0)

@pytest.mark.asyncio
async def test_new_session_stores_no_raw_refresh_secret():
    db = AsyncMock()
    account = user()
    with patch.object(user_sessions, "create_refresh_token", wraps=user_sessions.create_refresh_token):
        result = await user_sessions.create_session(db, account)
    token = decode_token(result["refresh_token"])
    session = db.add.call_args.args[0]
    assert session.id is not None
    assert token["jti"] not in repr(session)
    assert session.refresh_hash == user_sessions._digest(token["jti"])
    assert decode_token(result["access_token"])["sid"] == str(session.id)
    db.commit.assert_awaited_once()

@pytest.mark.asyncio
async def test_refresh_rotates_jti_hash_and_rejects_replay():
    db = AsyncMock()
    account = user()
    prior = await user_sessions.create_session(db, account)
    record = db.add.call_args.args[0]
    prior_digest = record.refresh_hash
    db.scalar.side_effect = [record, account, None]
    current = await user_sessions.rotate_session(db, prior["refresh_token"])
    assert record.refresh_hash != prior_digest
    assert current["refresh_token"] != prior["refresh_token"]
    with pytest.raises(HTTPException) as exc:
        await user_sessions.rotate_session(db, prior["refresh_token"])
    assert exc.value.status_code == 401

@pytest.mark.asyncio
async def test_logout_revokes_only_given_session():
    account = user()
    db = AsyncMock()
    original = await user_sessions.create_session(db, account)
    row = db.add.call_args.args[0]
    db.scalar.return_value = row
    await user_sessions.revoke_refresh(db, original["refresh_token"])
    assert row.revoked is True

@pytest.mark.asyncio
async def test_revoked_session_id_is_not_authorized():
    account = user()
    result = MagicMock()
    result.scalar_one_or_none.return_value = account
    db = AsyncMock()
    db.execute.return_value = result
    db.scalar.return_value = None
    request = Request({"type":"http", "headers":[]})
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="test")
    with patch("app.api.deps.decode_token", return_value={
        "sub":str(account.id),"type":"access","sv":0,"sid":str(uuid.uuid4()),
    }):
        with pytest.raises(HTTPException) as exc:
            await get_current_user(request, credentials=creds, db=db)
    assert exc.value.status_code == 401

@pytest.mark.asyncio
async def test_previous_phase_refresh_without_jti_cannot_be_rotated():
    from app.security.auth import create_refresh_token
    db = AsyncMock()
    with pytest.raises(HTTPException):
        await user_sessions.rotate_session(db, create_refresh_token(str(uuid.uuid4())))
