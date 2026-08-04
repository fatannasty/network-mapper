"""Sprint 3: credential encryption, password hashing, and token signing."""

import security
from models import EncryptedString


# ── Secret encryption at rest ─────────────────────────────────────────────────

def test_encrypt_decrypt_round_trip():
    secret = "Cisco#r0ck$!"
    blob = security.encrypt_secret(secret)
    assert blob != secret
    assert blob.startswith("enc:v1:")
    assert security.decrypt_secret(blob) == secret


def test_encrypted_blob_never_contains_plaintext():
    secret = "supersecretcommunity"
    blob = security.encrypt_secret(secret)
    assert "supersecretcommunity" not in blob


def test_legacy_plaintext_passes_through():
    assert security.decrypt_secret("public") == "public"
    assert security.decrypt_secret("") == ""


def test_encrypted_empty_stays_empty():
    assert security.encrypt_secret("") == ""


def test_encrypted_column_round_trips_via_type_decorator():
    col = EncryptedString()
    bound = col.process_bind_param("mysecret", dialect=None)
    assert bound.startswith("enc:v1:")
    assert col.process_result_value(bound, dialect=None) == "mysecret"


# ── Password hashing ──────────────────────────────────────────────────────────

def test_password_hash_and_verify():
    stored = security.hash_password("hunter2")
    assert stored.startswith("scrypt$")
    assert "hunter2" not in stored
    assert security.verify_password("hunter2", stored)
    assert not security.verify_password("wrong", stored)


def test_password_verify_rejects_malformed():
    assert not security.verify_password("x", "not-a-hash")


# ── Token signing ─────────────────────────────────────────────────────────────

def test_token_round_trip():
    token = security.create_token(7, "alice", "operator")
    payload = security.verify_token(token)
    assert payload is not None
    assert payload["sub"] == "7"
    assert payload["username"] == "alice"
    assert payload["role"] == "operator"


def test_token_tampered_body_rejected():
    token = security.create_token(7, "alice", "viewer")
    body, sig = token.split(".")
    forged = body[:-2] + ("ab" if not body.endswith("ab") else "cd") + "." + sig
    assert security.verify_token(forged) is None


def test_token_expired_rejected():
    token = security.create_token(7, "alice", "viewer", ttl=-10)
    assert security.verify_token(token) is None
