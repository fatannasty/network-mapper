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


# ── Topology (Sprint 5) ───────────────────────────────────────────────────────

def test_topology_shared_db_has_previous_data():
    resp = admin.get("/api/topology")
    assert resp.status_code == 200
    data = resp.json()
    assert "scan_id" in data
    assert "nodes" in data
    assert "links" in data
    assert isinstance(data["nodes"], list)
    assert isinstance(data["links"], list)


def test_topology_with_seeded_data():
    from database import SessionLocal
    import repositories

    with SessionLocal() as db:
        repositories.create_scan_job(db, "topo-scan", "10.0.0.0/24", ["public"], False)
        repositories.upsert_device(db, {
            "ip": "10.0.0.1", "hostname": "sw1", "vendor": "Cisco", "device_type": "switch",
        }, scan_id="topo-scan")
        repositories.replace_links(db, "topo-scan", [{
            "source": "10.0.0.1", "target": "10.0.0.2",
            "source_interface": "Gi1/0/1", "target_interface": "Gi1/0/1",
            "protocol": "lldp", "source_hostname": "sw1", "target_hostname": "sw2",
        }])

    resp = admin.get("/api/topology", params={"scan_id": "topo-scan"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["scan_id"] == "topo-scan"
    node_ips = {n["id"] for n in data["nodes"]}
    assert node_ips == {"10.0.0.1", "10.0.0.2"}
    assert len(data["links"]) == 1
    assert data["links"][0]["protocol"] == "lldp"
    assert data["links"][0]["source"] == "10.0.0.1"
    assert data["links"][0]["target"] == "10.0.0.2"


def test_topology_scan_not_found():
    resp = admin.get("/api/topology", params={"scan_id": "nonexistent"})
    assert resp.status_code == 404


def test_topology_after_discover():
    resp = admin.post("/api/discover", json={
        "subnet": "127.0.0.1/32", "communities": ["public"], "exclude_pcs": False,
    })
    assert resp.status_code == 200
    scan_id = resp.json()["scan_id"]

    topo = admin.get("/api/topology", params={"scan_id": scan_id}).json()
    assert topo["scan_id"] == scan_id
    node_ips = {n["id"] for n in topo["nodes"]}
    assert "127.0.0.1" in node_ips
    assert "connections" not in topo
    assert "links" in topo
