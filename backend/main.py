"""FastAPI application for the Discovery, Inventory and RBAC API.

Endpoints:
    GET  /health                          - service health (public)
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
    GET  /api/inventory/credentials       - stored credentials (names only, authenticated)
    POST /api/inventory/credentials       - create credential (admin)
    DELETE /api/inventory/credentials/{id}- delete credential (admin)
    GET  /api/inventory/sites             - known sites (authenticated)
    POST /api/inventory/sites             - create site (admin)

Roles:
    admin    - everything
    operator - run scans, view inventory (no credential/user management)
    viewer   - read-only inventory access
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

import repositories
import scanner
from database import get_db, init_db

AUTH_PROTOCOLS = ("md5", "sha", "none")
PRIVACY_PROTOCOLS = ("aes", "des", "none")
ROLES = ("admin", "operator", "viewer")

# Experimental VeloCloud LAN-inference links. These connect an SD-WAN edge to
# every LAN device in an inferred broadcast domain, are unverified, and bleed
# across sites (a Montreal edge showing up in the Miami topology). Excluded
# from topology graphs so foreign Veloclouds never pollute a site view.
NON_TOPOLOGY_PROTOCOLS = ("velocloud-lan",)


def _keep_topology_link(link) -> bool:
    """True if a Link belongs in topology graphs (not experimental inference)."""
    return link.protocol not in NON_TOPOLOGY_PROTOCOLS


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    _rename_old_scans()
    yield


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

def _bearer(authorization: str = Header(default="")) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    return authorization[len("Bearer "):].strip()


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


# ── Auth ─────────────────────────────────────────────────────────────────────

@app.post("/api/auth/login")
def auth_login(req: LoginRequest, db: Session = Depends(get_db)):
    result = repositories.issue_token(db, req.username, req.password)
    if result is None:
        raise HTTPException(status_code=401, detail="invalid username or password")
    return result


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

@app.get("/api/inventory/devices", dependencies=[Depends(authenticated)])
def inventory_devices(device_type: Optional[str] = Query(None),
                      vendor: Optional[str] = Query(None),
                      site: Optional[str] = Query(None),
                      search: Optional[str] = Query(None),
                      limit: int = Query(200, ge=1, le=5000),
                      db: Session = Depends(get_db)):
    devices = repositories.list_devices(db, device_type=device_type, vendor=vendor,
                                        site=site, search=search, limit=limit)
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
        writer.writerow(["ip", "hostname", "config_type", "collected_at", "error"])
        for c in db.query(DeviceConfig).order_by(DeviceConfig.collected_at.desc()).all():
            writer.writerow([c.device.ip if c.device else "",
                             c.device.hostname if c.device else "",
                             c.config_type,
                             c.collected_at.isoformat() if c.collected_at else "",
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


@app.get("/api/topology", dependencies=[Depends(authenticated)])
def api_topology(scan_id: Optional[str] = Query(None), db: Session = Depends(get_db)):
    from models import Device, ScanJob

    if scan_id:
        job = db.get(ScanJob, scan_id)
        if job is None:
            raise HTTPException(status_code=404, detail="scan not found")
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
        from models import Link as LinkModel
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
        jobs = repositories.list_scan_jobs(db, limit=1)
        if not jobs:
            return {"scan_id": None, "nodes": [], "links": [], "scan_meta": None}
        job = jobs[0]
        devices = db.query(Device).filter(Device.last_scan_id == job.id).all()
        links = [l for l in repositories.list_links(db, scan_id=job.id) if _keep_topology_link(l)]

        # Same cross-scan link inclusion as the scan_id branch so the default
        # latest-scan view also shows connections discovered by older scans.
        from models import Link as LinkModel
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

    nodes: list[dict] = []
    seen: set[str] = set()
    for d in devices:
        nodes.append({
            "id": d.ip,
            "ip": d.ip,
            "hostname": d.hostname,
            "vendor": d.vendor,
            "model": d.model,
            "device_type": d.device_type,
        })
        seen.add(d.ip)
    for link in links:
        for ep in (link.endpoint_a, link.endpoint_b):
            if ep not in seen:
                nodes.append({"id": ep, "ip": ep, "hostname": "", "vendor": "",
                              "model": "", "device_type": "unknown"})
                seen.add(ep)

    return {
        "scan_id": job.id,
        "nodes": nodes,
        "links": [l.to_dict() for l in links],
        "scan_meta": {
            "subnet": job.subnet,
            "device_count": job.device_count,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "scan_kind": getattr(job, "scan_kind", None),
        },
    }


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


@app.post("/api/catalyst/import", dependencies=[Depends(operator)])
def catalyst_import(req: CatalystImportRequest, db: Session = Depends(get_db)):
    import catalyst

    try:
        devices, links, debug = catalyst.import_devices(
            req.base_url, req.username, req.password,
            site_name=req.site_name, site_id=req.site_id,
            device_filter=req.device_filter)
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


# ── Sprint 9: Configuration Collection ────────────────────────────────────────

class ConfigCollectRequest(BaseModel):
    device_type: str = "switch"
    site_pattern: str = ""  # matches device hostname or site field
    limit: int = 50
    ssh_username: str = ""
    ssh_password: str = ""
    ssh_port: int = 22
    use_vault: bool = True  # fall back to vault SSH credentials when empty


@app.post("/api/inventory/collect-config", dependencies=[Depends(operator)])
def inventory_collect_config(req: ConfigCollectRequest,
                              db: Session = Depends(get_db)):
    import config_collector

    devices = repositories.get_devices_by_type(
        db, device_type=req.device_type, limit=req.limit)

    if req.site_pattern:
        pat = req.site_pattern.lower()
        devices = [d for d in devices
                   if pat in (d.hostname or "").lower()
                   or pat in (d.site or "").lower()]

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
                    db, d.id, cfg["config_text"], config_type="running")
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
                db, d.id, "", config_type="running", error=outcome["error"])
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


@app.post("/api/catalyst/collect-config", dependencies=[Depends(operator)])
def catalyst_collect_config(req: CatalystConfigCollectRequest,
                             db: Session = Depends(get_db)):
    """Collect running configs via the Catalyst config API (no per-device SSH)."""
    import catalyst

    devices = repositories.get_devices_by_type(
        db, device_type=req.device_type, limit=req.limit)
    if req.site_pattern:
        pat = req.site_pattern.lower()
        devices = [d for d in devices
                   if pat in (d.hostname or "").lower() or pat in (d.site or "").lower()]

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
                    db, d.id, cfg_text, config_type="running")
                results.append({
                    "device_id": d.id, "ip": d.ip, "hostname": d.hostname,
                    "status": "ok", "config_id": saved.id,
                })
            else:
                err = "Catalyst returned empty running config"
                repositories.save_device_config(db, d.id, "", error=err)
                results.append({
                    "device_id": d.id, "ip": d.ip, "hostname": d.hostname,
                    "status": "error", "error": err,
                })
        except catalyst.CatalystError as e:
            repositories.save_device_config(db, d.id, "", error=str(e))
            results.append({
                "device_id": d.id, "ip": d.ip, "hostname": d.hostname,
                "status": "error", "error": str(e),
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
