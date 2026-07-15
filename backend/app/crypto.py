"""Symmetric encryption for integration credentials at rest.

The rest of the codebase never stores secrets reversibly — it uses redaction
(github.py) or references (PodService.secret_ref). Integration credentials are
the one place we must keep a live secret (an org's GitHub token), so this module
introduces the first at-rest encryption layer, using Fernet (AES-128-CBC + HMAC).

Key material comes from ``settings.integration_secret_key`` (a url-safe base64
32-byte Fernet key). When it's unset we DERIVE a stable key from ``jwt_secret``
so dev works out of the box; production should set an explicit key so rotating
the JWT secret doesn't strand encrypted credentials. Ciphertext is stored in
``OrgIntegration.credentials_enc`` and NEVER serialized back to a client.
"""

from __future__ import annotations

import base64
import hashlib
from functools import lru_cache

from .config import get_settings


@lru_cache
def _fernet():
    from cryptography.fernet import Fernet  # in requirements.txt

    settings = get_settings()
    key = (settings.integration_secret_key or "").strip()
    if key:
        # Accept either a ready Fernet key or arbitrary text (hash → 32 bytes).
        try:
            Fernet(key.encode())
            raw = key.encode()
        except Exception:
            raw = base64.urlsafe_b64encode(hashlib.sha256(key.encode()).digest())
    else:
        # Dev fallback: deterministic key derived from the JWT secret.
        digest = hashlib.sha256(f"integration-creds:{settings.jwt_secret}".encode()).digest()
        raw = base64.urlsafe_b64encode(digest)
    return Fernet(raw)


def encrypt(plaintext: str) -> str:
    """Encrypt a UTF-8 string → url-safe token string (stored in the DB)."""
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt(token: str) -> str:
    """Decrypt a token produced by :func:`encrypt`. Raises on tamper/rotation."""
    return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
