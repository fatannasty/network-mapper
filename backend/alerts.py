"""Periodic health alerts: flapping, down, and SPOF notifications.

Detects state issues (flapping devices, unreachable devices, single points of
failure) and records in-app notifications, optionally emailing them when SMTP
is configured. Cooldowns prevent alert storms.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

COOLDOWN_HOURS = float(os.environ.get("ALERT_COOLDOWN_HOURS", "6"))


def _within_cooldown(db, kind: str, device_ip: str) -> bool:
    from models import Notification

    cutoff = datetime.utcnow() - timedelta(hours=COOLDOWN_HOURS)
    recent = (db.query(Notification)
              .filter(Notification.kind == kind,
                      Notification.device_ip == device_ip,
                      Notification.created_at >= cutoff)
              .first())
    return recent is not None


def _notify(db, kind: str, severity: str, title: str, message: str,
            device_ip: str = "") -> bool:
    from models import Notification
    from reports import send_email

    row = Notification(kind=kind, severity=severity, title=title,
                       message=message, device_ip=device_ip)
    db.add(row)
    db.flush()
    try:
        row.emailed = send_email(
            title, f"<p>{message}</p><p style='color:#6b7280'>Network Mapper alert.</p>")
    except Exception:
        row.emailed = False
    return True


def _last_spof_count(db) -> int | None:
    """Return the device count recorded in the most recent SPOF advisory."""
    from models import Notification

    last = (db.query(Notification)
            .filter(Notification.kind == "spof")
            .order_by(Notification.created_at.desc()).first())
    if last is None:
        return None
    try:
        return int(last.message.split()[0])
    except (ValueError, IndexError):
        return None


def run_alert_check(db) -> dict:
    """Scan current state and raise notifications for new issues."""
    import repositories
    from models import Device

    devices = db.query(Device).all()
    statuses = repositories._device_status_snapshot(db, [d.id for d in devices])
    flapping = repositories.flapping_ips(db)

    created = 0
    flapping_count = down_count = 0

    for ip in sorted(flapping):
        d = next((x for x in devices if x.ip == ip), None)
        if d is None or _within_cooldown(db, "flapping", ip):
            continue
        flapping_count += 1
        _notify(db, "flapping", "warning",
                f"Flapping: {d.hostname or ip}",
                f"{d.hostname or ip} ({ip}) is flapping — its reachability is "
                "repeatedly going up and down.", ip)
        created += 1

    for d in devices:
        if statuses.get(d.id) == "down":
            if _within_cooldown(db, "down", d.ip):
                continue
            down_count += 1
            _notify(db, "down", "critical",
                    f"Device down: {d.hostname or d.ip}",
                    f"{d.hostname or d.ip} ({d.ip}) is unreachable or has no "
                    "operational interfaces.", d.ip)
            created += 1

    # SPOF: a single aggregate advisory, re-issued only when the count changes.
    from models import Link
    from path_tracer import articulation_points

    spof_count = 0
    try:
        edges = [{"source": l.endpoint_a, "target": l.endpoint_b}
                 for l in db.query(Link).all()
                 if l.protocol not in ("velocloud-lan",)]
        spof_ips = set(articulation_points([d.ip for d in devices], edges)) if edges else set()
        if spof_ips and _last_spof_count(db) != len(spof_ips):
            sample_ips = sorted(spof_ips)[:6]
            names = []
            by_ip = {d.ip: d.hostname for d in devices}
            for ip in sample_ips:
                names.append(f"{by_ip.get(ip) or ip} ({ip})")
            _notify(db, "spof", "warning",
                    "Single point(s) of failure",
                    f"{len(spof_ips)} single point{'s' if len(spof_ips) != 1 else ''} of "
                    "failure detected — e.g. "
                    + ", ".join(names) + ".", "")
            spof_count = len(spof_ips)
            created += 1
    except Exception:
        spof_count = 0

    db.commit()
    return {"created": created, "flapping": flapping_count,
            "down": down_count, "spof": spof_count}