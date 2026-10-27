"""
Object storage service — thin wrapper around an S3-compatible client
(works with AWS S3, MinIO, Cloudflare R2, etc.) Media binaries are never
stored in PostgreSQL rows; only their storage_key + metadata are (see
docs/architecture.md, "Database Blueprint").

These functions are synchronous (boto3 is). Async callers must run them
via `asyncio.to_thread(...)` so a slow upload can't freeze the event loop
— which matters a lot when the worker runs inside the API process.
"""
import hashlib
import uuid
from datetime import timedelta

import boto3
from botocore.client import Config

from app.config.settings import get_settings

settings = get_settings()


def _client(*, public: bool = False):
    client_kwargs = dict(
        aws_access_key_id=settings.storage_access_key,
        aws_secret_access_key=settings.storage_secret_key,
        region_name=settings.storage_region,
        config=Config(
            signature_version="s3v4",
            # Fail fast with a clear error instead of hanging for minutes
            # (boto3's defaults are 60s timeouts x 5 retries).
            connect_timeout=10,
            read_timeout=30,
            retries={"max_attempts": 2, "mode": "standard"},
        ),
    )
    # Internal MinIO hostname is not reachable from the user's browser.
    # Sign media URLs for the externally reachable endpoint, when configured.
    endpoint = settings.storage_public_base_url if public and settings.storage_public_base_url else settings.storage_endpoint
    if endpoint:
        client_kwargs["endpoint_url"] = endpoint
    return boto3.client("s3", **client_kwargs)


def put_object(data: bytes, *, content_type: str, prefix: str = "assets") -> tuple[str, str, int]:
    """Uploads bytes and returns (storage_key, checksum, size_bytes)."""
    key = f"{prefix}/{uuid.uuid4()}"
    checksum = hashlib.sha256(data).hexdigest()
    _client().put_object(Bucket=settings.storage_bucket, Key=key, Body=data, ContentType=content_type)
    return key, checksum, len(data)


def get_signed_url(
    storage_key: str, expires_in: timedelta = timedelta(minutes=15),
    *, download_filename: str | None = None,
) -> str:
    """Short-lived signed URL; force attachment only for approved export files."""
    params = {"Bucket": settings.storage_bucket, "Key": storage_key}
    if download_filename:
        params["ResponseContentDisposition"] = f'attachment; filename="{download_filename}"'
        params["ResponseContentType"] = "video/mp4"
    return _client(public=True).generate_presigned_url(
        "get_object",
        Params=params,
        ExpiresIn=int(expires_in.total_seconds()),
    )


def get_publishable_object_bytes(storage_key: str, max_bytes: int = 60 * 1024 * 1024) -> bytes:
    client = _client()
    details = client.head_object(Bucket=settings.storage_bucket, Key=storage_key)
    if details["ContentLength"] <= 0 or details["ContentLength"] > max_bytes:
        raise ValueError("Video file is empty or exceeds upload size limit")
    stream = client.get_object(Bucket=settings.storage_bucket, Key=storage_key)["Body"]
    data = stream.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError("Video file is larger than upload limit")
    return data


def delete_object(storage_key: str) -> None:
    """Immediately revoke the user's saved voice-reference object."""
    _client().delete_object(Bucket=settings.storage_bucket, Key=storage_key)


def get_object_bytes(storage_key: str) -> bytes:
    obj = _client().get_object(Bucket=settings.storage_bucket, Key=storage_key)
    return obj["Body"].read()
