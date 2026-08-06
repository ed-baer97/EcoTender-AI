"""MinIO-backed raw artifact storage for ingestion workers."""

from __future__ import annotations

import io
import os
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from minio import Minio


@dataclass
class StoredObject:
    bucket: str
    object_key: str
    content_type: str
    size: int
    sha256_hex: str

    def to_meta(self, **extra: Any) -> dict[str, Any]:
        return {
            "bucket": self.bucket,
            "object_key": self.object_key,
            "content_type": self.content_type,
            "size": self.size,
            "sha256": self.sha256_hex,
            **extra,
        }


_CLIENT: Minio | None = None


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
