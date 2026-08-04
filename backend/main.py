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
                                  exclude_pcs=req.exclude_pcs, snmpv3=snmpv3_dict)
    except ValueError as exc:
        repositories.fail_scan_job(db, scan_id, str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    for device in result["devices"]:
        if req.site:
            device["site"] = req.site
        repositories.upsert_device(db, device, scan_id)

    repositories.finish_scan_job(db, scan_id, result)
    return DiscoverResponse(scan_id=scan_id, **result)


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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
