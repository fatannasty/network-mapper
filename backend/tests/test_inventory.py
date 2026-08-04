"""Sprint 2: inventory persistence (Devices, ScanJobs) via the API + repositories."""

from fastapi.testclient import TestClient

import repositories
from database import SessionLocal
from main import app

client = TestClient(app)


def _run_discovery(site=None):
    body = {"subnet": "127.0.0.1/32", "communities": ["public"], "exclude_pcs": False}
    if site:
        body["site"] = site
    return client.post("/api/discover", json=body)


# ── API persistence ───────────────────────────────────────────────────────────

def test_discover_persists_scan_job_and_device():
    resp = _run_discovery()
    assert resp.status_code == 200
    scan_id = resp.json()["scan_id"]

    scans = client.get("/api/inventory/scans").json()["scans"]
    assert any(s["id"] == scan_id and s["status"] == "completed" for s in scans)

    devices = client.get("/api/inventory/devices").json()["devices"]
    assert any(d["ip"] == "127.0.0.1" for d in devices)


def test_device_has_last_seen_and_first_seen():
    _run_discovery()
    devices = client.get("/api/inventory/devices").json()["devices"]
    dev = next(d for d in devices if d["ip"] == "127.0.0.1")
    assert dev["first_seen"] and dev["last_seen"]
    assert dev["last_scan_id"]


def test_upsert_keyed_on_ip():
    first = _run_discovery().json()
    second = _run_discovery().json()
    assert first["scan_id"] != second["scan_id"]
    devices = client.get("/api/inventory/devices").json()["devices"]
    loopbacks = [d for d in devices if d["ip"] == "127.0.0.1"]
    assert len(loopbacks) == 1  # upsert, not duplicate
    assert loopbacks[0]["first_seen"] <= loopbacks[0]["last_seen"]


def test_site_attribute_persisted():
    _run_discovery(site="Miami Station")
    devices = client.get("/api/inventory/devices", params={"site": "Miami Station"}).json()["devices"]
    assert all(d["site"] == "Miami Station" for d in devices)


def test_inventory_filters():
    _run_discovery()
    resp = client.get("/api/inventory/devices", params={"vendor": "ZZZ-none"}).json()
    assert resp["count"] == 0


def test_inventory_report_shape():
    _run_discovery()
    report = client.get("/api/inventory/report").json()
    assert "total_devices" in report
    assert "by_device_type" in report
    assert "by_vendor" in report
    assert "by_site" in report
    assert "recent_scans" in report


def test_inventory_device_not_found():
    assert client.get("/api/inventory/devices/99999").status_code == 404


# ── Repository upsert semantics ───────────────────────────────────────────────

def test_upsert_preserves_first_seen_updates_last_seen():
    with SessionLocal() as db:
        r1 = repositories.upsert_device(db, {
            "ip": "10.0.0.1", "hostname": "sw1", "device_type": "switch", "vendor": "Cisco",
        }, scan_id="scan-a")
        first = r1.first_seen
        import time
        time.sleep(0.01)
        r2 = repositories.upsert_device(db, {
            "ip": "10.0.0.1", "hostname": "sw1-core", "device_type": "core-switch", "vendor": "Cisco",
        }, scan_id="scan-b")
        assert r2.first_seen == first
        assert r2.hostname == "sw1-core"
        assert r2.device_type == "core-switch"
        assert r2.last_seen >= first


def test_upsert_requires_ip():
    with SessionLocal() as db:
        try:
            repositories.upsert_device(db, {"hostname": "x"}, scan_id="s")
            raise AssertionError("should have raised")
        except ValueError:
            pass


def test_scan_job_failure_path():
    with SessionLocal() as db:
        job = repositories.create_scan_job(db, "abcdef", "10.99.0.0/24", ["public"], True)
        repositories.fail_scan_job(db, "abcdef", "boom")
        from models import ScanJob
        assert db.get(ScanJob, "abcdef").status == "failed"
        assert db.get(ScanJob, "abcdef").error == "boom"
