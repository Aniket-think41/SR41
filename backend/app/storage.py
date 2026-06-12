"""
File storage — switchable between local disk (dev) and S3/R2 (prod) via the
STORAGE_BACKEND setting. Both implement the same `save_bytes(...) -> file_url`
contract, so the rest of the app never cares which is active.

Local:  writes under settings.upload_dir and serves the bytes from the
        /uploads static mount (see main.py); file_url = PUBLIC_BASE/uploads/<key>.
S3:     uploads with boto3 put_object; file_url = S3_PUBLIC_BASE_URL/<key>
        (works with AWS S3, Cloudflare R2, MinIO — anything boto3-compatible).
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from .config import get_settings

settings = get_settings()

# Allowed upload kinds → permitted extensions. "diagram" maps to image formats
# (PNG/SVG export), which is what design tools produce.
ALLOWED_EXT: dict[str, set[str]] = {
    "image": {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".avif"},
    "video": {".mp4", ".webm", ".ogg", ".mov", ".m4v"},
    "file": {".pdf", ".md", ".txt", ".json", ".csv", ".zip", ".skill", ".docx", ".pptx", ".xlsx"},
}
# Generic content types per kind, used when the client doesn't send one.
DEFAULT_CONTENT_TYPE = {"image": "application/octet-stream", "video": "application/octet-stream", "file": "application/octet-stream"}


class StorageError(Exception):
    pass


def _safe_name(filename: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9._-]", "-", filename or "").strip("-.") or "upload"
    return name[:120]


def ext_allowed(kind: str, filename: str) -> bool:
    allowed = ALLOWED_EXT.get(kind)
    if allowed is None:
        return False
    suffix = Path(_safe_name(filename)).suffix.lower()
    return suffix in allowed


def _make_key(kind: str, username: str, filename: str) -> str:
    # kind/username/<random>-<safe-name> — random prefix avoids collisions/overwrites
    return f"{kind}/{username}/{uuid.uuid4().hex[:12]}-{_safe_name(filename)}"


def save_bytes(data: bytes, *, kind: str, username: str, filename: str, content_type: str | None) -> str:
    """Persist bytes and return a public URL. Routes to local or S3 by config."""
    key = _make_key(kind, username, filename)
    ct = content_type or DEFAULT_CONTENT_TYPE.get(kind, "application/octet-stream")

    if settings.storage_backend == "s3":
        if not settings.s3_bucket:
            raise StorageError("STORAGE_BACKEND=s3 but S3_BUCKET is not configured")
        import boto3  # imported lazily — only needed when S3 is active

        s3 = boto3.client(
            "s3",
            region_name=settings.s3_region,
            endpoint_url=settings.s3_endpoint_url or None,
            aws_access_key_id=settings.aws_access_key_id or None,
            aws_secret_access_key=settings.aws_secret_access_key or None,
        )
        s3.put_object(Bucket=settings.s3_bucket, Key=key, Body=data, ContentType=ct)
        base = settings.s3_public_base_url.rstrip("/") or f"https://{settings.s3_bucket}.s3.amazonaws.com"
        return f"{base}/{key}"

    # local backend (default)
    dest = Path(settings.upload_dir) / key
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    base = settings.public_base_url.rstrip("/")
    return f"{base}/uploads/{key}"
