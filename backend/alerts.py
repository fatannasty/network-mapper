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


def _spof_never_notified(db, device_ip: str) -> bool:
    from models import Notification

    return (db.query(Notification)
            .filter(Notification.kind == "spof",
                    Notification.device_ip == device_ip)
            .first()) is None


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

    # SPOF advisories (one-time per device).
    from models import Link
    from path_tracer import articulation_points

    spof_count = 0
    try:
        edges = [{"source": l.endpoint_a, "target": l.endpoint_b}
                 for l in db.query(Link).all()
                 if l.protocol not in ("velocloud-lan",)]
        spof_ips = set(articulation_points([d.ip for d in devices], edges)) if edges else set()
        for ip in sorted(spof_ips):
            d = next((x for x in devices if x.ip == ip), None)
            if d is None or not _spof_never_notified(db, ip):
                continue
            spof_count += 1
            _notify(db, "spof", "warning",
                    f"Single point of failure: {d.hostname or ip}",
                    f"{d.hostname or ip} ({ip}) — if this device fails, the "
                    "network partitions.", ip)
            created += 1
    except Exception:
        spof_count = 0

    db.commit()
    return {"created": created, "flapping": flapping_count,
            "down": down_count, "spof": spof_count}