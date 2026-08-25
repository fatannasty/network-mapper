"""Application security primitives.

- Fernet (AES-128-CBC + HMAC-SHA256) encryption for secrets stored at rest.
- scrypt password hashing (stdlib, no extra deps).
- HMAC-SHA256 signed bearer tokens for RBAC sessions.

Key management:
    ENCRYPTION_KEY  env var overrides the Fernet key.
    SECRET_KEY      env var overrides the token-signing key.
    Otherwise a random key is generated and persisted to a gitignored
    file (backend/.secret_key) so zero-config dev keeps working. In
    production, always set both env vars explicitly.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time

from cryptography.fernet import Fernet

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
KEY_FILE = os.path.join(BACKEND_DIR, ".secret_key")

TOKEN_TTL_SECONDS = 12 * 3600
ROLES = ("admin", "operator", "viewer")

_encrypted_prefix = "enc:v1:"


def hash_api_token(token: str) -> str:
    """sha256 hex of an API token (never store the plaintext)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ── Key management ───────────────────────────────────────────────────────────

def _load_or_create_key() -> bytes:
    """Return the 32-byte url-safe key, loading from env/keyfile or creating it."""
    env_key = os.environ.get("ENCRYPTION_KEY") or os.environ.get("SECRET_KEY")
    if env_key:
        try:
            return _normalize_key(env_key)
        except ValueError:
            pass
    if os.path.exists(KEY_FILE):
        raw = open(KEY_FILE, "rb").read().strip()
        if len(raw) == 43 or len(raw) == 44:  # urlsafe base64 of 32 bytes
            try:
                return base64.urlsafe_b64decode(raw + b"=" * (-len(raw) % 4))
            except Exception:
                pass
    key = secrets.token_bytes(32)
    encoded = base64.urlsafe_b64encode(key).rstrip(b"=")
    open(KEY_FILE, "wb").write(encoded)
    os.chmod(KEY_FILE, 0o600)
    return key


def _normalize_key(key: str) -> bytes:
    raw = key.strip().encode()
    try:
        decoded = base64.urlsafe_b64decode(raw + b"=" * (-len(raw) % 4))
    except Exception:
        decoded = b""
    if len(decoded) == 32:
        return decoded
    # Allow a raw 32-byte hex or plain string key too.
    if len(raw) == 32:
        return raw
    # Derive a stable 32-byte key from any passphrase.
    return hashlib.sha256(raw).digest()


def _fernet() -> Fernet:
    return Fernet(base64.urlsafe_b64encode(_load_or_create_key()))


# ── Secret encryption at rest ────────────────────────────────────────────────

def encrypt_secret(plaintext: str) -> str:
    """Encrypt a secret for storage. Empty strings stay empty."""
    if not plaintext:
        return ""
    token = _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")
    return _encrypted_prefix + token


def decrypt_secret(blob: str) -> str:
    """Decrypt a stored secret. Plaintext/legacy values pass through."""
    if not blob:
        return ""
    if blob.startswith(_encrypted_prefix):
        return _fernet().decrypt(blob[len(_encrypted_prefix):].encode("ascii")).decode("utf-8")
    return blob


# ── Password hashing ─────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

    salt = secrets.token_bytes(16)
    kdf = Scrypt(salt=salt, length=32, n=2**14, r=8, p=1)
    digest = kdf.derive(password.encode("utf-8"))
    return f"scrypt$16384$8$1${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

    try:
        algo, n, r, p, salt_hex, digest_hex = stored.split("$")
        if algo != "scrypt":
            return False
        kdf = Scrypt(salt=bytes.fromhex(salt_hex), length=32, n=int(n), r=int(r), p=int(p))
        digest = kdf.derive(password.encode("utf-8"))
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


# ── Token signing ────────────────────────────────────────────────────────────

def _token_key() -> bytes:
    raw = os.environ.get("SECRET_KEY")
    if raw:
        return _normalize_key(raw)
    return _load_or_create_key()


def create_token(user_id: int, username: str, role: str, ttl: int = TOKEN_TTL_SECONDS) -> str:
    """Return an HMAC-signed bearer token with an expiry."""
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "iat": int(time.time()),
        "exp": int(time.time()) + ttl,
    }
    body = base64.urlsafe_b64encode(json.dumps(payload, sort_keys=True).encode()).rstrip(b"=").decode()
    sig = hmac.new(_token_key(), body.encode(), hashlib.sha256).digest()
    return body + "." + base64.urlsafe_b64encode(sig).rstrip(b"=").decode()


def verify_token(token: str) -> dict | None:
    """Validate a token and return its payload, or None if invalid/expired."""
    try:
        body, sig = token.split(".")
        expected = base64.urlsafe_b64encode(
            hmac.new(_token_key(), body.encode(), hashlib.sha256).digest()
        ).rstrip(b"=").decode()
        if not hmac.compare_digest(sig, expected):
            return None
        raw = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
        payload = json.loads(raw)
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        if payload.get("role") not in ROLES:
            return None
        return payload
    except (ValueError, KeyError, json.JSONDecodeError):
        return None
