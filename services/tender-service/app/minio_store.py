"""MinIO helpers for people's patrol photos."""

from __future__ import annotations

import io
import os
from dataclasses import dataclass
from hashlib import sha256

from minio import Minio

_CLIENT: Minio | None = None

ALLOWED_PHOTO_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
MAX_PHOTO_BYTES = 5 * 1024 * 1024


@dataclass
class StoredObject:
    bucket: str
    object_key: str
    content_type: str
    size: int
    sha256_hex: str


def _client() -> Minio:
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT
    endpoint = os.getenv("MINIO_ENDPOINT", "minio:9000")
    access_key = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    secret_key = os.getenv("MINIO_SECRET_KEY", "minioadmin")
    secure = os.getenv("MINIO_SECURE", "false").lower() in {"1", "true", "yes", "on"}
    _CLIENT = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)
    return _CLIENT


def store_bytes(
    data: bytes,
    *,
    object_prefix: str,
    filename: str,
    content_type: str = "application/octet-stream",
    bucket: str | None = None,
) -> StoredObject:
    bucket_name = bucket or os.getenv("MINIO_RAW_BUCKET", "ecotender-raw")
    digest = sha256(data).hexdigest()
    ext = ""
    if "." in filename:
        ext = "." + filename.rsplit(".", 1)[-1].lower()
    elif content_type in ALLOWED_PHOTO_TYPES:
        ext = ALLOWED_PHOTO_TYPES[content_type]
    object_key = f"{object_prefix.strip('/')}/{digest[:2]}/{digest}{ext}"
    client = _client()
    if not client.bucket_exists(bucket_name):
        client.make_bucket(bucket_name)
    client.put_object(
        bucket_name,
        object_key,
        io.BytesIO(data),
        length=len(data),
        content_type=content_type,
    )
    return StoredObject(
        bucket=bucket_name,
        object_key=object_key,
        content_type=content_type,
        size=len(data),
        sha256_hex=digest,
    )


def fetch_bytes(bucket: str, object_key: str) -> tuple[bytes, str | None]:
    client = _client()
    response = client.get_object(bucket, object_key)
    try:
        data = response.read()
        content_type = response.headers.get("Content-Type")
    finally:
        response.close()
        response.release_conn()
    return data, content_type
