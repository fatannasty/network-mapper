"""API tests for the FastAPI app (via TestClient)."""

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_discover_loopback():
    resp = client.post("/api/discover", json={
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
    resp = client.post("/api/discover", json={"subnet": "bogus"})
    assert resp.status_code == 400
