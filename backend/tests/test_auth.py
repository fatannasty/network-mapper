"""Sprint 3: RBAC - login, tokens, and role-based access control."""

from conftest import make_client, public_client

admin = make_client("admin")
operator = make_client("operator")
viewer = make_client("viewer")


# ── Login ─────────────────────────────────────────────────────────────────────

def test_login_success_returns_token():
    resp = public_client().post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["token"]
    assert data["role"] == "admin"
    assert data["token_type"] == "bearer"


def test_login_wrong_password():
    resp = public_client().post("/api/auth/login", json={"username": "admin", "password": "nope"})
    assert resp.status_code == 401


def test_login_unknown_user():
    resp = public_client().post("/api/auth/login", json={"username": "ghost", "password": "x"})
    assert resp.status_code == 401


def test_auth_me_with_token():
    resp = admin.get("/api/auth/me")
    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"


# ── Role enforcement ──────────────────────────────────────────────────────────

def test_viewer_cannot_run_discovery():
    resp = viewer.post("/api/discover", json={"subnet": "127.0.0.1/32"})
    assert resp.status_code == 403


def test_operator_can_run_discovery():
    resp = operator.post("/api/discover", json={"subnet": "127.0.0.1/32", "exclude_pcs": False})
    assert resp.status_code == 200


def test_viewer_can_read_inventory():
    assert viewer.get("/api/inventory/devices").status_code == 200
    assert viewer.get("/api/inventory/report").status_code == 200


def test_viewer_cannot_create_credential():
    resp = viewer.post("/api/inventory/credentials", json={"name": "c1", "snmp_community": "public"})
    assert resp.status_code == 403


def test_operator_cannot_create_credential():
    resp = operator.post("/api/inventory/credentials", json={"name": "c1", "snmp_community": "public"})
    assert resp.status_code == 403


def test_operator_cannot_manage_users():
    resp = operator.post("/api/auth/users", json={"username": "u1", "password": "pw", "role": "viewer"})
    assert resp.status_code == 403


def test_invalid_token_rejected():
    client = public_client()
    client.headers.update({"Authorization": "Bearer not-a-real-token"})
    assert client.get("/api/inventory/devices").status_code == 401


# ── User management (admin only) ─────────────────────────────────────────────

def test_admin_creates_lists_deletes_user():
    created = admin.post("/api/auth/users",
                         json={"username": "alice", "password": "pw123", "role": "operator"})
    assert created.status_code == 200
    assert created.json()["role"] == "operator"
    assert "password" not in created.json()

    listing = admin.get("/api/auth/users").json()
    assert any(u["username"] == "alice" for u in listing["users"])

    user_id = next(u["id"] for u in listing["users"] if u["username"] == "alice")
    deleted = admin.delete(f"/api/auth/users/{user_id}")
    assert deleted.status_code == 200


def test_duplicate_user_conflict():
    resp = admin.post("/api/auth/users", json={"username": "viewer", "password": "x", "role": "viewer"})
    assert resp.status_code == 409


def test_login_as_created_user():
    admin.post("/api/auth/users", json={"username": "bob", "password": "pw456", "role": "viewer"})
    resp = public_client().post("/api/auth/login", json={"username": "bob", "password": "pw456"})
    assert resp.status_code == 200
    assert resp.json()["role"] == "viewer"
