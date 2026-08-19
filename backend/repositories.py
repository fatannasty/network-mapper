"""Data-access layer for the inventory database.

All persistence goes through these functions so the rest of the app never
touches SQLAlchemy directly.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from models import Credential, Device, DeviceConfig, DeviceStatusHistory, Interface, Link, ScanJob, Site, SiteMapping, User
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
    # Identity fields are only ever overwritten with non-empty values so a
    # rescan that cannot identify a device (e.g. wrong SNMP community) does
    # not wipe out previously known hostname/vendor/model/type.
    device.hostname = data.get("hostname") or device.hostname
    device.vendor = data.get("vendor") or device.vendor
    device.model = data.get("model") or device.model
    device.device_type = data.get("device_type") or device.device_type
    device.confidence = data.get("confidence") or device.confidence
    device.open_ports = data.get("open_ports", device.open_ports or [])
    device.snmp_community = data.get("snmp_community") or device.snmp_community
    device.site = data.get("site", device.site or "")
    device.catalyst_id = data.get("catalyst_id") or data.get("_id") or device.catalyst_id
    device.last_scan_id = scan_id
    device.last_seen = now
    if data.get("latency_ms") is not None:
        device.latency_ms = data["latency_ms"]
        device.latency_checked_at = now
    db.commit()
    db.refresh(device)

    if data.get("snmp_identified") and "interfaces" in data:
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
                 site: str | None = None, search: str | None = None,
                 limit: int = 200) -> list[Device]:
    from sqlalchemy import or_
    query = db.query(Device)
    if device_type:
        query = query.filter(Device.device_type == device_type)
    if vendor:
        query = query.filter(Device.vendor.ilike(f"%{vendor}%"))
    if site:
        query = query.filter(Device.site == site)
    if search:
        pat = f"%{search}%"
        query = query.filter(or_(
            Device.hostname.ilike(pat),
            Device.ip.ilike(pat),
            Device.vendor.ilike(pat),
            Device.model.ilike(pat),
        ))
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


def record_device_status(db: Session, ip: str, status: str) -> bool:
    """Record a reachability transition for a device.

    Returns True only when a new row was written (i.e. the status changed from
    the previously recorded value), so the table stores transitions only.
    """
    last = (
        db.query(DeviceStatusHistory)
        .filter(DeviceStatusHistory.ip == ip)
        .order_by(DeviceStatusHistory.id.desc())
        .first()
    )
    if last is not None and last.status == status:
        return False
    db.add(DeviceStatusHistory(ip=ip, status=status))
    return True


def flapping_ips(db: Session, window_minutes: int = 10, threshold: int = 3) -> set[str]:
    """Return the IPs that have been flapping (>= threshold up/down transitions
    within the last `window_minutes`)."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
    rows = (
        db.query(DeviceStatusHistory.ip, func.count(DeviceStatusHistory.id))
        .filter(DeviceStatusHistory.observed_at >= cutoff)
        .group_by(DeviceStatusHistory.ip)
        .having(func.count(DeviceStatusHistory.id) >= threshold)
        .all()
    )
    return {ip for ip, _ in rows}


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


def list_links(db: Session, scan_id: str | None = None, limit: int = 5000) -> list[Link]:
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


def get_diagram_prefs(db: Session, scan_id: str) -> dict:
    job = db.query(ScanJob).filter(ScanJob.id == scan_id).first()
    if not job:
        return {"topology": "auto", "link_detail": "full"}
    return {
        "topology": job.diagram_topology or "auto",
        "link_detail": job.diagram_link_detail or "full",
    }


def set_diagram_prefs(db: Session, scan_id: str, topology: str, link_detail: str) -> bool:
    job = db.query(ScanJob).filter(ScanJob.id == scan_id).first()
    if not job:
        return False
    job.diagram_topology = topology
    job.diagram_link_detail = link_detail
    db.commit()
    return True


def count_links(db: Session) -> int:
    return db.query(func.count(Link.id)).scalar() or 0


def count_interfaces(db: Session) -> int:
    from models import Interface
    return db.query(func.count(Interface.id)).scalar() or 0


def link_counts_by_protocol(db: Session) -> dict:
    rows = db.query(Link.protocol, func.count(Link.id)).group_by(Link.protocol).all()
    return {p or "unknown": c for p, c in rows}


def interface_status_counts(db: Session) -> dict:
    from models import Interface
    rows = (
        db.query(Interface.if_oper_status, func.count(Interface.id))
        .group_by(Interface.if_oper_status)
        .all()
    )
    return {s or "unknown": c for s, c in rows}


def config_coverage(db: Session) -> dict:
    from models import Device, DeviceConfig

    total = db.query(func.count(DeviceConfig.id)).scalar() or 0
    distinct = (
        db.query(func.count(func.distinct(DeviceConfig.device_id))).scalar() or 0
    )
    rows = (
        db.query(Device.device_type, func.count(func.distinct(DeviceConfig.device_id)))
        .join(Device, Device.id == DeviceConfig.device_id)
        .group_by(Device.device_type)
        .all()
    )
    return {
        "total_configs": total,
        "devices_with_config": distinct,
        "by_device_type": {t or "unknown": c for t, c in rows},
    }


def scan_history(db: Session, limit: int = 100) -> list[dict]:
    """Every scan with its recorded device count plus actual link count."""
    jobs = db.query(ScanJob).order_by(ScanJob.started_at.desc()).limit(limit).all()
    result = []
    for job in jobs:
        row = job.to_dict()
        row["links"] = (
            db.query(func.count(Link.id)).filter(Link.scan_id == job.id).scalar() or 0
        )
        result.append(row)
    return result


def stale_devices(db: Session, days: int = 90) -> int:
    """Devices not seen in the last `days` days (likely decommissioned)."""
    from datetime import timedelta

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    return (
        db.query(func.count(Device.id))
        .filter(Device.last_seen < cutoff)
        .scalar()
        or 0
    )


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


def vault_communities(db: Session) -> list[str]:
    """All unique SNMP v2c communities stored in the credential vault.

    Used as the default community set for backfill walks so operators only
    need to maintain the vault, not per-request values.
    """
    rows = db.query(Credential.snmp_community).filter(
        Credential.snmp_community != "").all()
    seen: list[str] = []
    for (community,) in rows:
        if community and community not in seen:
            seen.append(community)
    return seen or ["public"]


def vault_ssh_credentials(db: Session) -> list[Credential]:
    """SSH credentials from the vault (type == 'ssh')."""
    return db.query(Credential).filter(Credential.credential_type == "ssh").all()


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


# ── Site mappings (Sprint 13) ────────────────────────────────────────────────

def create_site_mapping(db: Session, prefix: str, site: str) -> SiteMapping:
    """Add a hostname-prefix → site rule. Returns the mapping (or raises on dup)."""
    existing = db.query(SiteMapping).filter(SiteMapping.prefix == prefix).first()
    if existing:
        raise ValueError(f"mapping for prefix '{prefix}' already exists")
    mapping = SiteMapping(prefix=prefix, site=site)
    db.add(mapping)
    db.commit()
    db.refresh(mapping)
    return mapping


def list_site_mappings(db: Session) -> list[SiteMapping]:
    return db.query(SiteMapping).order_by(SiteMapping.prefix).all()


def delete_site_mapping(db: Session, mapping_id: int) -> bool:
    mapping = db.get(SiteMapping, mapping_id)
    if mapping is None:
        return False
    db.delete(mapping)
    db.commit()
    return True


def seed_site_mappings_from_hostnames(db: Session) -> dict:
    """Discover hostname-prefix → site rules from devices that DO have a site.

    Devices imported from a site-scoped Catalyst import carry both a site and
    a hostname; the shared prefix (e.g. "AMTRCHIIL") is a strong signal that
    other devices sharing that prefix belong to the same site. This seeds the
    mapping table so the full-environment backfill can use it.
    """
    rows = (
        db.query(Device.hostname, Device.site)
        .filter(Device.site != "", Device.hostname != "")
        .all()
    )
    prefixes: dict[str, str] = {}
    for hostname, site in rows:
        prefix = _hostname_prefix(hostname)
        if prefix and len(prefix) >= 5:
            prefixes.setdefault(prefix, site)

    created = 0
    skipped = 0
    for prefix, site in sorted(prefixes.items()):
        if db.query(SiteMapping).filter(SiteMapping.prefix == prefix).first():
            skipped += 1
            continue
        db.add(SiteMapping(prefix=prefix, site=site))
        created += 1
    db.commit()
    return {"discovered": len(prefixes), "created": created, "skipped": skipped}


def _hostname_prefix(hostname: str) -> str:
    """Extract the uppercase alphanumeric prefix of a hostname (up to 9 chars)."""
    clean = (hostname or "").split(".")[0].strip().upper()
    letters = ""
    for ch in clean:
        if ch.isalnum():
            letters += ch
        else:
            break
    return letters


def apply_site_mappings(db: Session, limit: int = 0) -> dict:
    """Backfill device.site for devices with blank site by matching hostname prefixes."""
    mappings = list_site_mappings(db)
    matched = 0
    updated = 0
    unchanged = 0
    query = db.query(Device).filter(Device.site == "")
    if limit:
        query = query.limit(limit)
    for device in query.all():
        hostname = (device.hostname or "").upper()
        if not hostname:
            continue
        best: tuple[int, str] = (0, "")
        for mapping in mappings:
            pref = mapping.prefix.upper()
            if hostname.startswith(pref) and len(pref) > best[0]:
                best = (len(pref), mapping.site)
        if best[0] > 0:
            matched += 1
            if device.site != best[1]:
                device.site = best[1]
                updated += 1
            else:
                unchanged += 1
    db.commit()
    return {"mappings": len(mappings), "matched": matched, "updated": updated,
            "unchanged": unchanged}


# ── Data-quality gates (Sprint 13) ────────────────────────────────────────────

def dod_gates(db: Session) -> dict:
    """Measure the Sprint 13 Definition of Done thresholds.

    Gates (from the Q19 decision):
        - site coverage    ≥ 90% of devices have a site
        - interface coverage ≥ 95% of network devices have interfaces
        - link validation  ≥ 80% of links validated (protocol != 'catalyst')
        - config coverage  ≥ 90% of switches have a config
    """
    total = db.query(func.count(Device.id)).scalar() or 0
    with_site = db.query(func.count(Device.id)).filter(Device.site != "").scalar() or 0

    network_types = ("switch", "router", "core-switch", "firewall")
    network_devices = (
        db.query(func.count(Device.id))
        .filter(Device.device_type.in_(network_types))
        .scalar() or 0
    )
    network_with_interfaces = (
        db.query(func.count(func.distinct(Interface.device_id)))
        .join(Device, Device.id == Interface.device_id)
        .filter(Device.device_type.in_(network_types))
        .scalar() or 0
    )

    total_links = db.query(func.count(Link.id)).scalar() or 0
    validated_links = (
        db.query(func.count(Link.id)).filter(Link.protocol != "catalyst").scalar() or 0
    )

    switches = db.query(func.count(Device.id)).filter(Device.device_type == "switch").scalar() or 0
    switches_with_config = (
        db.query(func.count(func.distinct(DeviceConfig.device_id)))
        .join(Device, Device.id == DeviceConfig.device_id)
        .filter(Device.device_type == "switch")
        .scalar() or 0
    )

    def pct(n: int, d: int) -> float:
        return round(100.0 * n / d, 1) if d else 0.0

    return {
        "site": {
            "target": 90, "actual": pct(with_site, total),
            "devices_with_site": with_site, "devices_total": total, "met": with_site >= 0.9 * total,
        },
        "interfaces": {
            "target": 95, "actual": pct(network_with_interfaces, network_devices),
            "devices_with_interfaces": network_with_interfaces, "devices_total": network_devices,
            "met": network_with_interfaces >= 0.95 * network_devices,
        },
        "links": {
            "target": 80, "actual": pct(validated_links, total_links),
            "validated": validated_links, "links_total": total_links, "met": validated_links >= 0.8 * total_links,
        },
        "configs": {
            "target": 90, "actual": pct(switches_with_config, switches),
            "switches_with_config": switches_with_config, "switches_total": switches, "met": switches_with_config >= 0.9 * switches,
        },
    }


# ── Device Configs (Sprint 9) ─────────────────────────────────────────────────

def save_device_config(db: Session, device_id: int, config_text: str,
                        config_type: str = "running", error: str = "",
                        collected_by: str = "") -> DeviceConfig:
    cfg = DeviceConfig(
        device_id=device_id,
        config_text=config_text,
        config_type=config_type,
        error=error,
        collected_by=collected_by or None,
    )
    db.add(cfg)
    db.commit()
    db.refresh(cfg)
    return cfg


def get_device_configs(db: Session, device_id: int,
                       limit: int = 20) -> list[DeviceConfig]:
    return (
        db.query(DeviceConfig)
        .filter(DeviceConfig.device_id == device_id)
        .order_by(DeviceConfig.collected_at.desc())
        .limit(limit)
        .all()
    )


def get_devices_by_type(db: Session, device_type: str = "switch",
                        limit: int = 500, site_pattern: str = "") -> list[Device]:
    from sqlalchemy import or_

    q = db.query(Device).filter(
        or_(
            Device.device_type.ilike(f"%{device_type}%"),
            Device.vendor.ilike("%cisco%"),
            Device.vendor.ilike("%aruba%"),
            Device.vendor.ilike("%meraki%"),
            Device.vendor.ilike("%hpe%"),
            Device.vendor.ilike("%h3c%"),
            Device.vendor.ilike("%juniper%"),
            Device.vendor.ilike("%arista%"),
            Device.vendor.ilike("%dell%"),
        )
    )
    if site_pattern:
        pat = site_pattern.lower()
        q = q.filter(
            or_(
                Device.hostname.ilike(f"%{pat}%"),
                Device.site.ilike(f"%{pat}%"),
            )
        )
    if limit:
        q = q.limit(limit)
    return q.all()


def classify_blank_devices(db: Session, limit: int = 0) -> dict:
    """Fill in device_type for blank-type devices using cheap heuristics.

    From Q18: fix the Catalyst full-env blanks (Meraki MR APs whose hostname
    ends in -AP/-APxx) and port-fingerprint the SNMP blanks (port 9100 →
    printer, port 161 → generic network host). Devices that stay blank remain
    honest 'unknown' rather than a wrong guess.
    """
    import re

    query = db.query(Device).filter(Device.device_type == "")
    if limit:
        query = query.limit(limit)
    changed = 0
    rows: list[tuple[Device, str]] = []
    for d in query.all():
        hostname = (d.hostname or "").strip().upper()
        ports = d.open_ports or []
        new_type = ""
        if re.search(r"(^|[-_])(AP|WAP|WIFI|AIR)[-_]?\d*$", hostname) or \
           re.search(r"-AP\d*$", hostname):
            new_type = "accesspoint"
        elif 9100 in ports:
            new_type = "printer"
        elif hostname.startswith("AP-") or "-AP" in hostname:
            new_type = "accesspoint"
        if new_type and new_type != d.device_type:
            d.device_type = new_type
            changed += 1
            rows.append((d, new_type))
    db.commit()
    return {"changed": changed, "total_scanned": len(rows)}
