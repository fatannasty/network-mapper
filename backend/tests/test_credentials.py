"""Sprint 3: encrypted credential storage via the API and repositories."""

from conftest import make_client

import repositories
from database import SessionLocal
from models import Credential

admin = make_client("admin")


def test_create_credential_round_trip():
    resp = admin.post("/api/inventory/credentials", json={
        "name": "core-switches",
        "credential_type": "snmp",
        "username": "snmp-ro",
        "password": "s3cret!",
        "snmp_community": "comm-public",
        "site": "Miami Station",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "core-switches"
    assert data["username"] == "snmp-ro"
    assert "password" not in data
    assert "snmp_community" not in data


def test_list_credentials_never_leaks_secrets():
    admin.post("/api/inventory/credentials",
               json={"name": "leak-check", "password": "p@ss", "snmp_community": "comm-secret"})
    body = admin.get("/api/inventory/credentials").json()
    cred = next(c for c in body["credentials"] if c["name"] == "leak-check")
    assert "password" not in cred
    assert "snmp_community" not in cred
    assert "p@ss" not in str(body)


def test_credential_encrypted_at_rest():
    with SessionLocal() as db:
        repositories.create_credential(db, "at-rest", username="u", password="plaintextpw",
                                       snmp_community="comm-public")
    # Query the raw column values (TypeDecorator decrypts on result, so read via SQL).
    with SessionLocal() as db:
        from sqlalchemy import text
        rows = db.execute(text(
            "SELECT password, snmp_community FROM credentials WHERE name='at-rest'"
        )).fetchone()
    assert rows[0].startswith("enc:v1:")
    assert "plaintextpw" not in rows[0]
    assert rows[1].startswith("enc:v1:")


def test_credential_decrypts_through_repository():
    with SessionLocal() as db:
        repositories.create_credential(db, "decrypt-check", snmp_community="comm-public")
        cred = db.query(Credential).filter(Credential.name == "decrypt-check").first()
        assert cred.snmp_community == "comm-public"  # decrypted transparently


def test_delete_credential():
    with SessionLocal() as db:
        cred = repositories.create_credential(db, "to-delete", snmp_community="public")
        cred_id = cred.id
    resp = admin.delete(f"/api/inventory/credentials/{cred_id}")
    assert resp.status_code == 200
    with SessionLocal() as db:
        assert db.get(Credential, cred_id) is None


def test_delete_missing_credential_404():
    assert admin.delete("/api/inventory/credentials/99999").status_code == 404


def test_duplicate_credential_conflict():
    admin.post("/api/inventory/credentials", json={"name": "dup-check"})
    resp = admin.post("/api/inventory/credentials", json={"name": "dup-check"})
    assert resp.status_code == 409
