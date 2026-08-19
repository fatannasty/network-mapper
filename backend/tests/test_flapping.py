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

