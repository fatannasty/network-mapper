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


def test_topology_nodes_include_operational_status():
    """The topology payload must carry per-device up/down/degraded/unknown state."""
    import uuid
    from datetime import datetime

    from database import SessionLocal
    from models import Device, Interface, ScanJob

    scan_id = uuid.uuid4().hex[:12]
    with SessionLocal() as db:
        db.add(ScanJob(id=scan_id, subnet="10.7.7.0/24", status="completed",
                       device_count=2, finished_at=datetime.utcnow()))
        db.add(Device(ip="10.7.7.1", hostname="sw-down", model="C9300",
                      device_type="switch", last_scan_id=scan_id))
        db.add(Device(ip="10.7.7.2", hostname="sw-up", model="C9300",
                      device_type="switch", last_scan_id=scan_id))
        db.flush()
        for d, status in [("10.7.7.1", "down"), ("10.7.7.2", "up")]:
            dev = db.query(Device).filter(Device.ip == d).first()
            db.add(Interface(device_id=dev.id, if_name="Gi0/0", if_oper_status=status))
        db.commit()

    resp = admin.get("/api/topology", params={"scan_id": scan_id})
    assert resp.status_code == 200
    by_ip = {n["ip"]: n for n in resp.json()["nodes"]}
    assert by_ip["10.7.7.1"]["status"] == "down"
    assert by_ip["10.7.7.2"]["status"] == "up"


def test_topology_summary_groups_by_subnet():
    import uuid
    from datetime import datetime

    from database import SessionLocal
    from models import Device, ScanJob

    scan_id = uuid.uuid4().hex[:12]
    with SessionLocal() as db:
        db.add(ScanJob(id=scan_id, subnet="10.8.8.0/24", status="completed",
                       device_count=3, finished_at=datetime.utcnow()))
        db.add(Device(ip="10.8.8.1", hostname="core1", model="C9500-24Y4C",
                      device_type="switch", last_scan_id=scan_id))
        db.add(Device(ip="10.8.9.1", hostname="dist1", model="C9300X-24Y",
                      device_type="switch", last_scan_id=scan_id))
        db.add(Device(ip="10.8.9.2", hostname="dist2", model="C9300X-24Y",
                      device_type="switch", last_scan_id=scan_id))
        db.commit()

    resp = admin.get("/api/topology/summary", params={"scan_id": scan_id})
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("summary") is True
    ids = {n["id"] for n in data["nodes"]}
    assert "10.8.8.1" in ids             # core stays individual
    assert "subnet:10.8.9.0/24" in ids   # distribution collapsed into a block
    block = next(n for n in data["nodes"] if n["id"] == "subnet:10.8.9.0/24")
    assert block["device_count"] == 2


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
    assert resp.status_code == 200
    data = resp.json()
    assert "nodes" in data
    assert "links" in data


def test_topology_includes_velocloud_lan_links():
    """VeloCloud SD-WAN edges surface in topology via their LAN-side links."""
    from database import SessionLocal
    import repositories

    with SessionLocal() as db:
        repositories.create_scan_job(db, "topo-vc-scan", "10.0.0.0/24", ["public"], False)
        repositories.upsert_device(db, {
            "ip": "10.0.0.1", "hostname": "sw1", "vendor": "Cisco", "device_type": "switch",
        }, scan_id="topo-vc-scan")
        # Velocloud edge reachable via an inferred 'velocloud-lan' link.
        repositories.upsert_device(db, {
            "ip": "10.0.0.99", "hostname": "AMT-XX-VC1", "vendor": "VMware VeloCloud",
            "device_type": "velocloud-edge",
        }, scan_id="other-scan")
        repositories.replace_links(db, "topo-vc-scan", [
            {"source": "10.0.0.1", "target": "10.0.0.2",
             "source_interface": "Gi1/0/1", "target_interface": "Gi1/0/1",
             "protocol": "lldp", "source_hostname": "sw1", "target_hostname": "sw2"},
            {"source": "10.0.0.1", "target": "10.0.0.99",
             "source_interface": "GE1 (LAN)", "target_interface": "unknown",
             "protocol": "velocloud-lan", "source_hostname": "sw1", "target_hostname": ""},
            {"source": "10.0.0.99", "target": "203.0.113.1",
             "source_interface": "GE3", "target_interface": "",
             "protocol": "velocloud", "source_hostname": "", "target_hostname": ""},
        ])

    resp = admin.get("/api/topology", params={"scan_id": "topo-vc-scan"})
    assert resp.status_code == 200
    data = resp.json()
    node_ips = {n["id"] for n in data["nodes"]}
    assert "10.0.0.99" in node_ips  # edge now part of the topology
    protos = {l["protocol"] for l in data["links"]}
    assert "velocloud-lan" in protos  # LAN-side link shown
    assert "velocloud" not in protos  # WAN transport link still hidden


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
