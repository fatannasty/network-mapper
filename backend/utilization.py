"""Interface utilization sampling for link utilization trends.

A background pass walks interface counters (ifHCInOctets/ifHCOutOctets) on a
rotating subset of network devices, derives bits/sec rates from consecutive
samples, and stores them for time-series charts.
"""

from __future__ import annotations

import os
import socket
from datetime import datetime, timedelta

from snmp import walk_if_table as _walk_v2c

POLL_BATCH = int(os.environ.get("UTIL_POLL_BATCH", "100"))
RETENTION_DAYS = int(os.environ.get("UTIL_RETENTION_DAYS", "30"))
DEFAULT_TIMEOUT = float(os.environ.get("UTIL_POLL_TIMEOUT", "6"))


def _int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _walk(ip: str, communities: list[str], timeout: float) -> list[dict]:
    try:
        return _walk_v2c(ip, communities, timeout=timeout)
    except (socket.timeout, OSError, ValueError):
        return []


def _targets(db, batch: int):
    from models import Device, InterfaceUtilization
    from sqlalchemy import func

    last = (db.query(InterfaceUtilization.device_id,
                     func.max(InterfaceUtilization.sampled_at).label("last"))
            .group_by(InterfaceUtilization.device_id).subquery())
    rows = (db.query(Device, last.c.last)
            .outerjoin(last, Device.id == last.c.device_id)
            .filter(Device.device_type.in_(("switch", "core-switch", "router")))
            .order_by(last.c.last.is_(None).desc(), last.c.last.asc())
            .limit(batch).all())
    return [(d, l) for d, l in rows]


def _prev_sample(db, device_id: int, if_index: str):
    from models import InterfaceUtilization

    return (db.query(InterfaceUtilization)
            .filter(InterfaceUtilization.device_id == device_id,
                    InterfaceUtilization.if_index == if_index)
            .order_by(InterfaceUtilization.sampled_at.desc()).first())


def _prune(db) -> int:
    from models import InterfaceUtilization

    cutoff = datetime.utcnow() - timedelta(days=RETENTION_DAYS)
    deleted = (db.query(InterfaceUtilization)
               .filter(InterfaceUtilization.sampled_at < cutoff).delete())
    return deleted


def run_utilization_pass(db, communities: list[str]) -> dict:
    """Sample interface counters on the least-recently-sampled devices."""
    from models import InterfaceUtilization

    targets = _targets(db, POLL_BATCH)
    sampled = errors = samples_added = rates_recorded = 0
    now = datetime.utcnow()

    for device, _last in targets:
        ifaces = _walk(device.ip, communities, DEFAULT_TIMEOUT)
        if not ifaces:
            errors += 1
            continue
        sampled += 1
        for itf in ifaces:
            idx = itf.get("ifIndex", "")
            if not idx:
                continue
            cur_in = _int(itf.get("ifHCInOctets"))
            cur_out = _int(itf.get("ifHCOutOctets"))
            prev = _prev_sample(db, device.id, idx)
            in_rate = out_rate = 0.0
            if prev is not None and prev.sampled_at:
                dt = (now - prev.sampled_at).total_seconds()
                if dt > 0:
                    if cur_in >= (prev.in_octets or 0):
                        in_rate = (cur_in - (prev.in_octets or 0)) * 8 / dt
                    if cur_out >= (prev.out_octets or 0):
                        out_rate = (cur_out - (prev.out_octets or 0)) * 8 / dt
                    if in_rate > 0 or out_rate > 0:
                        rates_recorded += 1
            db.add(InterfaceUtilization(
                device_id=device.id, if_index=idx,
                if_name=(itf.get("ifName") or itf.get("ifDescr") or idx)[:128],
                if_speed=(itf.get("ifHighSpeed") or itf.get("ifSpeed") or "")[:32],
                in_octets=cur_in, out_octets=cur_out,
                in_rate=round(in_rate), out_rate=round(out_rate),
                sampled_at=now))
            samples_added += 1
    db.commit()
    pruned = _prune(db)
    db.commit()
    return {"targets": len(targets), "sampled": sampled, "errors": errors,
            "samples_added": samples_added, "rates_recorded": rates_recorded,
            "pruned": pruned}


def device_utilization(db, device_id: int, days: int = 3) -> dict:
    """Time-series per interface for one device (top interfaces by traffic)."""
    from models import Device, InterfaceUtilization
    from sqlalchemy import func

    device = db.get(Device, device_id)
    if device is None:
        return {"device_id": device_id, "interfaces": []}
    cutoff = datetime.utcnow() - timedelta(days=max(1, days))

    # Top interfaces by average total rate over the window.
    avg = (db.query(InterfaceUtilization.if_index,
                    func.avg(InterfaceUtilization.in_rate + InterfaceUtilization.out_rate).label("avg"))
           .filter(InterfaceUtilization.device_id == device_id,
                   InterfaceUtilization.sampled_at >= cutoff)
           .group_by(InterfaceUtilization.if_index)
           .order_by(func.avg(InterfaceUtilization.in_rate + InterfaceUtilization.out_rate).desc())
           .limit(8).all())

    interfaces = []
    for if_index, _a in avg:
        rows = (db.query(InterfaceUtilization)
                .filter(InterfaceUtilization.device_id == device_id,
                        InterfaceUtilization.if_index == if_index,
                        InterfaceUtilization.sampled_at >= cutoff)
                .order_by(InterfaceUtilization.sampled_at.asc()).all())
        interfaces.append({
            "if_index": if_index,
            "if_name": rows[0].if_name if rows else if_index,
            "if_speed": rows[0].if_speed if rows else "",
            "series": [{
                "t": r.sampled_at.isoformat(),
                "in_rate": r.in_rate, "out_rate": r.out_rate,
            } for r in rows],
        })
    return {"device_id": device_id, "ip": device.ip, "hostname": device.hostname,
            "interfaces": interfaces}


def top_utilization(db, days: int = 1, limit: int = 10) -> dict:
    """Busiest interfaces network-wide by average rate."""
    from models import Device, InterfaceUtilization
    from sqlalchemy import func

    cutoff = datetime.utcnow() - timedelta(days=max(1, days))
    rows = (db.query(
                Device.ip, Device.hostname, InterfaceUtilization.if_name,
                func.avg(InterfaceUtilization.in_rate).label("in"),
                func.avg(InterfaceUtilization.out_rate).label("out"),
                func.max(InterfaceUtilization.in_rate + InterfaceUtilization.out_rate).label("peak"))
            .join(Device, Device.id == InterfaceUtilization.device_id)
            .filter(InterfaceUtilization.sampled_at >= cutoff)
            .group_by(Device.ip, Device.hostname, InterfaceUtilization.if_name)
            .order_by((func.avg(InterfaceUtilization.in_rate + InterfaceUtilization.out_rate)).desc())
            .limit(limit).all())
    return {"days": days, "top": [{
        "ip": ip, "hostname": hostname, "if_name": if_name,
        "avg_in_rate": round(in_r or 0), "avg_out_rate": round(out_r or 0),
        "peak_rate": round(peak or 0),
    } for ip, hostname, if_name, in_r, out_r, peak in rows]}