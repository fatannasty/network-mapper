"""Data-access layer for the inventory database.

All persistence goes through these functions so the rest of the app never
touches SQLAlchemy directly.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from models import Credential, Device, Interface, Link, ScanJob, Site, User
from security import create_token, hash_password, verify_password


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

    if "interfaces" in data:
        _sync_interfaces(db, device, data.get("interfaces") or [])

    db.commit()
    db.refresh(device)
    return device


def _sync_interfaces(db: Session, device: Device, interfaces: list[dict]) -> None:
    """Replace the device's interface rows with the freshly walked set."""
    existing = {row.if_index: row for row in device.interfaces}
    seen: set[str] = set()
    for iface in interfaces:
        idx = str(iface.get("ifIndex", ""))
        if not idx:
            continue
        seen.add(idx)
        row = existing.get(idx)
        if row is None:
            row = Interface(device_id=device.id, if_index=idx)
            db.add(row)
        row.if_descr = iface.get("ifDescr", "")
        row.if_name = iface.get("ifName", "")
        row.if_type = iface.get("ifType", "")
        row.if_speed = iface.get("ifSpeed", "")
        row.if_phys_address = iface.get("ifPhysAddress", "")
        row.if_admin_status = iface.get("ifAdminStatus", "")
        row.if_oper_status = iface.get("ifOperStatus", "")
        row.if_high_speed = iface.get("ifHighSpeed", "")
        row.if_alias = iface.get("ifAlias", "")
    for idx, row in existing.items():
        if idx not in seen:
            db.delete(row)


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

def replace_links(db: Session, scan_id: str, links: list[dict]) -> None:
    """Replace all links recorded for a scan with the freshly built set."""
    db.query(Link).filter(Link.scan_id == scan_id).delete()
    for link in links:
        db.add(Link(
            scan_id=scan_id,
            endpoint_a=link.get("source", ""),
            endpoint_b=link.get("target", ""),
            interface_a=link.get("source_interface", ""),
            interface_b=link.get("target_interface", ""),
            protocol=link.get("protocol", "lldp"),
            hostname_a=link.get("source_hostname", ""),
            hostname_b=link.get("target_hostname", ""),
        ))
    db.commit()


def list_links(db: Session, scan_id: str | None = None, limit: int = 500) -> list[Link]:
    query = db.query(Link)
    if scan_id:
        query = query.filter(Link.scan_id == scan_id)
    return query.order_by(Link.id).limit(limit).all()

def create_scan_job(db: Session, scan_id: str, subnet: str, communities: list[str],
                    exclude_pcs: bool, snmpv3_username: str = "") -> ScanJob:
    job = ScanJob(id=scan_id, subnet=subnet, communities=communities, exclude_pcs=exclude_pcs,
                  snmpv3_username=snmpv3_username)
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
    """Create a credential. password/snmp_community are encrypted at rest."""
    cred = Credential(name=name, credential_type=credential_type, username=username,
                      password=password, snmp_community=snmp_community, site=site)
    db.add(cred)
    db.commit()
    db.refresh(cred)
    return cred


def list_credentials(db: Session) -> list[Credential]:
    return db.query(Credential).order_by(Credential.name).all()


def delete_credential(db: Session, credential_id: int) -> bool:
    cred = db.get(Credential, credential_id)
    if cred is None:
        return False
    db.delete(cred)
    db.commit()
    return True


# ── Users ─────────────────────────────────────────────────────────────────────

def create_user(db: Session, username: str, password: str, role: str = "viewer") -> User:
    """Create an app user with a scrypt-hashed password."""
    from sqlalchemy.exc import IntegrityError

    user = User(username=username, password_hash=hash_password(password), role=role)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ValueError(f"username '{username}' already exists") from None
    db.refresh(user)
    return user


def list_users(db: Session) -> list[User]:
    return db.query(User).order_by(User.username).all()


def get_user(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def delete_user(db: Session, user_id: int) -> bool:
    user = db.get(User, user_id)
    if user is None:
        return False
    db.delete(user)
    db.commit()
    return True


def authenticate(db: Session, username: str, password: str) -> User | None:
    """Verify credentials and return the user, or None."""
    user = db.query(User).filter(User.username == username).first()
    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def issue_token(db: Session, username: str, password: str) -> dict | None:
    """Authenticate and return {token, role, username} or None on failure."""
    user = authenticate(db, username, password)
    if user is None:
        return None
    token = create_token(user.id, user.username, user.role)
    return {"token": token, "token_type": "bearer", "username": user.username, "role": user.role}


def get_user_by_token(token: str) -> dict | None:
    """Return the token payload if valid (no DB round-trip needed)."""
    from security import verify_token

    return verify_token(token)


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
