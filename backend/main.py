"""FastAPI application for the Discovery and Classification MVP.

Endpoints:
    GET  /health                    - service health + local network info
    POST /api/discover              - run a subnet discovery scan, persist + return results
    GET  /api/inventory/devices     - list persisted devices (filters: type/vendor/site)
    GET  /api/inventory/devices/{id}- single device
    GET  /api/inventory/scans       - recent scan job history
    GET  /api/inventory/report      - inventory summary counts
    GET  /api/inventory/credentials - stored credentials (names only)
    GET  /api/inventory/sites       - known sites
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

import repositories
import scanner
from database import get_db, init_db


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Network Discovery API",
    version="0.2.0",
    description="NetBrain-style discovery and classification platform (Sprint 1-2)",
    lifespan=lifespan,
)


class DiscoverRequest(BaseModel):
    subnet: str
    communities: Optional[list[str]] = ["public"]
    exclude_pcs: bool = True
    site: Optional[str] = None


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


# ── Service ───────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "service": "network-discovery", "version": app.version,
            "local_ip": scanner.local_ip()}


# ── Discovery ─────────────────────────────────────────────────────────────────

@app.post("/api/discover", response_model=DiscoverResponse)
def api_discover(req: DiscoverRequest, db: Session = Depends(get_db)):
    scan_id = uuid.uuid4().hex[:12]
    repositories.create_scan_job(db, scan_id, req.subnet, req.communities or ["public"], req.exclude_pcs)
    try:
        result = scanner.discover(req.subnet, communities=req.communities, exclude_pcs=req.exclude_pcs)
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

@app.get("/api/inventory/devices")
def inventory_devices(device_type: Optional[str] = Query(None),
                      vendor: Optional[str] = Query(None),
                      site: Optional[str] = Query(None),
                      limit: int = Query(200, ge=1, le=1000),
                      db: Session = Depends(get_db)):
    devices = repositories.list_devices(db, device_type=device_type, vendor=vendor,
                                        site=site, limit=limit)
    return {"count": len(devices), "devices": [d.to_dict() for d in devices]}


@app.get("/api/inventory/devices/{device_id}")
def inventory_device(device_id: int, db: Session = Depends(get_db)):
    device = repositories.get_device(db, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="device not found")
    return device.to_dict()


@app.get("/api/inventory/scans")
def inventory_scans(limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    jobs = repositories.list_scan_jobs(db, limit=limit)
    return {"count": len(jobs), "scans": [j.to_dict() for j in jobs]}


@app.get("/api/inventory/report")
def inventory_report(db: Session = Depends(get_db)):
    from models import Device

    return {
        "total_devices": db.query(Device).count(),
        "by_device_type": repositories.device_counts(db, Device.device_type),
        "by_vendor": repositories.device_counts(db, Device.vendor),
        "by_site": repositories.device_counts(db, Device.site),
        "recent_scans": [j.to_dict() for j in repositories.list_scan_jobs(db, limit=5)],
    }


@app.get("/api/inventory/credentials")
def inventory_credentials(db: Session = Depends(get_db)):
    creds = repositories.list_credentials(db)
    return {"count": len(creds), "credentials": [c.to_dict() for c in creds]}


@app.get("/api/inventory/sites")
def inventory_sites(db: Session = Depends(get_db)):
    sites = repositories.list_sites(db)
    return {"count": len(sites), "sites": [s.to_dict() for s in sites]}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
