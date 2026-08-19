"""Data-hygiene startup migrations: model dedupe + stale running-scan cleanup."""

from datetime import datetime, timedelta

import database
from database import SessionLocal
from models import Device, ScanJob


def test_model_dedupe_and_stale_scan_fail():
    with SessionLocal() as db:
        db.add(Device(ip="10.9.9.1", hostname="dup", model="C9300L-24P-4X, C9300L-24P-4X",
                      device_type="switch"))
        db.add(Device(ip="10.9.9.2", hostname="printer", model="HP X,SN:ABC,FN:DEF",
                      device_type="printer"))
        db.add(ScanJob(id="stalejob1", subnet="test", status="running",
                       started_at=datetime.utcnow() - timedelta(days=2)))
        db.add(ScanJob(id="freshjob1", subnet="test", status="running",
                       started_at=datetime.utcnow()))
        db.commit()

    database._run_migrations()

    with SessionLocal() as db:
        dup = db.query(Device).filter(Device.ip == "10.9.9.1").first()
        printer = db.query(Device).filter(Device.ip == "10.9.9.2").first()
        stale = db.query(ScanJob).filter(ScanJob.id == "stalejob1").first()
        fresh = db.query(ScanJob).filter(ScanJob.id == "freshjob1").first()

    assert dup.model == "C9300L-24P-4X"          # exact duplicate collapsed
    assert printer.model == "HP X,SN:ABC,FN:DEF"  # no duplicates -> untouched
    assert stale.status == "failed"               # stale run auto-failed
    assert fresh.status == "running"              # fresh run untouched
