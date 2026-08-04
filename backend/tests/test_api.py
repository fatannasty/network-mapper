"""API tests for the FastAPI app (via TestClient)."""

from conftest import make_client, public_client

admin = make_client("admin")


def test_health_is_public():
    resp = public_client().get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_discover_loopback():
    resp = admin.post("/api/discover", json={
        "subnet": "127.0.0.1/32",
        "communities": ["public"],
        "exclude_pcs": False,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["scan_id"]
    assert data["alive_hosts"] == 1
    assert "devices" in data
    assert "connections" in data


def test_discover_invalid_cidr():
    resp = admin.post("/api/discover", json={"subnet": "bogus"})
    assert resp.status_code == 400


def test_discover_requires_auth():
    resp = public_client().post("/api/discover", json={"subnet": "127.0.0.1/32"})
    assert resp.status_code == 401


def test_inventory_requires_auth():
    resp = public_client().get("/api/inventory/devices")
    assert resp.status_code == 401
