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
