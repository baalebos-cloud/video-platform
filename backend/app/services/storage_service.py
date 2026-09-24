"""
Object storage service — thin wrapper around an S3-compatible client
(works with AWS S3, MinIO, Cloudflare R2, etc.) Media binaries are never
stored in PostgreSQL rows; only their storage_key + metadata are (see
docs/architecture.md, "Database Blueprint").
"""
import hashlib
import uuid
from datetime import timedelta

import boto3
from botocore.client import Config

from app.config.settings import get_settings

settings = get_settings()


def _client():
    client_kwargs = dict(
        aws_access_key_id=settings.storage_access_key,
        aws_secret_access_key=settings.storage_secret_key,
        config=Config(signature_version="s3v4"),
    )
    if settings.storage_endpoint:
        client_kwargs["endpoint_url"] = settings.storage_endpoint
    return boto3.client("s3", **client_kwargs)


def put_object(data: bytes, *, content_type: str, prefix: str = "assets") -> tuple[str, str, int]:
    """Uploads bytes and returns (storage_key, checksum, size_bytes)."""
    key = f"{prefix}/{uuid.uuid4()}"
    checksum = hashlib.sha256(data).hexdigest()
    _client().put_object(Bucket=settings.storage_bucket, Key=key, Body=data, ContentType=content_type)
    return key, checksum, len(data)


def get_signed_url(storage_key: str, expires_in: timedelta = timedelta(minutes=15)) -> str:
    """Short-lived signed URL for private media, per the security guidelines."""
    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.storage_bucket, "Key": storage_key},
        ExpiresIn=int(expires_in.total_seconds()),
    )


def get_object_bytes(storage_key: str) -> bytes:
    obj = _client().get_object(Bucket=settings.storage_bucket, Key=storage_key)
    return obj["Body"].read()
