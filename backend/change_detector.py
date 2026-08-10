"""Scan-to-scan change detection (Sprint 11).

Compares two scan jobs and identifies added/removed devices and topology links,
plus devices whose identity fields (hostname, vendor, type) changed between scans.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from models import Device, Link, ScanJob


def compare_scans(
    db: Session,
    scan_a_id: str,
    scan_b_id: str,
) -> dict:
    """Return device and link diffs between two scan jobs.

    Returns a dict with keys:
        added_devices, removed_devices, changed_devices,
        added_links, removed_links,
        scan_a, scan_b (summary dicts)
    """
    scan_a = db.get(ScanJob, scan_a_id)
    scan_b = db.get(ScanJob, scan_b_id)
    if not scan_a or not scan_b:
        missing = []
        if not scan_a:
            missing.append(scan_a_id)
        if not scan_b:
            missing.append(scan_b_id)
        return {"error": f"scan(s) not found: {', '.join(missing)}"}

    # ── Devices ────────────────────────────────────────────────────────
    devices_a = set()
    devices_b = set()
    device_map_a: dict[str, dict] = {}
    device_map_b: dict[str, dict] = {}

    for d in db.query(Device).filter(Device.last_scan_id == scan_a_id).all():
        devices_a.add(d.ip)
        device_map_a[d.ip] = {
            "ip": d.ip, "hostname": d.hostname, "vendor": d.vendor,
            "model": d.model, "device_type": d.device_type,
        }

    for d in db.query(Device).filter(Device.last_scan_id == scan_b_id).all():
        devices_b.add(d.ip)
        device_map_b[d.ip] = {
            "ip": d.ip, "hostname": d.hostname, "vendor": d.vendor,
            "model": d.model, "device_type": d.device_type,
        }

    added = sorted(devices_b - devices_a)
    removed = sorted(devices_a - devices_b)

    changed: list[dict] = []
    for ip in sorted(devices_a & devices_b):
        a = device_map_a[ip]
        b = device_map_b[ip]
        diffs = {}
        for key in ("hostname", "vendor", "model", "device_type"):
            if a.get(key) != b.get(key):
                diffs[key] = {"from": a.get(key), "to": b.get(key)}
        if diffs:
            changed.append({"ip": ip, "changes": diffs})

    # ── Links ──────────────────────────────────────────────────────────
    links_a = db.query(Link).filter(Link.scan_id == scan_a_id).all()
    links_b = db.query(Link).filter(Link.scan_id == scan_b_id).all()

    link_set_a = {(l.endpoint_a, l.endpoint_b) for l in links_a}
    link_set_b = {(l.endpoint_a, l.endpoint_b) for l in links_b}

    added_links = sorted(link_set_b - link_set_a)
    removed_links = sorted(link_set_a - link_set_b)

    def _link_dict(ep):
        return {"source": ep[0], "target": ep[1]}

    return {
        "scan_a": {"id": scan_a.id, "subnet": scan_a.subnet,
                    "device_count": scan_a.device_count,
                    "started_at": scan_a.started_at.isoformat() if scan_a.started_at else None},
        "scan_b": {"id": scan_b.id, "subnet": scan_b.subnet,
                    "device_count": scan_b.device_count,
                    "started_at": scan_b.started_at.isoformat() if scan_b.started_at else None},
        "devices": {
            "added": added,
            "removed": removed,
            "changed": changed,
            "count_a": len(devices_a),
            "count_b": len(devices_b),
        },
        "links": {
            "added": [_link_dict(l) for l in added_links],
            "removed": [_link_dict(l) for l in removed_links],
            "count_a": len(link_set_a),
            "count_b": len(link_set_b),
        },
    }
