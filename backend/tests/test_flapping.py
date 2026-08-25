"""Reachability flapping detection (P1)."""

from datetime import datetime, timedelta, timezone

import repositories
from database import SessionLocal
from models import DeviceStatusHistory


def test_record_device_status_writes_transitions_only():
    with SessionLocal() as db:
        assert repositories.record_device_status(db, "10.1.1.1", "up") is True
        db.commit()
        assert repositories.record_device_status(db, "10.1.1.1", "up") is False  # unchanged
        assert repositories.record_device_status(db, "10.1.1.1", "down") is True
        db.commit()
        count = db.query(DeviceStatusHistory).filter(DeviceStatusHistory.ip == "10.1.1.1").count()
        assert count == 2  # up + down only; the duplicate "up" was not stored


def test_flapping_ips_detects_recent_oscillation():
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        # 10.2.2.2 oscillates 4x within the last few minutes -> flapping.
        for i, status in enumerate(["up", "down", "up", "down"]):
            db.add(DeviceStatusHistory(ip="10.2.2.2", status=status,
                                       observed_at=now - timedelta(minutes=i)))
        # 10.3.3.3 changed once -> not flapping.
        db.add(DeviceStatusHistory(ip="10.3.3.3", status="up",
                                   observed_at=now - timedelta(minutes=1)))
        # 10.4.4.4 flapped 4x but an hour ago -> outside the window.
        for i, status in enumerate(["up", "down", "up", "down"]):
            db.add(DeviceStatusHistory(ip="10.4.4.4", status=status,
                                       observed_at=now - timedelta(hours=1, minutes=i)))
        db.commit()

        flapping = repositories.flapping_ips(db, window_minutes=10, threshold=3)
        assert "10.2.2.2" in flapping
        assert "10.3.3.3" not in flapping
        assert "10.4.4.4" not in flapping


def test_measure_latency_pass_records_status(monkeypatch):
    """The poll pass updates latency and records reachability transitions."""
    import main
    from models import Device

    with SessionLocal() as db:
        db.add(Device(ip="10.6.6.1", hostname="sw1", model="C9300", device_type="switch"))
        db.add(Device(ip="10.6.6.2", hostname="sw2", model="C9300", device_type="switch"))
        db.commit()

    monkeypatch.setattr(
        main.scanner, "measure_latencies",
        lambda ips: {ip: (10.0 if ip == "10.6.6.1" else None) for ip in ips},
    )

    with SessionLocal() as db:
        devices = db.query(Device).filter(Device.ip.in_(["10.6.6.1", "10.6.6.2"])).all()
        measured, updated = main._measure_latency_pass(db, devices)
        db.commit()

    assert measured == 2
    assert updated == 1  # only 10.6.6.1 returned a latency

    with SessionLocal() as db:
        d1 = db.query(Device).filter(Device.ip == "10.6.6.1").first()
        d2 = db.query(Device).filter(Device.ip == "10.6.6.2").first()
        assert d1.latency_ms == 10.0
        assert d1.latency_checked_at is not None
        assert d2.latency_checked_at is None

        hist = {r.ip: r.status for r in db.query(DeviceStatusHistory)
                .filter(DeviceStatusHistory.ip.in_(["10.6.6.1", "10.6.6.2"])).all()}
        assert hist["10.6.6.1"] == "up"
        assert hist["10.6.6.2"] == "down"



def test_alert_check_creates_notifications(monkeypatch):
    from database import SessionLocal
    from models import Device, Interface, Notification
    import alerts, repositories

    with SessionLocal() as db:
        db.query(Notification).delete()
        db.query(Device).filter(Device.site == "AlertSite").delete()
        d = Device(ip="10.9.0.77", hostname="SW-ALERT", device_type="switch", site="AlertSite")
        db.add(d)
        db.flush()
        db.add(Interface(device_id=d.id, if_name="Gi1", if_oper_status="down"))
        db.commit()

    with SessionLocal() as db:
        # flapping_ips sees it as flapping + status is down → both alerts.
        monkeypatch.setattr(repositories, "flapping_ips", lambda db: {"10.9.0.77"})
        res = alerts.run_alert_check(db)
    assert res["created"] >= 1

    from conftest import make_client
    client = make_client("admin")
    data = client.get("/api/notifications").json()
    assert data["unseen"] >= 1
    assert any(n["device_ip"] == "10.9.0.77" for n in data["notifications"])

    # Mark the newest as seen.
    nid = next(n["id"] for n in data["notifications"] if n["device_ip"] == "10.9.0.77")
    assert client.post(f"/api/notifications/{nid}/seen").json()["seen"] is True

    # Cooldown prevents duplicate alerts on a second check.
    with SessionLocal() as db:
        res2 = alerts.run_alert_check(db)
    assert res2["created"] == 0


def test_spof_alert_is_aggregate_and_deduplicated(monkeypatch):
    from database import SessionLocal
    from models import Device, Link, Notification
    from path_tracer import articulation_points
    import alerts

    with SessionLocal() as db:
        db.query(Notification).filter(Notification.kind == "spof").delete()
        db.query(Link).filter(Link.scan_id == "spof-scan").delete()
        db.query(Device).filter(Device.site == "SpofSite").delete()
        # A simple graph where the middle device is a SPOF.
        for i, ip in enumerate(["10.10.0.1", "10.10.0.2", "10.10.0.3"]):
            db.add(Device(ip=ip, hostname=f"S{i}", device_type="switch", site="SpofSite"))
        db.flush()
        db.add_all([
            Link(scan_id="spof-scan", endpoint_a="10.10.0.1", endpoint_b="10.10.0.2", protocol="lldp"),
            Link(scan_id="spof-scan", endpoint_a="10.10.0.2", endpoint_b="10.10.0.3", protocol="lldp"),
        ])
        db.commit()

    with SessionLocal() as db:
        res = alerts.run_alert_check(db)
    assert res["spof"] == 1

    from conftest import make_client
    client = make_client("admin")
    notes = client.get("/api/notifications", params={"limit": 100}).json()["notifications"]
    spof = [n for n in notes if n["kind"] == "spof"]
    assert len(spof) == 1  # aggregate, not one per device
    assert "1 single point of failure" in spof[0]["message"]

    # Same count again -> no new advisory.
    with SessionLocal() as db:
        res2 = alerts.run_alert_check(db)
    assert res2["spof"] == 0
