"""Data-access layer for the inventory database.

All persistence goes through these functions so the rest of the app never
touches SQLAlchemy directly.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from models import Credential, Device, ScanJob, Site


# ── Devices ───────────────────────────────────────────────────────────────────

def upsert_device(db: Session, data: dict, scan_id: str) -> Device:
    """Insert a device or update it (keyed on IP). Keeps first_seen on updates."""
    ip = data.get("ip", "")
    if not ip:
        raise ValueError("device requires an ip")

    device = db.query(Device).filter(Device.ip == ip).first()
    now = datetime.now(timezone.utc)
    if device is None:
        device = Device(ip=ip, first_seen=now)
        db.add(device)

    device.mac = data.get("mac", device.mac or "")
    device.hostname = data.get("hostname", device.hostname or "")
    device.vendor = data.get("vendor", device.vendor or "")
    device.model = data.get("model", device.model or "")
    device.device_type = data.get("device_type", device.device_type or "")
    device.confidence = data.get("confidence", device.confidence or 0)
    device.open_ports = data.get("open_ports", device.open_ports or [])
    device.snmp_community = data.get("snmp_community", device.snmp_community or "")
    device.site = data.get("site", device.site or "")
    device.last_scan_id = scan_id
    device.last_seen = now
    db.commit()
    db.refresh(device)
    return device


def list_devices(db: Session, device_type: str | None = None, vendor: str | None = None,
                 site: str | None = None, limit: int = 200) -> list[Device]:
    query = db.query(Device)
    if device_type:
        query = query.filter(Device.device_type == device_type)
    if vendor:
        query = query.filter(Device.vendor.ilike(f"%{vendor}%"))
    if site:
        query = query.filter(Device.site == site)
    return query.order_by(Device.last_seen.desc()).limit(limit).all()


def get_device(db: Session, device_id: int) -> Device | None:
    return db.get(Device, device_id)


def device_counts(db: Session, column) -> dict:
    rows = (
        db.query(column, func.count(Device.id))
        .group_by(column)
        .order_by(func.count(Device.id).desc())
        .all()
    )
    return {k or "unknown": v for k, v in rows}


# ── Scan jobs ─────────────────────────────────────────────────────────────────

def create_scan_job(db: Session, scan_id: str, subnet: str, communities: list[str],
                    exclude_pcs: bool) -> ScanJob:
    job = ScanJob(id=scan_id, subnet=subnet, communities=communities, exclude_pcs=exclude_pcs)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def finish_scan_job(db: Session, scan_id: str, result: dict) -> ScanJob:
    job = db.get(ScanJob, scan_id)
    if job is None:
        raise KeyError(f"scan job {scan_id} not found")
    job.status = "completed"
    job.finished_at = datetime.now(timezone.utc)
    job.local_ip = result.get("local_ip", "")
    job.scanned_hosts = result.get("scanned_hosts", 0)
    job.alive_hosts = result.get("alive_hosts", 0)
    job.device_count = result.get("device_count", 0)
    job.snmp_identified = result.get("snmp_identified", 0)
    db.commit()
    db.refresh(job)
    return job


def fail_scan_job(db: Session, scan_id: str, error: str) -> ScanJob:
    job = db.get(ScanJob, scan_id)
    if job is None:
        raise KeyError(f"scan job {scan_id} not found")
    job.status = "failed"
    job.error = error
    job.finished_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(job)
    return job


def list_scan_jobs(db: Session, limit: int = 20) -> list[ScanJob]:
    return db.query(ScanJob).order_by(ScanJob.started_at.desc()).limit(limit).all()


# ── Credentials / Sites ───────────────────────────────────────────────────────

def create_credential(db: Session, name: str, credential_type: str = "snmp",
                      username: str = "", password: str = "", snmp_community: str = "",
                      site: str = "") -> Credential:
    cred = Credential(name=name, credential_type=credential_type, username=username,
                      password=password, snmp_community=snmp_community, site=site)
    db.add(cred)
    db.commit()
    db.refresh(cred)
    return cred


def list_credentials(db: Session) -> list[Credential]:
    return db.query(Credential).order_by(Credential.name).all()


def create_site(db: Session, name: str, location: str = "") -> Site:
    existing = db.query(Site).filter(Site.name == name).first()
    if existing:
        return existing
    site = Site(name=name, location=location)
    db.add(site)
    db.commit()
    db.refresh(site)
    return site


def list_sites(db: Session) -> list[Site]:
    return db.query(Site).order_by(Site.name).all()
