"""FastAPI application for the Discovery, Inventory and RBAC API.

Endpoints:
    GET  /health                          - service health (public)
    GET  /metrics                         - Prometheus metrics (public)
    POST /api/auth/login                  - obtain a bearer token (public)
    GET  /api/auth/me                     - current token payload (authenticated)
    POST /api/auth/users                  - create user (admin)
    GET  /api/auth/users                  - list users (admin)
    DELETE /api/auth/users/{id}           - delete user (admin)
    POST /api/discover                    - run a discovery scan (operator+)
    GET  /api/inventory/devices           - list persisted devices (authenticated)
    GET  /api/inventory/devices/{id}      - single device (authenticated)
    GET  /api/inventory/scans             - recent scan history (authenticated)
    GET  /api/inventory/report            - inventory summary (authenticated)
    GET  /api/inventory/report/export     - CSV export (authenticated)
    GET  /api/inventory/credentials       - stored credentials (authenticated)
    POST /api/inventory/credentials       - create credential (admin)
    DELETE /api/inventory/credentials/{id}- delete credential (admin)
    GET  /api/inventory/sites             - known sites (authenticated)
    POST /api/inventory/sites             - create site (admin)
    GET  /api/inventory/links             - all topology links (authenticated)
    GET  /api/inventory/devices/{id}/configs - device configs (authenticated)
    POST /api/inventory/collect-config    - collect configs via SSH (operator+)
    GET  /api/topology                    - topology graph (authenticated)
    POST /api/topology/diagram            - engineering diagram export (authenticated)
    GET  /api/topology/path               - shortest path (authenticated)
    GET  /api/topology/changes            - scan diff (authenticated)
    POST /api/catalyst/import             - Catalyst Center import (operator+)
    POST /api/catalyst/test               - Catalyst connectivity test (operator+)
    POST /api/catalyst/sites              - list Catalyst sites (operator+)
    POST /api/catalyst/collect-config     - collect configs via Catalyst API (operator+)
    POST /api/velocloud/import            - VeloCloud Orchestra import (operator+)
    POST /api/velocloud/test              - VeloCloud connectivity test (operator+)
    POST /api/meraki/import               - Meraki Dashboard import (operator+)
    POST /api/meraki/test                 - Meraki Dashboard connectivity test (operator+)

Roles:
    admin    - everything
    operator - run scans, view inventory (no credential/user management)
    viewer   - read-only inventory access
"""

from __future__ import annotations

import asyncio
import os
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Response, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from prometheus_client import CollectorRegistry, Gauge, generate_latest
from sqlalchemy import func
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

import repositories
import scanner
from database import get_db, init_db

AUTH_PROTOCOLS = ("md5", "sha", "none")
PRIVACY_PROTOCOLS = ("aes", "des", "none")
ROLES = ("admin", "operator", "viewer")

# Render cache: identical diagram/package requests (same nodes, links and
# options) are served from memory so repeat exports are instant. LRU-bounded
# by total bytes (not entry count) so large PNGs/VSDXs can't balloon memory.
import hashlib as _hashlib
import json as _json
from collections import OrderedDict as _OrderedDict

_RENDER_CACHE: _OrderedDict = _OrderedDict()
_RENDER_CACHE_MAX_BYTES = int(os.environ.get("RENDER_CACHE_MAX_BYTES", 128 * 1024 * 1024))
_RENDER_CACHE_BYTES = 0


def _render_cache_key(payload: dict) -> str:
    return _hashlib.md5(_json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def _render_cache_get(key: str):
    if key in _RENDER_CACHE:
        _RENDER_CACHE.move_to_end(key)
        return _RENDER_CACHE[key]
    return None


def _render_cache_set(key: str, data: bytes) -> None:
    global _RENDER_CACHE_BYTES
    if len(data) > _RENDER_CACHE_MAX_BYTES:
        return  # single artifact exceeds the whole budget — don't cache it
    _RENDER_CACHE[key] = data
    _RENDER_CACHE.move_to_end(key)
    _RENDER_CACHE_BYTES += len(data)
    while _RENDER_CACHE_BYTES > _RENDER_CACHE_MAX_BYTES and _RENDER_CACHE:
        _, oldest = _RENDER_CACHE.popitem(last=False)
        _RENDER_CACHE_BYTES -= len(oldest)


# Lightweight in-memory rate limiter for the expensive export endpoints.
import logging as _logging
import time as _time

logger = _logging.getLogger("network_mapper")

_EXPORT_RATE_MAX = int(os.environ.get("EXPORT_RATE_LIMIT", 30))  # requests / window
_EXPORT_RATE_WINDOW = 60.0
_rate_hits: dict[str, list[float]] = {}


def _enforce_export_rate(request) -> None:
    key = getattr(request.client, "host", "unknown")
    now = _time.monotonic()
    hits = [t for t in _rate_hits.get(key, []) if now - t < _EXPORT_RATE_WINDOW]
    if len(hits) >= _EXPORT_RATE_MAX:
        raise HTTPException(status_code=429, detail="Too many export requests; try again shortly.")
    hits.append(now)
    _rate_hits[key] = hits


# Stricter limiter for login (brute-force protection).
_LOGIN_RATE_MAX = int(os.environ.get("LOGIN_RATE_LIMIT", 10))  # attempts / window
_LOGIN_RATE_WINDOW = 60.0
_login_hits: dict[str, list[float]] = {}


def _enforce_login_rate(request) -> None:
    key = getattr(request.client, "host", "unknown")
    now = _time.monotonic()
    hits = [t for t in _login_hits.get(key, []) if now - t < _LOGIN_RATE_WINDOW]
    if len(hits) >= _LOGIN_RATE_MAX:
        raise HTTPException(status_code=429, detail="Too many login attempts; try again shortly.")
    hits.append(now)
    _login_hits[key] = hits


# Hard caps on diagram/package input so a huge payload can't exhaust the renderer.
MAX_DIAGRAM_NODES = int(os.environ.get("MAX_DIAGRAM_NODES", 2000))
MAX_DIAGRAM_LINKS = int(os.environ.get("MAX_DIAGRAM_LINKS", 10000))


def _validate_export_input(req) -> None:
    if not req.nodes:
        raise HTTPException(status_code=400, detail="no topology nodes supplied")
    if len(req.nodes) > MAX_DIAGRAM_NODES:
        raise HTTPException(status_code=400, detail=f"too many nodes (max {MAX_DIAGRAM_NODES})")
    if len(req.links) > MAX_DIAGRAM_LINKS:
        raise HTTPException(status_code=400, detail=f"too many links (max {MAX_DIAGRAM_LINKS})")

# Experimental VeloCloud LAN-inference links. These connect an SD-WAN edge to
# every LAN device in an inferred broadcast domain, are unverified, and bleed
# across sites (a Montreal edge showing up in the Miami topology). Excluded
# from topology graphs so foreign Veloclouds never pollute a site view.
NON_TOPOLOGY_PROTOCOLS = ("velocloud-lan",)


def _keep_topology_link(link) -> bool:
    """True if a Link belongs in topology graphs (not experimental inference)."""
    return link.protocol not in NON_TOPOLOGY_PROTOCOLS


# Background reachability poller (feeds up/down/flapping state). Interval in
# seconds; set to 0 (or negative) to disable.
_LATENCY_POLL_INTERVAL = int(os.environ.get("LATENCY_POLL_INTERVAL", "60"))


def _measure_latency_pass(db: Session, devices) -> tuple[int, int]:
    """Ping `devices`, update latency and record reachability transitions."""
    import datetime

    latencies = scanner.measure_latencies([d.ip for d in devices])
    now = datetime.datetime.now(datetime.timezone.utc)
    updated = 0
    for device in devices:
        latency = latencies.get(device.ip)
        status = "up" if (latency is not None and latency > 0) else "down"
        repositories.record_device_status(db, device.ip, status)
        if latency is not None:
            device.latency_ms = latency
            device.latency_checked_at = now
            updated += 1
    return len(devices), updated


def _run_latency_poll() -> dict:
    from database import SessionLocal

    with SessionLocal() as db:
        devices = repositories.list_devices(db, limit=5000)
        if not devices:
            return {"measured": 0, "updated": 0}
        measured, updated = _measure_latency_pass(db, devices)
        db.commit()
        return {"measured": measured, "updated": updated}


async def _latency_poll_loop() -> None:
    while True:
        await asyncio.sleep(_LATENCY_POLL_INTERVAL)
        try:
            result = await run_in_threadpool(_run_latency_poll)
            logger.info("latency poll: %s", result)
        except Exception as exc:  # noqa: BLE001
            logger.warning("latency poll failed: %s", exc)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    _rename_old_scans()
    poll_task = None
    if _LATENCY_POLL_INTERVAL > 0:
        poll_task = asyncio.create_task(_latency_poll_loop())
    try:
        yield
    finally:
        if poll_task is not None:
            poll_task.cancel()
            try:
                await poll_task
            except asyncio.CancelledError:
                pass


def _rename_old_scans():
    """Rename generic 'catalyst-center' scan labels to include device counts and dates."""
    from database import engine
    with engine.connect() as conn:
        # Rename catalyst-center scans with descriptive labels
        rows = conn.exec_driver_sql(
            "SELECT id, device_count, started_at FROM scan_jobs WHERE subnet = 'catalyst-center'"
        ).fetchall()
        for row in rows:
            scan_id, count, ts = row
            date_str = str(ts)[:10] if ts else "unknown date"
            label = f"Catalyst Import ({count} devices, {date_str})"
            conn.exec_driver_sql(
                "UPDATE scan_jobs SET subnet = ? WHERE id = ?",
                [label, scan_id],
            )
        conn.commit()


app = FastAPI(
    title="Network Discovery API",
    version="0.3.0",
    description="NetBrain-style discovery and classification platform (Sprint 3: encrypted credentials, SNMPv3, RBAC)",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:4173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request/response models ──────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class UserCreateRequest(BaseModel):
    username: str
    password: str
    role: str = "viewer"


class SnmpV3Request(BaseModel):
    username: str
    auth_protocol: str = "sha"          # md5 | sha | none
    auth_password: str = ""
    privacy_protocol: str = "aes"       # aes | des | none
    privacy_password: Optional[str] = None


class DiscoverRequest(BaseModel):
    subnet: str
    communities: Optional[list[str]] = ["public"]
    exclude_pcs: bool = True
    site: Optional[str] = None
    snmp_port: int = 161
    verbose: bool = False
    snmpv3: Optional[SnmpV3Request] = None


class DiscoverResponse(BaseModel):
    scan_id: str
    subnet: str
    local_ip: str
    scanned_hosts: int
    alive_hosts: int
    device_count: int
    snmp_identified: int
    devices: list[dict]
    connections: list[dict]


class CredentialRequest(BaseModel):
    name: str
    credential_type: str = "snmp"       # snmp | ssh | api
    username: str = ""
    password: str = ""
    snmp_community: str = ""
    site: str = ""


class SiteRequest(BaseModel):
    name: str
    location: str = ""


# ── Authentication / RBAC ────────────────────────────────────────────────────

def _bearer(request: Request) -> str:
    # Accept the token from either the Authorization header (API clients) or an
    # httpOnly cookie (browser). The header takes precedence.
    authorization = request.headers.get("Authorization", "")
    if authorization.startswith("Bearer "):
        return authorization[len("Bearer "):].strip()
    cookie = request.cookies.get("token")
    if cookie:
        return cookie.strip()
    raise HTTPException(status_code=401, detail="missing bearer token")


def get_current_user(token: str = Depends(_bearer)) -> dict:
    payload = repositories.get_user_by_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="invalid or expired token")
    return payload


def require_roles(*roles: str):
    def dependency(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="insufficient permissions")
        return user
    return dependency


authenticated = require_roles(*ROLES)
operator = require_roles("admin", "operator")
admin = require_roles("admin")


# ── Service ───────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "service": "network-discovery", "version": app.version,
            "local_ip": scanner.local_ip()}


@app.get("/metrics")
def metrics(db: Session = Depends(get_db)):
    """Prometheus metrics for the latest persisted network state.

    This is intentionally public so Prometheus can scrape it without an
    application bearer token. It reports last-known state; active reachability
    polling is separate from this export layer.
    """
    from models import Device, Interface, Link

    registry = CollectorRegistry()
    devices = Gauge(
        "network_mapper_devices_total",
        "Known devices grouped by type, vendor and site.",
        ["device_type", "vendor", "site"], registry=registry,
    )
    links = Gauge(
        "network_mapper_links_total",
        "Known topology links grouped by discovery protocol.",
        ["protocol"], registry=registry,
    )
    interfaces = Gauge(
        "network_mapper_interfaces_total",
        "Known interfaces grouped by operational status.",
        ["status"], registry=registry,
    )
    stale = Gauge(
        "network_mapper_stale_devices_total",
        "Devices not seen within the stale threshold.",
        ["days"], registry=registry,
    )
    last_scan = Gauge(
        "network_mapper_last_scan_timestamp_seconds",
        "Unix timestamp of the latest completed scan.", registry=registry,
    )
    last_scan_devices = Gauge(
        "network_mapper_last_scan_devices",
        "Device count recorded by the latest scan.", registry=registry,
    )
    last_scan_links = Gauge(
        "network_mapper_last_scan_links",
        "Link count recorded by the latest scan.", registry=registry,
    )
    scan_success = Gauge(
        "network_mapper_last_scan_success",
        "Whether the latest scan completed successfully.", registry=registry,
    )

    for (device_type, vendor, site, count) in (
        db.query(Device.device_type, Device.vendor, Device.site, func.count(Device.id))
        .group_by(Device.device_type, Device.vendor, Device.site)
        .all()
    ):
        devices.labels(device_type or "unknown", vendor or "unknown", site or "unknown").set(count)

    for protocol, count in db.query(Link.protocol, func.count(Link.id)).group_by(Link.protocol).all():
        links.labels(protocol or "unknown").set(count)

    for status, count in (
        db.query(Interface.if_oper_status, func.count(Interface.id))
        .group_by(Interface.if_oper_status)
        .all()
    ):
        interfaces.labels(status or "unknown").set(count)

    stale.labels("90").set(repositories.stale_devices(db, days=90))
    latest = repositories.list_scan_jobs(db, limit=1)
    if latest:
        scan = latest[0]
        scan_success.set(1 if scan.status == "completed" else 0)
        last_scan_devices.set(scan.device_count or 0)
        last_scan_links.set(
            db.query(func.count(Link.id)).filter(Link.scan_id == scan.id).scalar() or 0
        )
        if scan.finished_at:
            last_scan.set(scan.finished_at.timestamp())

    return Response(content=generate_latest(registry), media_type="text/plain; version=0.0.4")


# ── Auth ─────────────────────────────────────────────────────────────────────

@app.post("/api/auth/login")
def auth_login(req: LoginRequest, request: Request, db: Session = Depends(get_db)):
    _enforce_login_rate(request)
    result = repositories.issue_token(db, req.username, req.password)
    if result is None:
        raise HTTPException(status_code=401, detail="invalid username or password")
    resp = JSONResponse(content=result)
    # Also deliver the token as an httpOnly cookie so the browser never has to
    # hold it in JS/localStorage (mitigates XSS token theft).
    resp.set_cookie(
        "token", result["token"],
        httponly=True, samesite="lax", path="/",
        secure=os.environ.get("COOKIE_SECURE", "") == "1",
        max_age=12 * 3600,
    )
    return resp


@app.post("/api/auth/logout")
def auth_logout():
    resp = JSONResponse(content={"ok": True})
    resp.delete_cookie("token", path="/")
    return resp


@app.get("/api/auth/me")
def auth_me(user: dict = Depends(authenticated)):
    return user


@app.post("/api/auth/users", dependencies=[Depends(admin)])
def auth_create_user(req: UserCreateRequest, db: Session = Depends(get_db)):
    role = req.role if req.role in ROLES else "viewer"
    try:
        user = repositories.create_user(db, req.username, req.password, role)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return user.to_dict()


@app.get("/api/auth/users", dependencies=[Depends(admin)])
def auth_list_users(db: Session = Depends(get_db)):
    users = repositories.list_users(db)
    return {"count": len(users), "users": [u.to_dict() for u in users]}


@app.delete("/api/auth/users/{user_id}", dependencies=[Depends(admin)])
def auth_delete_user(user_id: int, db: Session = Depends(get_db)):
    if not repositories.delete_user(db, user_id):
        raise HTTPException(status_code=404, detail="user not found")
    return {"deleted": True}


class UserUpdateRequest(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None


@app.patch("/api/auth/users/{user_id}", dependencies=[Depends(admin)])
def auth_update_user(user_id: int, req: UserUpdateRequest, db: Session = Depends(get_db)):
    from models import User as UserModel
    user = db.get(UserModel, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    if req.username is not None:
        existing = db.query(UserModel).filter(UserModel.username == req.username, UserModel.id != user_id).first()
        if existing:
            raise HTTPException(status_code=409, detail="username already exists")
        user.username = req.username
    if req.password:
        user.password_hash = hash_password(req.password)
    if req.role and req.role in ROLES:
        user.role = req.role
    if req.is_active is not None:
        user.is_active = req.is_active
    db.commit()
    db.refresh(user)
    return user.to_dict()


@app.get("/api/admin/activity", dependencies=[Depends(admin)])
def admin_activity(db: Session = Depends(get_db)):
    """Return recent system activity from scan history."""
    scans = repositories.list_scan_jobs(db, limit=20)
    activity = []
    for s in scans:
        activity.append({
            "type": "scan",
            "action": f"Scan completed: {s.subnet}",
            "timestamp": s.finished_at.isoformat() if s.finished_at else s.started_at.isoformat() if s.started_at else None,
            "status": s.status,
            "details": {"device_count": s.device_count, "scan_kind": s.scan_kind},
        })
    return {"activity": activity}


@app.get("/api/admin/status", dependencies=[Depends(admin)])
def admin_status(db: Session = Depends(get_db)):
    """Return system status overview."""
    from models import Device, Interface, Link, ScanJob
    import os

    db_size = os.path.getsize("network_mapper.db") if os.path.exists("network_mapper.db") else 0
    latest_scan = repositories.list_scan_jobs(db, limit=1)
    stale_devices = repositories.stale_devices(db, days=90)

    return {
        "database_size_bytes": db_size,
        "total_devices": db.query(func.count(Device.id)).scalar() or 0,
        "total_links": db.query(func.count(Link.id)).scalar() or 0,
        "total_interfaces": db.query(func.count(Interface.id)).scalar() or 0,
        "total_scans": db.query(func.count(ScanJob.id)).scalar() or 0,
        "stale_devices_90d": stale_devices,
        "latest_scan": latest_scan[0].to_dict() if latest_scan else None,
        "scan_success_rate": 100.0 if not stale_devices else max(0, 100.0 - (stale_devices / max(db.query(func.count(Device.id)).scalar() or 1, 1)) * 100),
    }


# ── Discovery ─────────────────────────────────────────────────────────────────

@app.post("/api/discover", response_model=DiscoverResponse, dependencies=[Depends(operator)])
def api_discover(req: DiscoverRequest, db: Session = Depends(get_db)):
    snmpv3_dict = None
    snmpv3_username = ""
    if req.snmpv3:
        if req.snmpv3.auth_protocol.lower() not in AUTH_PROTOCOLS:
            raise HTTPException(status_code=400, detail="snmpv3.auth_protocol must be md5, sha, or none")
        if req.snmpv3.privacy_protocol.lower() not in PRIVACY_PROTOCOLS:
            raise HTTPException(status_code=400, detail="snmpv3.privacy_protocol must be aes, des, or none")
        snmpv3_dict = {
            "username": req.snmpv3.username,
            "auth_protocol": req.snmpv3.auth_protocol.lower(),
            "auth_password": req.snmpv3.auth_password,
            "privacy_protocol": req.snmpv3.privacy_protocol.lower(),
            "privacy_password": req.snmpv3.privacy_password or req.snmpv3.auth_password,
        }
        snmpv3_username = req.snmpv3.username

    scan_id = uuid.uuid4().hex[:12]
    communities = req.communities or ["public"]
    repositories.create_scan_job(db, scan_id, req.subnet, communities, req.exclude_pcs,
                                 snmpv3_username=snmpv3_username)
    try:
        result = scanner.discover(req.subnet, communities=communities,
                                  exclude_pcs=req.exclude_pcs, snmpv3=snmpv3_dict,
                                  snmp_port=req.snmp_port, verbose=req.verbose)
    except ValueError as exc:
        repositories.fail_scan_job(db, scan_id, str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    for device in result["devices"]:
        if req.site:
            device["site"] = req.site
        repositories.upsert_device(db, device, scan_id)

    repositories.replace_links(db, scan_id, result["connections"])
    repositories.finish_scan_job(db, scan_id, result)

    return {"scan_id": scan_id, **result}


# ── Inventory ─────────────────────────────────────────────────────────────────

@app.post("/api/inventory/measure-latency", dependencies=[Depends(operator)])
def inventory_measure_latency(site: Optional[str] = Query(None),
                              db: Session = Depends(get_db)):
    """Ping every device and store the ICMP round-trip time (latency_ms)."""
    devices = repositories.list_devices(db, site=site, limit=5000)
    if not devices:
        return {"measured": 0, "updated": 0}

    measured, updated = _measure_latency_pass(db, devices)
    db.commit()
    return {"measured": measured, "updated": updated}


@app.get("/api/inventory/devices", dependencies=[Depends(authenticated)])
def inventory_devices(device_type: Optional[str] = Query(None),
                      vendor: Optional[str] = Query(None),
                      site: Optional[str] = Query(None),
                      search: Optional[str] = Query(None),
                      vlan_90: Optional[bool] = Query(None),
                      limit: int = Query(200, ge=1, le=5000),
                      db: Session = Depends(get_db)):
    devices = repositories.list_devices(db, device_type=device_type, vendor=vendor,
                                        site=site, search=search, vlan_90=vlan_90,
                                        limit=limit)
    return {"count": len(devices), "devices": [d.to_dict() for d in devices]}


@app.get("/api/inventory/devices/{device_id}", dependencies=[Depends(authenticated)])
def inventory_device(device_id: int, db: Session = Depends(get_db)):
    device = repositories.get_device(db, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="device not found")
    return device.to_dict()


@app.get("/api/inventory/scans", dependencies=[Depends(authenticated)])
def inventory_scans(limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    jobs = repositories.list_scan_jobs(db, limit=limit)
    return {"count": len(jobs), "scans": [j.to_dict() for j in jobs]}


@app.get("/api/inventory/report", dependencies=[Depends(authenticated)])
def inventory_report(db: Session = Depends(get_db)):
    from models import Device

    return {
        "total_devices": db.query(Device).count(),
        "total_links": repositories.count_links(db),
        "total_interfaces": repositories.count_interfaces(db),
        "by_device_type": repositories.device_counts(db, Device.device_type),
        "by_vendor": repositories.device_counts(db, Device.vendor),
        "by_site": repositories.device_counts(db, Device.site),
        "link_protocols": repositories.link_counts_by_protocol(db),
        "interface_status": repositories.interface_status_counts(db),
        "config_coverage": repositories.config_coverage(db),
        "stale_devices_90d": repositories.stale_devices(db, days=90),
        "dod_gates": repositories.dod_gates(db),
        "scan_history": repositories.scan_history(db, limit=100),
        "recent_scans": [j.to_dict() for j in repositories.list_scan_jobs(db, limit=5)],
    }


@app.get("/api/inventory/report/export", dependencies=[Depends(authenticated)])
def inventory_report_export(report: str = Query(...), db: Session = Depends(get_db)):
    """Export a report as CSV. `report` is one of: devices, links, scans, configs."""
    from io import StringIO
    from models import Device, DeviceConfig
    import csv

    buf = StringIO()
    writer = csv.writer(buf)
    filename = "report"

    if report == "devices":
        filename = "devices"
        writer.writerow(["ip", "hostname", "vendor", "model", "device_type",
                         "site", "confidence", "first_seen", "last_seen"])
        for d in db.query(Device).order_by(Device.ip).all():
            writer.writerow([
                d.ip, d.hostname, d.vendor, d.model, d.device_type,
                d.site, d.confidence,
                d.first_seen.isoformat() if d.first_seen else "",
                d.last_seen.isoformat() if d.last_seen else "",
            ])
    elif report == "links":
        filename = "links"
        writer.writerow(["source", "target", "source_interface", "target_interface",
                         "protocol", "source_hostname", "target_hostname", "scan_id"])
        for l in repositories.list_links(db, limit=5000):
            writer.writerow([l.endpoint_a, l.endpoint_b, l.interface_a, l.interface_b,
                             l.protocol, l.hostname_a, l.hostname_b, l.scan_id])
    elif report == "scans":
        filename = "scans"
        writer.writerow(["id", "subnet", "status", "device_count", "links",
                         "started_at", "finished_at"])
        for s in repositories.scan_history(db, limit=1000):
            writer.writerow([s["id"], s["subnet"], s["status"], s["device_count"],
                             s["links"], s["started_at"], s["finished_at"]])
    elif report == "configs":
        filename = "configs"
        writer.writerow(["ip", "hostname", "config_type", "collected_at", "collected_by", "error"])
        for c in db.query(DeviceConfig).order_by(DeviceConfig.collected_at.desc()).all():
            writer.writerow([c.device.ip if c.device else "",
                             c.device.hostname if c.device else "",
                             c.config_type,
                             c.collected_at.isoformat() if c.collected_at else "",
                             c.collected_by or "",
                             c.error or ""])
    else:
        raise HTTPException(status_code=400,
                            detail="report must be one of: devices, links, scans, configs")

    from fastapi.responses import Response
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}.csv"'},
    )


@app.get("/api/configs/download", dependencies=[Depends(authenticated)])
def download_configs(db: Session = Depends(get_db)):
    """Download every collected config as plain text (one block per device).

    Each block is delimited by a header comment: hostname (IP), config type,
    collection timestamp, and who collected it. Configs are ordered newest
    first; when a device has multiple snapshots only the latest is included.
    """
    from models import DeviceConfig

    rows = (
        db.query(DeviceConfig)
        .order_by(DeviceConfig.device_id, DeviceConfig.collected_at.desc())
        .all()
    )

    latest_by_device: dict[int, DeviceConfig] = {}
    for cfg in rows:
        if cfg.device_id not in latest_by_device:
            latest_by_device[cfg.device_id] = cfg

    parts: list[str] = []
    for cfg in sorted(latest_by_device.values(), key=lambda c: (c.device.hostname or "").lower() or (c.device.ip or "")):
        hostname = cfg.device.hostname if cfg.device else ""
        ip = cfg.device.ip if cfg.device else ""
        when = cfg.collected_at.isoformat() if cfg.collected_at else ""
        by = cfg.collected_by or ""
        if cfg.error:
            body = f"[collection failed: {cfg.error}]"
        else:
            body = cfg.config_text or "(empty config)"
        parts.append(
            "# " + "=" * 72 + "\n"
            f"# {hostname or ip} ({ip})\n"
            f"# config_type: {cfg.config_type}\n"
            f"# collected_at: {when}\n"
            f"# collected_by: {by or 'unknown'}\n"
            + "# " + "=" * 72 + "\n\n"
            + body.rstrip("\n") + "\n"
        )

    from fastapi.responses import Response
    return Response(
        content="\n".join(parts),
        media_type="text/plain",
        headers={"Content-Disposition": 'attachment; filename="configs.txt"'},
    )


@app.get("/api/topology", dependencies=[Depends(authenticated)])
def api_topology(scan_id: Optional[str] = Query(None), focus: Optional[str] = Query(None),
                 site: Optional[str] = Query(None),
                 db: Session = Depends(get_db)):
    """Topology for a scan. With `focus=<ip>`, only that device and its
    direct neighbors (across every scan) are returned so the view stays
    focused on a single device's connections. With `site=<name>`, all
    devices at that site and their inter-connections are returned."""
    from models import Device, ScanJob
    from models import Link as LinkModel

    if scan_id:
        job = db.get(ScanJob, scan_id)
        if job is None:
            # Stale scan_id (e.g. from a replaced import) — fall back to latest.
            jobs = repositories.list_scan_jobs(db, limit=1)
            job = jobs[0] if jobs else None
    else:
        jobs = repositories.list_scan_jobs(db, limit=1)
        job = jobs[0] if jobs else None

    if job is None:
        return {"scan_id": None, "nodes": [], "links": [], "scan_meta": None}

    if site:
        # Site-focused topology: all devices at this site plus their
        # connections across every scan.
        devices = db.query(Device).filter(Device.site == site).all()
        site_ips = {d.ip for d in devices}
        if site_ips:
            touched = db.query(LinkModel).filter(
                LinkModel.protocol.notin_(NON_TOPOLOGY_PROTOCOLS),
                (LinkModel.endpoint_a.in_(site_ips)) | (LinkModel.endpoint_b.in_(site_ips)),
            ).all()
            neighbor_ips = set()
            for l in touched:
                neighbor_ips.add(l.endpoint_a)
                neighbor_ips.add(l.endpoint_b)
            known = set(site_ips)
            for ip in neighbor_ips:
                if ip not in known:
                    d = db.query(Device).filter(Device.ip == ip).first()
                    if d:
                        devices.append(d)
                        known.add(ip)
            extra_links = db.query(LinkModel).filter(
                LinkModel.protocol.notin_(NON_TOPOLOGY_PROTOCOLS),
                LinkModel.endpoint_a.in_(known) & LinkModel.endpoint_b.in_(known),
            ).all()
            links: list[dict] = []
            link_keys: set[tuple] = set()
            for l in extra_links:
                key = (l.endpoint_a, l.endpoint_b, l.interface_a, l.interface_b)
                if key not in link_keys:
                    link_keys.add(key)
                    links.append(l)
        else:
            links = []
    elif focus:
        focus_dev = db.query(Device).filter(Device.ip == focus).first()
        if focus_dev is None:
            return {"scan_id": job.id if job else None, "nodes": [], "links": [], "scan_meta": None, "focus": focus}

        # Direct links touching the focused device, across every scan.
        direct = [l for l in repositories.list_links(db, limit=50000)
                  if _keep_topology_link(l) and (l.endpoint_a == focus or l.endpoint_b == focus)]
        neighbor_ips = {focus}
        for l in direct:
            neighbor_ips.add(l.endpoint_a)
            neighbor_ips.add(l.endpoint_b)

        links = list(direct)
        # Include links between neighbours so the neighbourhood graph is
        # fully connected (not just spokes from the focused device).
        extra = db.query(LinkModel).filter(
            LinkModel.protocol.notin_(NON_TOPOLOGY_PROTOCOLS),
            LinkModel.endpoint_a.in_(neighbor_ips) & LinkModel.endpoint_b.in_(neighbor_ips),
        ).all()
        link_keys = {(l.endpoint_a, l.endpoint_b, l.interface_a, l.interface_b) for l in links}
        for l in extra:
            key = (l.endpoint_a, l.endpoint_b, l.interface_a, l.interface_b)
            if key not in link_keys:
                links.append(l)

        devices = db.query(Device).filter(Device.ip.in_(neighbor_ips)).all()
    elif scan_id:
        # For specific scans, fetch links first, then include ALL devices
        # that appear as link endpoints — even those whose last_scan_id
        # was later overwritten by a newer import.
        links = [l for l in repositories.list_links(db, scan_id=job.id) if _keep_topology_link(l)]
        link_ips = set()
        for l in links:
            link_ips.add(l.endpoint_a)
            link_ips.add(l.endpoint_b)
        devices = db.query(Device).filter(
            (Device.last_scan_id == job.id) | (Device.ip.in_(link_ips))
        ).all()

        # Also include links between any of these devices regardless of
        # which scan created them, so site imports show their connections
        # even when the links were discovered by an earlier SNMP walk.
        device_ips = {d.ip for d in devices}
        if device_ips:
            touched = db.query(LinkModel).filter(
                LinkModel.protocol.notin_(NON_TOPOLOGY_PROTOCOLS),
                (LinkModel.endpoint_a.in_(device_ips)) | (LinkModel.endpoint_b.in_(device_ips)),
            ).all()
            neighbor_ips = set()
            for l in touched:
                neighbor_ips.add(l.endpoint_a); neighbor_ips.add(l.endpoint_b)
            known = set(device_ips)
            for ip in neighbor_ips:
                if ip not in known:
                    d = db.query(Device).filter(Device.ip == ip).first()
                    if d:
                        devices.append(d)
                        known.add(ip)
            extra_links = db.query(LinkModel).filter(
                LinkModel.protocol.notin_(NON_TOPOLOGY_PROTOCOLS),
                LinkModel.endpoint_a.in_(known) & LinkModel.endpoint_b.in_(known),
            ).all()
            link_keys = {(l.endpoint_a, l.endpoint_b, l.interface_a, l.interface_b) for l in links}
            for l in extra_links:
                key = (l.endpoint_a, l.endpoint_b, l.interface_a, l.interface_b)
                if key not in link_keys:
                    links.append(l)
    else:
        devices = db.query(Device).filter(Device.last_scan_id == job.id).all()
        links = [l for l in repositories.list_links(db, scan_id=job.id) if _keep_topology_link(l)]

        # Same cross-scan link inclusion as the scan_id branch so the default
        # latest-scan view also shows connections discovered by older scans.
        device_ips = {d.ip for d in devices}
        if device_ips:
            # 1. Find all links touching the scan's devices, collect neighbors
            touched = db.query(LinkModel).filter(
                LinkModel.protocol.notin_(NON_TOPOLOGY_PROTOCOLS),
                (LinkModel.endpoint_a.in_(device_ips)) | (LinkModel.endpoint_b.in_(device_ips)),
            ).all()
            neighbor_ips = set()
            for l in touched:
                neighbor_ips.add(l.endpoint_a); neighbor_ips.add(l.endpoint_b)
            # 2. Include neighbors as devices
            known = set(device_ips)
            for ip in neighbor_ips:
                if ip not in known:
                    d = db.query(Device).filter(Device.ip == ip).first()
                    if d:
                        devices.append(d)
                        known.add(ip)
            # 3. All links among the expanded device set
            extra_links = db.query(LinkModel).filter(
                LinkModel.protocol.notin_(NON_TOPOLOGY_PROTOCOLS),
                LinkModel.endpoint_a.in_(known) & LinkModel.endpoint_b.in_(known),
            ).all()
            link_keys = {(l.endpoint_a, l.endpoint_b, l.interface_a, l.interface_b) for l in links}
            for l in extra_links:
                key = (l.endpoint_a, l.endpoint_b, l.interface_a, l.interface_b)
                if key not in link_keys:
                    links.append(l)

    # Enrich with operational state: per-device up/down derived from interface
    # oper status (falling back to reachability latency when there are none).
    from models import Interface as InterfaceModel

    iface_counts: dict[int, dict[str, int]] = {}
    device_ids = [d.id for d in devices if d.id is not None]
    if device_ids:
        for dev_id, status in db.query(InterfaceModel.device_id, InterfaceModel.if_oper_status).filter(
            InterfaceModel.device_id.in_(device_ids)
        ).all():
            c = iface_counts.setdefault(dev_id, {"up": 0, "down": 0})
            if status == "up":
                c["up"] += 1
            elif status == "down":
                c["down"] += 1

    def _device_status(d) -> str:
        c = iface_counts.get(d.id, {"up": 0, "down": 0})
        if c["up"] and c["down"]:
            return "degraded"
        if c["up"]:
            return "up"
        if c["down"]:
            return "down"
        if d.latency_checked_at:
            return "up" if (d.latency_ms or 0) > 0 else "down"
        return "unknown"

    flapping = repositories.flapping_ips(db)

    nodes: list[dict] = []
    seen: set[str] = set()
    status_by_ip: dict[str, str] = {}
    for d in devices:
        st = _device_status(d)
        if d.ip in flapping:
            st = "flapping"
        status_by_ip[d.ip] = st
        nodes.append({
            "id": d.ip,
            "ip": d.ip,
            "hostname": d.hostname,
            "vendor": d.vendor,
            "model": d.model,
            "device_type": d.device_type,
            "status": st,
            "vlan_90": d.vlan_90,
        })
        seen.add(d.ip)
    for link in links:
        for ep in (link.endpoint_a, link.endpoint_b):
            if ep not in seen:
                nodes.append({"id": ep, "ip": ep, "hostname": "", "vendor": "",
                              "model": "", "device_type": "unknown", "status": "unknown"})
                seen.add(ep)

    link_dicts = [l.to_dict() for l in links]
    for ld in link_dicts:
        if status_by_ip.get(ld.get("source")) == "down" or status_by_ip.get(ld.get("target")) == "down":
            ld["status"] = "down"
        else:
            ld["status"] = "up"

    # Mark single points of failure (articulation points) in the topology.
    from path_tracer import articulation_points
    spof_ips = articulation_points([n["ip"] for n in nodes], link_dicts)
    for n in nodes:
        n["spof"] = n["ip"] in spof_ips

    return {
        "scan_id": job.id,
        "nodes": nodes,
        "links": link_dicts,
        "scan_meta": {
            "subnet": job.subnet,
            "device_count": job.device_count,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "scan_kind": getattr(job, "scan_kind", None),
        },
        "focus": focus,
    }


def _summarize_topology(nodes: list[dict], links: list[dict], scan_id) -> dict:
    """Collapse distribution/access/endpoint tiers into subnet super-nodes.

    Top-tier devices (internet/velocloud/router/core) stay individual; every
    other device is folded into its /24 subnet block. Links are bundled into
    one edge per block pair with a count. Lets huge graphs render as a small,
    readable block diagram (drill into a block for detail).
    """
    from diagram_export import _layer_of, _subnet24

    top_tiers = {"internet", "velocloud", "router", "core"}
    top_nodes: list[dict] = []
    blocks: dict[str, dict] = {}
    ip_block: dict[str, str] = {}

    for n in nodes:
        ip = n.get("ip") or ""
        if _layer_of(n) in top_tiers:
            top_nodes.append(dict(n))
            continue
        pfx = _subnet24(ip) or "unknown"
        ip_block[ip] = pfx
        b = blocks.setdefault(pfx, {"count": 0, "up": 0, "down": 0, "flapping": 0})
        b["count"] += 1
        st = n.get("status") or "unknown"
        if st == "up":
            b["up"] += 1
        elif st == "down":
            b["down"] += 1
        elif st == "flapping":
            b["flapping"] += 1

    top_ips = {n["ip"] for n in top_nodes}
    summary_nodes = top_nodes
    for pfx in sorted(blocks):
        b = blocks[pfx]
        if b["flapping"]:
            status = "flapping"
        elif b["up"] == 0 and b["down"] > 0:
            status = "down"
        elif b["up"] > 0 and b["down"] > 0:
            status = "degraded"
        elif b["up"] > 0:
            status = "up"
        else:
            status = "unknown"
        summary_nodes.append({
            "id": f"subnet:{pfx}", "ip": "", "hostname": pfx,
            "vendor": "", "model": "", "device_type": "subnet",
            "subnet": pfx, "device_count": b["count"],
            "up": b["up"], "down": b["down"], "flapping": b["flapping"],
            "status": status,
        })

    block_id: dict[str, str] = {ip: ip for ip in top_ips}
    block_id.update({ip: f"subnet:{pfx}" for ip, pfx in ip_block.items()})

    bundle: dict[tuple[str, str], dict] = {}
    for l in links:
        s, t = l.get("source"), l.get("target")
        bs, bt = block_id.get(s), block_id.get(t)
        if not bs or not bt or bs == bt:
            continue
        key = tuple(sorted((bs, bt)))
        e = bundle.setdefault(key, {"source": key[0], "target": key[1], "count": 0, "down": 0})
        e["count"] += 1
        if l.get("status") == "down":
            e["down"] += 1

    summary_links = [
        {"source": e["source"], "target": e["target"], "count": e["count"],
         "status": "down" if e["down"] == e["count"] else "up"}
        for e in bundle.values()
    ]
    return {"scan_id": scan_id, "nodes": summary_nodes, "links": summary_links, "summary": True}


@app.get("/api/topology/summary", dependencies=[Depends(authenticated)])
def api_topology_summary(scan_id: Optional[str] = Query(None), db: Session = Depends(get_db)):
    """Clustered topology: subnet super-nodes + bundled edges (for large sites)."""
    data = api_topology(scan_id=scan_id, focus=None, site=None, db=db)
    return _summarize_topology(data.get("nodes") or [], data.get("links") or [], data.get("scan_id"))


class DiagramLegendEntry(BaseModel):
    key: str = ""
    label: str
    color: str = "#333333"


class DiagramExportRequest(BaseModel):
    """Engineering-drawing export of the topology graph the user is viewing.

    `nodes`/`links` come straight from the loaded /api/topology payload so the
    drawing matches exactly what is on screen (site focus, filters included).
    """
    format: str = "pdf"                       # pdf | vsdx | docx | png
    nodes: list[dict]
    links: list[dict]
    title: str = "AMTRAK NETWORK DIAGRAM"
    drawn_by: str = ""
    drawn_date: str = ""
    drawing_title: str = ""
    document_name: str = ""
    revision: str = ""
    rev_date: str = ""
    rev_time: str = ""
    color_links: bool = True
    legend: list[DiagramLegendEntry] = []
    exclude_endpoints: bool = False
    topology: str = "auto"                    # auto | tree | star | ring | bus
    link_detail: str = "full"                 # full | backbone | core
    scale: float = 2.0                        # PNG render scale (lower = preview)


def _diagram_cache_payload(fmt: str, req: DiagramExportRequest) -> dict:
    """Stable fields that determine the rendered output (excludes the
    auto-generated timestamps so repeat exports hit the render cache)."""
    return {
        "fmt": fmt,
        "nodes": req.nodes,
        "links": req.links,
        "title": req.title,
        "drawn_by": req.drawn_by,
        "drawn_date": req.drawn_date,
        "drawing_title": req.drawing_title,
        "document_name": req.document_name,
        "revision": req.revision,
        "rev_date": req.rev_date,
        "rev_time": req.rev_time,
        "color_links": req.color_links,
        "legend": [e.model_dump() for e in req.legend],
        "exclude_endpoints": req.exclude_endpoints,
        "topology": req.topology,
        "link_detail": req.link_detail,
        "scale": req.scale,
    }


@app.post("/api/topology/diagram", dependencies=[Depends(authenticated)])
async def api_topology_diagram(req: DiagramExportRequest, request: Request):
    """Render the topology as an Amtrak engineering drawing sheet.

    PDF and Word are static renders; the Visio (.vsdx) output is built from
    native shapes and 1-D connectors so devices and links stay editable.
    """
    import datetime
    import diagram_export

    _enforce_export_rate(request)
    _validate_export_input(req)

    fmt = req.format.lower()
    if fmt not in ("pdf", "vsdx", "docx", "png"):
        raise HTTPException(status_code=400, detail=f"unsupported format: {req.format}")

    cache_key = _render_cache_key(_diagram_cache_payload(fmt, req))
    cached = _render_cache_get(cache_key)
    if cached is not None:
        data = cached
    else:
        now = datetime.datetime.now()
        opts = {
            "title": req.title,
            "drawn_by": req.drawn_by,
            "drawn_date": req.drawn_date or now.strftime("%m%d%Y"),
            "drawing_title": req.drawing_title or req.title,
            "document_name": req.document_name,
            "revision": req.revision,
            "rev_date": req.rev_date or now.strftime("%d %b %y"),
            "rev_time": req.rev_time or now.strftime("%I:%M %p"),
            "color_links": req.color_links,
            "legend": [e.model_dump() for e in req.legend] or diagram_export.DEFAULT_LEGEND,
            "exclude_endpoints": req.exclude_endpoints,
            "topology": req.topology,
            "link_detail": req.link_detail,
            "scale": req.scale,
        }
        started = _time.monotonic()
        data = await run_in_threadpool(diagram_export.export_diagram, req.nodes, req.links, fmt, opts)
        logger.info("rendered %s (%d nodes) in %.2fs", fmt, len(req.nodes), _time.monotonic() - started)
        _render_cache_set(cache_key, data)

    media_types = {
        "pdf": "application/pdf",
        "png": "image/png",
        "vsdx": "application/vnd.ms-visio.drawing.main+xml",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
    slug = "".join(c if c.isalnum() else "-" for c in req.title.lower()).strip("-") or "diagram"
    return Response(
        content=data,
        media_type=media_types[fmt],
        headers={"Content-Disposition": f'attachment; filename="{slug}.{fmt}"'},
    )


class DiagramPrefsRequest(BaseModel):
    scan_id: str
    topology: str = "auto"
    link_detail: str = "full"


@app.get("/api/topology/diagram-prefs", dependencies=[Depends(authenticated)])
def api_diagram_prefs_get(scan_id: str = Query(...), db: Session = Depends(get_db)):
    """Remembered diagram layout preferences for a scan/site."""
    return repositories.get_diagram_prefs(db, scan_id)


@app.post("/api/topology/diagram-prefs", dependencies=[Depends(authenticated)])
def api_diagram_prefs_set(req: DiagramPrefsRequest, db: Session = Depends(get_db)):
    """Persist the diagram layout preferences for a scan/site."""
    if not repositories.set_diagram_prefs(db, req.scan_id, req.topology, req.link_detail):
        raise HTTPException(status_code=404, detail="scan not found")
    return {"ok": True}


@app.get("/api/topology/port-table", dependencies=[Depends(authenticated)])
def api_port_table(scan_id: Optional[str] = Query(None), db: Session = Depends(get_db)):
    """Companion CSV: every device, its interfaces, and what each port connects
    to (device -> port -> neighbor), matching the topology diagram."""
    from diagram_export import build_port_table

    data = api_topology(scan_id=scan_id, focus=None, site=None, db=db)
    csv_text = build_port_table(data.get("nodes") or [], data.get("links") or [])
    return Response(content=csv_text, media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="device-port-table.csv"'})


@app.post("/api/topology/package", dependencies=[Depends(authenticated)])
async def api_topology_package(req: DiagramExportRequest, request: Request):
    """One-click executive package: PDF + Word + port-table CSV in a ZIP."""
    import datetime
    import io
    import zipfile
    import diagram_export

    _enforce_export_rate(request)
    _validate_export_input(req)

    slug = "".join(c if c.isalnum() else "-" for c in req.title.lower()).strip("-") or "diagram"
    cache_key = _render_cache_key(_diagram_cache_payload("package", req))
    cached = _render_cache_get(cache_key)
    if cached is not None:
        data = cached
    else:
        now = datetime.datetime.now()
        opts = {
            "title": req.title,
            "drawn_by": req.drawn_by,
            "drawn_date": req.drawn_date or now.strftime("%m%d%Y"),
            "drawing_title": req.drawing_title or req.title,
            "document_name": req.document_name,
            "revision": req.revision,
            "rev_date": req.rev_date or now.strftime("%d %b %y"),
            "rev_time": req.rev_time or now.strftime("%I:%M %p"),
            "color_links": req.color_links,
            "legend": [e.model_dump() for e in req.legend] or diagram_export.DEFAULT_LEGEND,
            "exclude_endpoints": req.exclude_endpoints,
            "topology": req.topology,
            "link_detail": req.link_detail or "backbone",
        }

        def _build_package():
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr(f"{slug}.pdf", diagram_export.export_diagram(req.nodes, req.links, "pdf", opts))
                z.writestr(f"{slug}.docx", diagram_export.export_diagram(req.nodes, req.links, "docx", opts))
                z.writestr(f"{slug}-port-table.csv", diagram_export.build_port_table(req.nodes, req.links))
            return buf.getvalue()

        started = _time.monotonic()
        data = await run_in_threadpool(_build_package)
        logger.info("built package (%d nodes) in %.2fs", len(req.nodes), _time.monotonic() - started)
        _render_cache_set(cache_key, data)

    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{slug}-package.zip"'},
    )


@app.get("/api/topology/path", dependencies=[Depends(authenticated)])
def api_topology_path(source: str = Query(...), target: str = Query(...),
                      db: Session = Depends(get_db)):
    """Return the shortest path between two device IPs using the topology graph."""
    jobs = repositories.list_scan_jobs(db, limit=1)
    if not jobs:
        raise HTTPException(status_code=404, detail="no topology data available")
    job = jobs[0]

    links = [l for l in repositories.list_links(db, scan_id=job.id, limit=5000)
             if _keep_topology_link(l)]

    from path_tracer import build_path
    result = build_path([
        {
            "source": l.endpoint_a, "target": l.endpoint_b,
            "source_interface": l.interface_a, "target_interface": l.interface_b,
            "protocol": l.protocol,
            "source_hostname": l.hostname_a, "target_hostname": l.hostname_b,
        }
        for l in links
    ], source, target)

    return {
        "source": source,
        "target": target,
        "path": result.get("path", []),
        "hops": result.get("hops", 0),
        "error": result.get("error"),
    }


@app.get("/api/inventory/links", dependencies=[Depends(authenticated)])
def inventory_links(db: Session = Depends(get_db)):
    """Return all topology links across every scan for inventory display."""
    return {"links": [l.to_dict() for l in repositories.list_links(db, limit=5000)]}


@app.get("/api/topology/changes", dependencies=[Depends(authenticated)])
def api_topology_changes(scan_a: str = Query(...), scan_b: str = Query(...),
                         db: Session = Depends(get_db)):
    """Compare two scan jobs — return added/removed devices and links."""
    from change_detector import compare_scans
    result = compare_scans(db, scan_a, scan_b)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.get("/api/inventory/credentials", dependencies=[Depends(authenticated)])
def inventory_credentials(db: Session = Depends(get_db)):
    creds = repositories.list_credentials(db)
    return {"count": len(creds), "credentials": [c.to_dict() for c in creds]}


@app.post("/api/inventory/credentials", dependencies=[Depends(admin)])
def inventory_create_credential(req: CredentialRequest, db: Session = Depends(get_db)):
    try:
        cred = repositories.create_credential(
            db, req.name, req.credential_type, req.username,
            req.password, req.snmp_community, req.site,
        )
    except Exception:
        db.rollback()
        raise HTTPException(status_code=409, detail="credential name already exists") from None
    return cred.to_dict()


@app.delete("/api/inventory/credentials/{credential_id}", dependencies=[Depends(admin)])
def inventory_delete_credential(credential_id: int, db: Session = Depends(get_db)):
    if not repositories.delete_credential(db, credential_id):
        raise HTTPException(status_code=404, detail="credential not found")
    return {"deleted": True}


@app.get("/api/inventory/sites", dependencies=[Depends(authenticated)])
def inventory_sites(db: Session = Depends(get_db)):
    sites = repositories.list_sites(db)
    return {"count": len(sites), "sites": [s.to_dict() for s in sites]}


@app.post("/api/inventory/sites", dependencies=[Depends(admin)])
def inventory_create_site(req: SiteRequest, db: Session = Depends(get_db)):
    site = repositories.create_site(db, req.name, req.location)
    return site.to_dict()


# ── Site Mappings (Sprint 13) ────────────────────────────────────────────────

class SiteMappingRequest(BaseModel):
    prefix: str
    site: str


@app.get("/api/inventory/site-mappings", dependencies=[Depends(authenticated)])
def inventory_site_mappings(db: Session = Depends(get_db)):
    mappings = repositories.list_site_mappings(db)
    return {"count": len(mappings), "mappings": [m.to_dict() for m in mappings]}


@app.post("/api/inventory/site-mappings", dependencies=[Depends(admin)])
def inventory_create_site_mapping(req: SiteMappingRequest, db: Session = Depends(get_db)):
    try:
        mapping = repositories.create_site_mapping(db, req.prefix.strip(), req.site.strip())
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return mapping.to_dict()


@app.delete("/api/inventory/site-mappings/{mapping_id}", dependencies=[Depends(admin)])
def inventory_delete_site_mapping(mapping_id: int, db: Session = Depends(get_db)):
    if not repositories.delete_site_mapping(db, mapping_id):
        raise HTTPException(status_code=404, detail="mapping not found")
    return {"deleted": True}


@app.post("/api/inventory/site-mappings/seed", dependencies=[Depends(admin)])
def inventory_seed_site_mappings(db: Session = Depends(get_db)):
    """Auto-discover prefix→site rules from devices that already carry a site."""
    return repositories.seed_site_mappings_from_hostnames(db)


@app.post("/api/inventory/site-mappings/apply", dependencies=[Depends(operator)])
def inventory_apply_site_mappings(limit: int = 0, db: Session = Depends(get_db)):
    """Backfill device.site for blank-site devices using the mapping table."""
    return repositories.apply_site_mappings(db, limit=limit)


# ── Data-quality backfill jobs (Sprint 13) ───────────────────────────────────

class BackfillRequest(BaseModel):
    communities: Optional[list[str]] = None
    max_workers: int = 25
    timeout: float = 8.0
    limit: int = 0           # cap the device set (0 = all eligible)
    device_type: str = ""     # restrict to a device type (e.g. "switch")


def _vault_or_request_communities(db: Session, req: BackfillRequest) -> list[str]:
    """Vault SNMP communities, overridden by explicit request values."""
    if req.communities:
        return [c for c in req.communities if c]
    return repositories.vault_communities(db)


def _target_devices(db: Session, req: BackfillRequest,
                    device_types: tuple[str, ...]) -> list[dict]:
    """Network devices matching the requested scope (thread-safe plain dicts)."""
    from models import Device
    from sqlalchemy import or_

    q = db.query(Device).filter(Device.device_type.in_(device_types))
    if req.device_type:
        q = q.filter(Device.device_type == req.device_type)
    q = q.order_by(Device.ip)
    if req.limit:
        q = q.limit(req.limit)
    return [{
        "ip": d.ip, "hostname": d.hostname, "device_type": d.device_type,
        "id": d.id,
    } for d in q.all()]


@app.post("/api/backfill/classify-blanks", dependencies=[Depends(operator)])
def backfill_classify_blanks(limit: int = 0, db: Session = Depends(get_db)):
    """Classify blank-type devices via hostname/port heuristics (Q18)."""
    return repositories.classify_blank_devices(db, limit=limit)


@app.post("/api/backfill/interfaces", dependencies=[Depends(operator)])
def backfill_interfaces(req: BackfillRequest, db: Session = Depends(get_db)):
    """Walk IF-MIB on network devices (switch/router/core-switch) via SNMP."""
    import backfill

    devices = _target_devices(
        db, req, ("switch", "router", "core-switch", "firewall"))
    communities = _vault_or_request_communities(db, req)
    summary = backfill.backfill_interfaces(
        devices, communities,
        max_workers=req.max_workers, timeout=req.timeout)

    # Persist walked interfaces onto the matching devices.
    from models import Device, Interface

    saved_devices = 0
    saved_interfaces = 0
    for r in summary["results"]:
        device = db.get(Device, r.get("device_id"))
        if device is None or r["error"]:
            continue
        interfaces = r.get("interfaces") or []
        if not interfaces:
            continue
        repositories._sync_interfaces(db, device, interfaces)
        saved_devices += 1
        saved_interfaces += len(interfaces)
    db.commit()

    return {**summary,
            "persisted_devices": saved_devices,
            "persisted_interfaces": saved_interfaces}


@app.post("/api/backfill/links", dependencies=[Depends(operator)])
def backfill_links(req: BackfillRequest, db: Session = Depends(get_db)):
    """Walk LLDP/CDP on core/routers to validate (and later replace) Catalyst links."""
    import backfill
    from models import Link, ScanJob
    import uuid as _uuid

    devices = _target_devices(db, req, ("core-switch", "router"))
    if not devices:
        devices = _target_devices(db, req, ("switch", "router", "core-switch"))
    communities = _vault_or_request_communities(db, req)
    summary = backfill.backfill_link_validation(
        devices, communities,
        max_workers=req.max_workers, timeout=req.timeout)

    # Persist validated neighbor links under their own scan so link-protocol
    # reports and topology show SNMP-validated connectivity alongside the
    # Catalyst-derived links.
    scan_id = _uuid.uuid4().hex[:12]
    scan = ScanJob(id=scan_id, subnet="CatC: SNMP Link Validation",
                   communities=communities, exclude_pcs=True)
    scan.scan_kind = "validation"
    db.add(scan)

    ip_by_hostname: dict[str, str] = {}
    for d in devices:
        if d.get("hostname"):
            ip_by_hostname[(d["hostname"] or "").lower()] = d["ip"]

    links: list[dict] = []
    seen: set[tuple] = set()
    for r in summary["results"]:
        if r["error"] and r["neighbor_count"] == 0:
            continue
        for n in r.get("neighbors", []):
            remote_name = n.get("remote_sysname") or n.get("remote_device_id") or ""
            remote = n.get("remote_ip") or ip_by_hostname.get(remote_name.lower(), "")
            target_id = remote or remote_name
            if not target_id or target_id == r["ip"]:
                continue
            a, b = sorted((r["ip"], target_id))
            key = (a, b)
            if key in seen:
                continue
            seen.add(key)
            links.append(Link(
                scan_id=scan_id,
                endpoint_a=a, endpoint_b=b,
                interface_a=n.get("local_port", ""),
                interface_b=n.get("remote_port_id") or n.get("remote_port_desc") or n.get("remote_port", ""),
                protocol=n.get("protocol", "lldp"),
            ))
    db.add_all(links)
    db.commit()

    return {"scan_id": scan_id, "validation_links": len(links), **summary}


@app.post("/api/backfill/vlan90", dependencies=[Depends(operator)])
def backfill_vlan90(limit: int = 0, db: Session = Depends(get_db)):
    """Recompute VLAN 90 flags from locally stored running configs.

    Fixes devices imported before the flag existed (or while the detector
    was shadowed) without requiring a fresh Catalyst import. Devices with
    no stored config are left unflagged (vlan_90 = NULL).
    """
    import catalyst
    from models import Device, DeviceConfig

    rows = (
        db.query(DeviceConfig, Device.id, Device.ip)
        .join(Device, Device.id == DeviceConfig.device_id)
        .filter(DeviceConfig.config_type == "running",
                DeviceConfig.error.is_(None) | (DeviceConfig.error == ""))
        .order_by(DeviceConfig.collected_at.desc())
        .all()
    )
    latest_by_id: dict[int, str] = {}
    for cfg, dev_id, _ip in rows:
        if dev_id not in latest_by_id and cfg.config_text:
            latest_by_id[dev_id] = cfg.config_text

    targets = db.query(Device).filter(Device.id.in_(latest_by_id.keys()))
    if limit:
        targets = targets.limit(limit)
    devices = targets.all()

    updated = detected = 0
    for d in devices:
        cfg = latest_by_id.get(d.id, "")
        flag = catalyst.detect_vlan90(cfg)
        if d.vlan_90 != flag:
            d.vlan_90 = flag
            updated += 1
        if flag:
            detected += 1
    db.commit()

    return {
        "devices_with_config": len(devices),
        "updated": updated,
        "vlan90_detected": detected,
        "backfilled": True,
    }


def _neighbors_for_ip(raw: list[dict]) -> list[dict]:
    return raw or []


# ── Catalyst Center Import ─────────────────────────────────────────────────────

class CatalystImportRequest(BaseModel):
    base_url: str
    username: str
    password: str
    site_name: str = ""
    site_id: str = ""
    device_filter: str = ""
    skip_enrichment: bool = False  # skip CDP/LLDP/POE per-device walk for faster imports
    detect_vlan90: bool = False     # fetch running configs to flag VLAN 90 switches


@app.post("/api/catalyst/import", dependencies=[Depends(operator)])
def catalyst_import(req: CatalystImportRequest, db: Session = Depends(get_db)):
    import catalyst

    try:
        stored = (repositories.get_running_configs_by_ip(db)
                  if req.detect_vlan90 else None)
        devices, links, debug = catalyst.import_devices(
            req.base_url, req.username, req.password,
            site_name=req.site_name, site_id=req.site_id,
            device_filter=req.device_filter,
            skip_enrichment=req.skip_enrichment,
            flag_vlan90=req.detect_vlan90,
            stored_configs=stored)
    except catalyst.CatalystError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}") from e

    scan_id = uuid.uuid4().hex[:12]
    site_label = req.site_name or req.device_filter or "Full Environment"
    scan_subnet = f"CatC: {site_label}"[:64]
    job = repositories.create_scan_job(db, scan_id, scan_subnet, [], False)
    if req.site_name:
        job.scan_kind = f"site:{site_label}"
    elif req.device_filter:
        job.scan_kind = f"filter:{site_label}"
    else:
        job.scan_kind = "full_env"
    db.commit()

    for device in devices:
        repositories.upsert_device(db, device, scan_id)

    repositories.replace_links(db, scan_id, links)

    repositories.finish_scan_job(db, scan_id, {
        "subnet": "catalyst-center", "local_ip": "",
        "scanned_hosts": len(devices), "alive_hosts": len(devices),
        "device_count": len(devices), "snmp_identified": 0,
        "devices": devices, "connections": links,
    })

    return {"scan_id": scan_id, "device_count": len(devices),
            "links_found": len(links), "debug": debug}


@app.post("/api/catalyst/sites", dependencies=[Depends(operator)])
def catalyst_sites(req: CatalystImportRequest):
    import catalyst
    import traceback

    try:
        token = catalyst.authenticate(req.base_url, req.username, req.password)
        result = catalyst.get_sites(req.base_url, token)
        return {"sites": result["sites"],
                "debug": result.get("debug", {})}
    except catalyst.CatalystError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {e}\n\n{traceback.format_exc()}")


@app.post("/api/catalyst/site-members-debug", dependencies=[Depends(operator)])
def catalyst_site_members_debug(req: CatalystImportRequest):
    import catalyst
    import traceback

    if not req.site_id:
        raise HTTPException(status_code=400, detail="site_id is required")

    try:
        result = catalyst.debug_site_membership(
            req.base_url, req.username, req.password, req.site_id)
    except catalyst.CatalystError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {e}\n\n{traceback.format_exc()}")

    return result


@app.post("/api/catalyst/test", dependencies=[Depends(operator)])
def catalyst_test(req: CatalystImportRequest):
    import catalyst
    import traceback

    try:
        result = catalyst.test_connection(req.base_url, req.username, req.password)
    except catalyst.CatalystError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        tb = traceback.format_exc()
        raise HTTPException(status_code=500, detail=f"Error: {e}\n\nTraceback:\n{tb}")

    return result


# ── VeloCloud Orchestra Import ──────────────────────────────────────────────────

class VeloCloudImportRequest(BaseModel):
    base_url: str
    username: str = ""
    password: str = ""
    token: str = ""  # Direct JWT token (alternative to username/password)


@app.post("/api/velocloud/test", dependencies=[Depends(operator)])
def velocloud_test(req: VeloCloudImportRequest):
    import velocloud

    try:
        if req.token:
            edges = velocloud.get_edges(req.base_url, req.token)
            result = {"connected": True, "edge_count": len(edges)}
        else:
            result = velocloud.test_connection(req.base_url, req.username, req.password)
    except velocloud.VeloCloudError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")
    return result


@app.post("/api/velocloud/import", dependencies=[Depends(operator)])
def velocloud_import(req: VeloCloudImportRequest, db: Session = Depends(get_db)):
    import velocloud

    try:
        if req.token:
            devices, links, debug = velocloud.import_edges_with_token(req.base_url, req.token)
        else:
            devices, links, debug = velocloud.import_edges(req.base_url, req.username, req.password)
    except velocloud.VeloCloudError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")

    scan_id = uuid.uuid4().hex[:12]
    scan_subnet = "VeloCloud: Orchestra"
    job = repositories.create_scan_job(db, scan_id, scan_subnet, [], False)
    job.scan_kind = "velocloud"
    db.commit()

    for device in devices:
        repositories.upsert_device(db, device, scan_id)

    repositories.replace_links(db, scan_id, links)

    repositories.finish_scan_job(db, scan_id, {
        "subnet": "velocloud", "local_ip": "",
        "scanned_hosts": len(devices), "alive_hosts": len(devices),
        "device_count": len(devices), "snmp_identified": 0,
        "devices": devices, "connections": links,
    })

    return {"scan_id": scan_id, "device_count": len(devices),
            "links_found": len(links), "debug": debug}


# ── Meraki Dashboard Import ────────────────────────────────────────────────────

class MerakiImportRequest(BaseModel):
    base_url: str = "https://api.meraki.com"
    api_key: str


@app.post("/api/meraki/test", dependencies=[Depends(operator)])
def meraki_test(req: MerakiImportRequest):
    import meraki

    try:
        result = meraki.test_connection(req.base_url, req.api_key)
    except meraki.MerakiError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")
    return result


@app.post("/api/meraki/import", dependencies=[Depends(operator)])
def meraki_import(req: MerakiImportRequest, db: Session = Depends(get_db)):
    import meraki

    try:
        devices, links, debug = meraki.import_devices(req.base_url, req.api_key)
    except meraki.MerakiError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")

    scan_id = uuid.uuid4().hex[:12]
    scan_subnet = "Meraki: Dashboard"
    job = repositories.create_scan_job(db, scan_id, scan_subnet, [], False)
    job.scan_kind = "meraki"
    db.commit()

    for device in devices:
        repositories.upsert_device(db, device, scan_id)

    repositories.replace_links(db, scan_id, links)

    repositories.finish_scan_job(db, scan_id, {
        "subnet": "meraki-dashboard", "local_ip": "",
        "scanned_hosts": len(devices), "alive_hosts": len(devices),
        "device_count": len(devices), "snmp_identified": 0,
        "devices": devices, "connections": links,
    })

    return {"scan_id": scan_id, "device_count": len(devices),
            "links_found": len(links), "debug": debug}


# ── Sprint 9: Configuration Collection ────────────────────────────────────────

class ConfigCollectRequest(BaseModel):
    device_type: str = "switch"
    site_pattern: str = ""  # matches device hostname or site field
    limit: int = 50
    device_id: Optional[int] = None  # collect a single device only
    ssh_username: str = ""
    ssh_password: str = ""
    ssh_port: int = 22
    use_vault: bool = True  # fall back to vault SSH credentials when empty


@app.post("/api/inventory/collect-config")
def inventory_collect_config(req: ConfigCollectRequest,
                             user: dict = Depends(operator),
                             db: Session = Depends(get_db)):
    import config_collector

    if req.device_id is not None:
        devices = [repositories.get_device(db, req.device_id)]
        if devices[0] is None:
            raise HTTPException(status_code=404, detail="device not found")
    else:
        devices = repositories.get_devices_by_type(
            db, device_type=req.device_type, limit=req.limit,
            site_pattern=req.site_pattern)

    # Vault fallback: when no SSH creds are supplied, try each stored SSH
    # credential until authentication succeeds.
    vault_creds = repositories.vault_ssh_credentials(db) if req.use_vault else []

    def creds_for(device):
        if req.ssh_username:
            return [(req.ssh_username, req.ssh_password, req.ssh_port)]
        return [(c.username, c.password, 22) for c in vault_creds]

    results: list[dict] = []
    for d in devices:
        attempts = creds_for(d)
        outcome = None
        for username, password, port in attempts:
            if not username:
                continue
            try:
                cfg = config_collector.collect_config(
                    ip=d.ip, username=username, password=password, port=port)
                saved = repositories.save_device_config(
                    db, d.id, cfg["config_text"], config_type="running",
                    collected_by=user["username"])
                outcome = {
                    "device_id": d.id, "ip": d.ip, "hostname": d.hostname,
                    "status": "ok", "config_id": saved.id, "user": username,
                }
                break
            except config_collector.ConfigCollectorError as e:
                outcome = {
                    "device_id": d.id, "ip": d.ip, "hostname": d.hostname,
                    "status": "error", "error": str(e), "user": username,
                }
        if outcome is None:
            outcome = {
                "device_id": d.id, "ip": d.ip, "hostname": d.hostname,
                "status": "error", "error": "no SSH credentials available",
            }
        if outcome["status"] == "error":
            repositories.save_device_config(
                db, d.id, "", config_type="running", error=outcome["error"],
                collected_by=user["username"])
        results.append(outcome)

    success = sum(1 for r in results if r["status"] == "ok")
    return {
        "total": len(results),
        "success": success,
        "failed": len(results) - success,
        "results": results,
    }


class CatalystConfigCollectRequest(BaseModel):
    base_url: str
    username: str
    password: str
    device_type: str = "switch"
    site_pattern: str = ""
    limit: int = 50
    device_id: Optional[int] = None  # collect a single device only


@app.post("/api/catalyst/collect-config")
def catalyst_collect_config(req: CatalystConfigCollectRequest,
                            user: dict = Depends(operator),
                            db: Session = Depends(get_db)):
    """Collect running configs via the Catalyst config API (no per-device SSH)."""
    import catalyst

    if req.device_id is not None:
        devices = [repositories.get_device(db, req.device_id)]
        if devices[0] is None:
            raise HTTPException(status_code=404, detail="device not found")
    else:
        devices = repositories.get_devices_by_type(
            db, device_type=req.device_type, limit=req.limit,
            site_pattern=req.site_pattern)

    try:
        token = catalyst.authenticate(req.base_url, req.username, req.password)
    except catalyst.CatalystError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    results: list[dict] = []
    for d in devices:
        device_id = d.catalyst_id or ""
        if not device_id:
            results.append({
                "device_id": d.id, "ip": d.ip, "hostname": d.hostname,
                "status": "skipped", "error": "no catalyst_id on record",
            })
            continue
        try:
            cfg_text = catalyst.get_device_running_config(
                req.base_url, token, device_id)
            if cfg_text:
                saved = repositories.save_device_config(
                    db, d.id, cfg_text, config_type="running",
                    collected_by=user["username"])
                results.append({
                    "device_id": d.id, "ip": d.ip, "hostname": d.hostname,
                    "status": "ok", "config_id": saved.id,
                    "collected_by": user["username"],
                })
            else:
                err = "Catalyst returned empty running config"
                repositories.save_device_config(
                    db, d.id, "", error=err, collected_by=user["username"])
                results.append({
                    "device_id": d.id, "ip": d.ip, "hostname": d.hostname,
                    "status": "error", "error": err,
                })
        except catalyst.CatalystError as e:
            repositories.save_device_config(
                db, d.id, "", error=str(e), collected_by=user["username"])
            results.append({
                "device_id": d.id, "ip": d.ip, "hostname": d.hostname,
                "status": "error", "error": str(e),
                "collected_by": user["username"],
            })

    success = sum(1 for r in results if r["status"] == "ok")
    return {
        "total": len(results),
        "success": success,
        "failed": len(results) - success,
        "results": results,
    }


@app.get("/api/inventory/devices/{device_id}/configs",
         dependencies=[Depends(authenticated)])
def inventory_device_configs(device_id: int, db: Session = Depends(get_db)):
    configs = repositories.get_device_configs(db, device_id)
    return [c.to_dict() for c in configs]


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
