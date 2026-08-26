"""Sprint 2: inventory persistence (Devices, ScanJobs) via the API + repositories."""

import pytest

from conftest import make_client

import repositories
import scanner
from database import SessionLocal

client = make_client("admin")


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


# ── Interface persistence (Sprint 4) ──────────────────────────────────────────

_INTERFACES = [
    {"ifIndex": "1", "ifDescr": "eth0", "ifName": "eth0", "ifType": "ethernet",
     "ifSpeed": "1000", "ifPhysAddress": "00:11:22:33:44:55",
     "ifAdminStatus": "up", "ifOperStatus": "up", "ifHighSpeed": "1000", "ifAlias": ""},
    {"ifIndex": "2", "ifDescr": "eth1", "ifName": "eth1", "ifType": "ethernet",
     "ifSpeed": "1000", "ifPhysAddress": "66:77:88:99:aa:bb",
     "ifAdminStatus": "up", "ifOperStatus": "up", "ifHighSpeed": "1000", "ifAlias": "uplink"},
]


def test_interfaces_persisted_with_device():
    with SessionLocal() as db:
        device = repositories.upsert_device(db, {
            "ip": "10.0.0.5", "hostname": "sw5", "vendor": "Cisco", "device_type": "switch",
            "snmp_identified": True, "interfaces": _INTERFACES,
        }, scan_id="scan-if-a")
        assert len(device.interfaces) == 2
        by_index = {i.if_index: i for i in device.interfaces}
        assert by_index["1"].if_descr == "eth0"
        assert by_index["1"].if_phys_address == "00:11:22:33:44:55"
        assert by_index["2"].if_alias == "uplink"


def test_interfaces_synced_on_rescan():
    with SessionLocal() as db:
        repositories.upsert_device(db, {
            "ip": "10.0.0.5", "hostname": "sw5", "vendor": "Cisco", "device_type": "switch",
            "snmp_identified": True, "interfaces": _INTERFACES,
        }, scan_id="scan-if-a")
        device = repositories.upsert_device(db, {
            "ip": "10.0.0.5", "hostname": "sw5", "vendor": "Cisco", "device_type": "switch",
            "snmp_identified": True,
            "interfaces": [{"ifIndex": "1", "ifDescr": "eth0", "ifType": "ethernet"}],
        }, scan_id="scan-if-b")
        assert len(device.interfaces) == 1
        assert device.interfaces[0].if_index == "1"
        assert device.interfaces[0].if_alias == ""


def test_interfaces_preserved_when_rescan_not_identified():
    with SessionLocal() as db:
        repositories.upsert_device(db, {
            "ip": "10.0.0.5", "hostname": "sw5", "vendor": "Cisco", "device_type": "switch",
            "snmp_identified": True, "interfaces": _INTERFACES,
        }, scan_id="scan-if-a")
        device = repositories.upsert_device(db, {
            "ip": "10.0.0.5", "hostname": "", "vendor": "", "device_type": "",
            "snmp_identified": False, "interfaces": [],
        }, scan_id="scan-if-b")
        assert len(device.interfaces) == 2  # not wiped by an unidentified rescan


def test_upsert_preserves_identity_when_rescan_returns_blank():
    with SessionLocal() as db:
        repositories.upsert_device(db, {
            "ip": "10.0.0.7", "hostname": "sw7", "vendor": "Cisco",
            "model": "C9300L-24P-4G", "device_type": "switch", "confidence": 5,
        }, scan_id="scan-a")
        device = repositories.upsert_device(db, {
            "ip": "10.0.0.7", "hostname": "", "vendor": "", "model": "",
            "device_type": "", "confidence": 0,
        }, scan_id="scan-b")
        assert device.hostname == "sw7"
        assert device.vendor == "Cisco"
        assert device.model == "C9300L-24P-4G"
        assert device.device_type == "switch"
        assert device.confidence == 5
        assert device.last_scan_id == "scan-b"


def test_device_to_dict_includes_interfaces():
    with SessionLocal() as db:
        device = repositories.upsert_device(db, {
            "ip": "10.0.0.5", "hostname": "sw5", "vendor": "Cisco", "device_type": "switch",
            "snmp_identified": True, "interfaces": _INTERFACES,
        }, scan_id="scan-if-a")
        data = device.to_dict()
        assert len(data["interfaces"]) == 2
        assert data["interfaces"][0]["ifDescr"] == "eth0"


# ── Latency persistence (RTT) ────────────────────────────────────────────────

def test_upsert_device_persists_latency():
    with SessionLocal() as db:
        device = repositories.upsert_device(db, {
            "ip": "10.0.0.9", "hostname": "sw9", "device_type": "switch",
            "latency_ms": 3.21,
        }, scan_id="scan-lat")
        assert device.latency_ms == pytest.approx(3.21)
        assert device.latency_checked_at is not None
        assert device.to_dict()["latency_ms"] == pytest.approx(3.21)


def test_measure_latency_endpoint(monkeypatch):
    _run_discovery()
    monkeypatch.setattr(scanner, "measure_latencies", lambda ips: {ip: 4.5 for ip in ips})
    resp = client.post("/api/inventory/measure-latency")
    assert resp.status_code == 200
    assert resp.json()["updated"] >= 1
    devices = client.get("/api/inventory/devices").json()["devices"]
    dev = next(d for d in devices if d["ip"] == "127.0.0.1")
    assert dev["latency_ms"] == pytest.approx(4.5)
    assert dev["latency_checked_at"]


# ── Link persistence (Sprint 5) ───────────────────────────────────────────────

_LINKS = [
    {"source": "10.0.0.1", "target": "10.0.0.2", "source_interface": "Gi1/0/1",
     "target_interface": "Gi1/0/1", "protocol": "lldp",
     "source_hostname": "sw1", "target_hostname": "sw2"},
    {"source": "10.0.0.1", "target": "10.0.0.3", "source_interface": "Gi1/0/2",
     "target_interface": "Eth1/0/24", "protocol": "cdp",
     "source_hostname": "sw1", "target_hostname": "sw3"},
]


def test_replace_links_and_list_links_roundtrip():
    with SessionLocal() as db:
        repositories.replace_links(db, "scan-links-a", _LINKS)
        links = repositories.list_links(db, scan_id="scan-links-a")
        assert len(links) == 2
        protos = {l.protocol for l in links}
        assert protos == {"lldp", "cdp"}
        l = next(ll for ll in links if ll.protocol == "lldp")
        assert l.endpoint_a == "10.0.0.1"
        assert l.endpoint_b == "10.0.0.2"
        assert l.interface_a == "Gi1/0/1"
        assert l.hostname_a == "sw1"
        assert l.hostname_b == "sw2"


def test_replace_links_overwrites_previous_scan():
    with SessionLocal() as db:
        repositories.replace_links(db, "scan-links-a", _LINKS)
        repositories.replace_links(db, "scan-links-a", _LINKS[:1])
        links = repositories.list_links(db, scan_id="scan-links-a")
        assert len(links) == 1
        assert links[0].endpoint_b == "10.0.0.2"


def test_list_links_defaults_without_scan_id():
    with SessionLocal() as db:
        repositories.replace_links(db, "scan-links-a", _LINKS)
        repositories.replace_links(db, "scan-links-b", _LINKS[:1])
        links = repositories.list_links(db)
        assert len(links) >= 3


def test_bulk_ops_ips_and_set_site():
    from conftest import make_client
    from database import SessionLocal
    from models import Device

    with SessionLocal() as db:
        db.query(Device).filter(Device.site == "BulkSite").delete()
        d1 = Device(ip="10.7.0.1", hostname="B1", device_type="switch", site="")
        d2 = Device(ip="10.7.0.2", hostname="B2", device_type="switch", site="")
        db.add_all([d1, d2])
        db.commit()

    client = make_client("admin")
    # bulk set-site
    r = client.post("/api/inventory/bulk-set-site",
                    json={"ips": ["10.7.0.1", "10.7.0.2"], "site": "BulkSite"})
    assert r.status_code == 200 and r.json()["updated"] == 2

    # backfill interfaces scoped by IP list (uses vault communities; walk mocked away)
    import backfill as backfill_mod
    import unittest.mock as mock
    with mock.patch.object(backfill_mod, "walk_device_interfaces",
                           return_value=({"id": 1, "ip": "10.7.0.1"}, [], "")):
        resp = client.post("/api/backfill/interfaces", json={"ips": ["10.7.0.1"]})
    assert resp.status_code == 200
    assert resp.json()["total"] == 1

    with SessionLocal() as db:
        assert db.query(Device).filter(Device.site == "BulkSite").count() == 2


def test_utilization_series_and_pass(monkeypatch):
    from conftest import make_client
    from database import SessionLocal
    from models import Device, InterfaceUtilization
    from datetime import datetime, timedelta

    with SessionLocal() as db:
        db.query(InterfaceUtilization).delete()
        db.query(Device).filter(Device.site == "UtilSite").delete()
        d = Device(ip="10.8.0.1", hostname="SW-UTIL", device_type="switch", site="UtilSite")
        db.add(d)
        db.flush()
        # Two samples for Gi1 to seed a delta (10 Mbps in / 5 Mbps out).
        t0 = datetime.utcnow() - timedelta(minutes=5)
        db.add(InterfaceUtilization(device_id=d.id, if_index="1", if_name="Gi1",
                                    in_octets=0, out_octets=0, sampled_at=t0))
        db.commit()
        dev_id = d.id

    client = make_client("admin")
    resp = client.get(f"/api/inventory/devices/{dev_id}/utilization")
    assert resp.status_code == 200

    # A second sample 5 minutes later → rates derived from the delta.
    import utilization
    from snmp import walk_if_table as _orig
    def fake_walk(ip, communities, port=None, timeout=None, max_oids=2048):
        return [{"ifIndex": "1", "ifName": "Gi1", "ifHighSpeed": "1000",
                 "ifHCInOctets": "37500000", "ifHCOutOctets": "18750000"}]
    monkeypatch.setattr(utilization, "_walk_v2c", fake_walk)
    with SessionLocal() as db:
        res = utilization.run_utilization_pass(db, ["public"])
    assert res["samples_added"] >= 1

    resp = client.get(f"/api/inventory/devices/{dev_id}/utilization")
    data = resp.json()
    assert len(data["interfaces"]) >= 1
    series = data["interfaces"][0]["series"]
    last = series[-1]
    assert last["in_rate"] > 0 and last["out_rate"] > 0  # ~10 Mbps / ~5 Mbps

    top = client.get("/api/utilization/top", params={"days": 1}).json()
    assert any(t["ip"] == "10.8.0.1" for t in top["top"])


def test_scheduled_config_pass_search_and_health_history(monkeypatch):
    from conftest import make_client
    from database import SessionLocal
    from models import Device, DeviceConfig, HealthSnapshot
    import main

    with SessionLocal() as db:
        db.query(Device).filter(Device.site == "OpsSite").delete()
        db.add(Device(ip="10.11.0.1", hostname="CORE-ATLANTIC-1", device_type="core-switch", site="OpsSite"))
        db.add(Device(ip="10.11.0.2", hostname="SW-ATLANTIC-2", device_type="switch", site="OpsSite"))
        db.commit()

    # Search endpoint.
    client = make_client("admin")
    r = client.get("/api/search", params={"q": "atlantic"})
    assert r.status_code == 200
    data = r.json()
    assert any(d["ip"] == "10.11.0.1" for d in data["devices"])
    # The site name matches a different term.
    r2 = client.get("/api/search", params={"q": "ops"})
    assert "OpsSite" in r2.json()["sites"]

    # Scheduled config pass picks devices and (mock) collects.
    from unittest import mock
    with mock.patch("main._collect_configs", return_value={"total": 2, "success": 2, "failed": 0, "results": []}):
        with SessionLocal() as db:
            res = main._run_config_collect_pass()
    assert res["total"] == 2

    # Health history snapshot + endpoint.
    with SessionLocal() as db:
        main._record_health_snapshot()
    h = client.get("/api/health/history").json()
    assert len(h["points"]) >= 1
    assert "score" in h["points"][0]

    with SessionLocal() as db:
        db.query(HealthSnapshot).delete()
        db.query(Device).filter(Device.site == "OpsSite").delete()
        db.commit()
