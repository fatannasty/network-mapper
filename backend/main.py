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


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


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
                      limit: int = Query(200, ge=1, le=1000),
                      db: Session = Depends(get_db)):
    devices = repositories.list_devices(db, device_type=device_type, vendor=vendor,
                                        site=site, limit=limit)
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
        "by_device_type": repositories.device_counts(db, Device.device_type),
        "by_vendor": repositories.device_counts(db, Device.vendor),
        "by_site": repositories.device_counts(db, Device.site),
        "recent_scans": [j.to_dict() for j in repositories.list_scan_jobs(db, limit=5)],
    }


@app.get("/api/topology", dependencies=[Depends(authenticated)])
def api_topology(scan_id: Optional[str] = Query(None), db: Session = Depends(get_db)):
    from models import Device, ScanJob

    if scan_id:
        job = db.get(ScanJob, scan_id)
        if job is None:
            raise HTTPException(status_code=404, detail="scan not found")
    else:
        jobs = repositories.list_scan_jobs(db, limit=1)
        if not jobs:
            return {"scan_id": None, "nodes": [], "links": []}
        job = jobs[0]

    devices = db.query(Device).filter(Device.last_scan_id == job.id).all()
    links = repositories.list_links(db, scan_id=job.id)

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

    return {"scan_id": job.id, "nodes": nodes, "links": [l.to_dict() for l in links]}


@app.get("/api/topology/path", dependencies=[Depends(authenticated)])
def api_topology_path(source: str = Query(...), target: str = Query(...),
                      db: Session = Depends(get_db)):
    """Return the shortest path between two device IPs using the topology graph."""
    jobs = repositories.list_scan_jobs(db, limit=1)
    if not jobs:
        raise HTTPException(status_code=404, detail="no topology data available")
    job = jobs[0]

    links = repositories.list_links(db, scan_id=job.id, limit=5000)

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
    repositories.create_scan_job(db, scan_id, "catalyst-center", [], False)

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

    results: list[dict] = []
    for d in devices:
        try:
            cfg = config_collector.collect_config(
                ip=d.ip,
                username=req.ssh_username,
                password=req.ssh_password,
                port=req.ssh_port,
            )
            saved = repositories.save_device_config(
                db, d.id, cfg["config_text"], config_type="running")
            results.append({
                "device_id": d.id,
                "ip": d.ip,
                "hostname": d.hostname,
                "status": "ok",
                "config_id": saved.id,
            })
        except config_collector.ConfigCollectorError as e:
            repositories.save_device_config(
                db, d.id, "", config_type="running", error=str(e))
            results.append({
                "device_id": d.id,
                "ip": d.ip,
                "hostname": d.hostname,
                "status": "error",
                "error": str(e),
            })
        except Exception as e:
            results.append({
                "device_id": d.id,
                "ip": d.ip,
                "hostname": d.hostname,
                "status": "error",
                "error": str(e),
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
