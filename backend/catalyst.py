"""Cisco Catalyst Center (DNA Center) REST API client.

Provides device inventory and physical topology import for Sprint 7.
"""

from __future__ import annotations

import base64
import json
import ssl
import time
import urllib.request
from typing import Optional


class CatalystError(Exception):
    pass


def _request(url: str, token: str, method: str = "GET",
             data: bytes | None = None, timeout: float = 30.0) -> dict:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("X-Auth-Token", token)
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            raw = resp.read().decode()
            if resp.status < 300:
                return json.loads(raw) if raw.strip() else {}
            raise CatalystError(f"HTTP {resp.status}: {raw[:500]}")
    except json.JSONDecodeError as e:
        raise CatalystError(f"Invalid JSON response: {e}") from e
    except urllib.error.HTTPError as e:
        msg = e.read().decode()[:500] if e.fp else str(e)
        raise CatalystError(f"HTTP {e.code}: {msg}") from e
    except OSError as e:
        raise CatalystError(f"Connection failed: {e}") from e


def authenticate(base_url: str, username: str, password: str,
                 timeout: float = 30.0) -> str:
    """Authenticate with Catalyst Center and return a token.

    Tries both the classic DNAC API path and the newer Catalyst 2.3.5+ path.
    """
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    auth = base64.b64encode(f"{username}:{password}".encode()).decode()
    base = base_url.rstrip("/")

    # Strip any path suffix the user might have included
    for suffix in ("/dna", "/api", "/dna/intent/api", "/dna/system/api"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break

    auth_paths = [
        f"{base}/dna/system/api/v1/auth/token",
        f"{base}/api/system/v1/auth/token",
        f"{base}/api/v1/auth/token",
        f"{base}/dna/intent/api/v1/auth/token",
    ]

    errors: list[str] = []
    for url in auth_paths:
        req = urllib.request.Request(url, method="POST")
        req.add_header("Authorization", f"Basic {auth}")
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")

        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                raw_body = resp.read().decode()
                data = json.loads(raw_body)
                token = data.get("Token") or data.get("token") or ""
                if token:
                    return token
                errors.append(f"{url}: HTTP {resp.status} — no token in: {raw_body[:200]}")
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:300] if e.fp else "(no body)"
            errors.append(f"{url}: HTTP {e.code} — {body}")
        except OSError as e:
            errors.append(f"{url}: {e}")

    raise CatalystError(
        f"Authentication failed trying {len(auth_paths)} endpoints.\n"
        + "\n".join(errors)
    )


def _resolve_base(base_url: str) -> str:
    """Strip extra path segments from the base URL."""
    base = base_url.rstrip("/")
    for suffix in ("/dna", "/api", "/dna/intent/api", "/dna/system/api", "/dna/intent/api/v1"):
        if base.endswith(suffix):
            return base[: -len(suffix)]
    return base


def test_connection(base_url: str, username: str, password: str,
                    timeout: float = 30.0) -> dict:
    """Test connectivity and return device count without importing."""
    token = authenticate(base_url, username, password, timeout=timeout)
    base = _resolve_base(base_url)
    devices = get_devices(base, token, limit=50, timeout=timeout)
    sample = devices[0] if devices else None
    return {
        "connected": True,
        "device_count": len(devices),
        "sample": sample,
    }


def get_devices(base_url: str, token: str, limit: int = 500,
                timeout: float = 60.0) -> list[dict]:
    """Fetch all network devices from Catalyst Center."""
    base = _resolve_base(base_url)
    url = f"{base}/dna/intent/api/v1/network-device"

    last_error = ""
    # Try offset=1 first (classic API), fallback to offset=0 (newer)
    for offset in (1, 0):
        try:
            data = _request(f"{url}?limit={limit}&offset={offset}", token, timeout=timeout)
            devices = data.get("response", [])
            if devices:
                return devices
            last_error = f"offset={offset}: empty response"
        except CatalystError as e:
            last_error = f"offset={offset}: {e}"

    raise CatalystError(f"Failed to fetch devices from {base}: {last_error}")


def get_physical_topology(base_url: str, token: str,
                          timeout: float = 60.0) -> list[dict]:
    """Fetch physical topology links from Catalyst Center."""
    base = _resolve_base(base_url)
    url = f"{base}/dna/intent/api/v1/topology/physical-topology"
    try:
        data = _request(url, token, timeout=timeout)
    except CatalystError:
        # Try alternative endpoint
        url2 = f"{base}/dna/intent/api/v1/topology/site-topology"
        data = _request(url2, token, timeout=timeout)

    resp = data.get("response", [])
    if isinstance(resp, dict):
        return resp.get("links", [])
    if isinstance(resp, list):
        return resp
    return []


def get_device_detail(base_url: str, token: str, device_id: str,
                      timeout: float = 30.0) -> dict:
    """Fetch detailed info for a single device."""
    base = _resolve_base(base_url)
    url = f"{base}/dna/intent/api/v1/network-device/{device_id}"
    data = _request(url, token, timeout=timeout)
    return data.get("response", {})


def get_device_interfaces(base_url: str, token: str, device_id: str,
                          timeout: float = 30.0) -> list[dict]:
    """Fetch interfaces for a device."""
    base = _resolve_base(base_url)
    url = f"{base}/dna/intent/api/v1/interface"
    params = f"?deviceId={device_id}"
    data = _request(f"{url}{params}", token, timeout=timeout)
    return data.get("response", [])


def get_sites(base_url: str, token: str, timeout: float = 30.0) -> dict:
    """Fetch site hierarchy and return state/city pairs.

    Returns {sites, debug} where sites is the list of {state, city, site_id}
    and debug includes raw info for troubleshooting.
    """
    base = _resolve_base(base_url)

    # Try multiple API paths
    urls = [
        f"{base}/dna/intent/api/v1/site",
        f"{base}/dna/intent/api/v1/site?type=area,building,floor",
    ]

    data = {}
    for url in urls:
        try:
            data = _request(url, token, timeout=timeout)
            break
        except Exception:
            continue

    raw_sites = data.get("response", [])
    if not raw_sites:
        return {"sites": [], "debug": {"raw_count": 0, "sample": [], "note": "No sites returned"}}

    # Show raw sample for debugging
    sample_raw = []
    for s in raw_sites[:3]:
        sample_raw.append({
            "name": s.get("name"),
            "siteHierarchy": s.get("siteHierarchy"),
            "id": s.get("id", "")[:12],
            "parentId": s.get("parentId", "")[:12],
            "type": s.get("siteType", s.get("groupType", s.get("type", "?"))),
        })

    # Build lookup
    by_id: dict[str, dict] = {}
    for s in raw_sites:
        sid = s.get("id", "")
        by_id[sid] = {
            "id": sid,
            "name": s.get("name", ""),
            "parentId": s.get("parentId", ""),
            "hierarchy": s.get("siteHierarchy", "") or s.get("name", ""),
            "type": (s.get("siteType") or s.get("groupType") or s.get("type") or "").lower(),
        }

    result: list[dict] = []
    for s in raw_sites:
        info = by_id.get(s.get("id", ""), {})
        parent = by_id.get(info.get("parentId", ""), {})
        typ = info.get("type", "")

        if "building" in typ or "floor" in typ:
            result.append({
                "state": parent.get("name", ""),
                "city": info.get("name", ""),
                "site_id": info.get("id", ""),
            })
        elif "area" in typ:
            state = info.get("name", "")
            for child in raw_sites:
                cinfo = by_id.get(child.get("id", ""), {})
                if cinfo.get("parentId") == info.get("id"):
                    ct = cinfo.get("type", "")
                    if "building" in ct or "floor" in ct:
                        result.append({
                            "state": state,
                            "city": cinfo.get("name", ""),
                            "site_id": cinfo.get("id", ""),
                        })

    # Sort and deduplicate
    result.sort(key=lambda x: (x["state"], x["city"]))
    deduped, seen = [], set()
    for r in result:
        key = (r["state"], r["city"])
        if r["city"] and key not in seen:
            seen.add(key)
            deduped.append(r)

    return {
        "sites": deduped,
        "debug": {
            "raw_count": len(raw_sites),
            "parsed_locations": len(deduped),
            "sample_raw": sample_raw,
        },
    }


def import_devices(base_url: str, username: str, password: str,
                   timeout: float = 120.0, site_name: str = "") -> tuple[list[dict], list[dict], dict]:
    """Authenticate, fetch devices and topology, return (devices, links, debug).

    If site_name is given, filters devices by case-insensitive substring match
    on siteName or siteHierarchy, and keeps only topology links between matching devices.

    Devices are normalized to our standard dict format:
        {ip, hostname, vendor, model, device_type, interfaces, ...}

    Links are normalized to:
        {source, target, source_interface, target_interface, protocol}
    """
    token = authenticate(base_url, username, password, timeout=timeout)

    errors: list[str] = []
    try:
        raw_devices = get_devices(base_url, token, timeout=timeout)
    except CatalystError as e:
        errors.append(f"Device fetch failed: {e}")
        raw_devices: list[dict] = []
    try:
        raw_topology = get_physical_topology(base_url, token, timeout=timeout)
    except CatalystError as e:
        errors.append(f"Physical topology failed: {e}")
        raw_topology: list[dict] = []

    # Also try site-topology (broader than physical, includes more links)
    site_links: list[dict] = []
    try:
        base = _resolve_base(base_url)
        st_url = f"{base}/dna/intent/api/v1/topology/site-topology"
        st_data = _request(st_url, token, timeout=timeout)
        st_resp = st_data.get("response", [])
        if isinstance(st_resp, dict):
            site_links = st_resp.get("links", [])
        elif isinstance(st_resp, list):
            site_links = st_resp
        errors.append(f"Site topology: {len(site_links)} links")
    except Exception as e:
        errors.append(f"Site topology skipped: {e}")

    # Merge topology sources
    raw_topology = list(raw_topology) + list(site_links)

    raw_device_count_before = len(raw_devices)

    # Collect debug sample BEFORE site filtering
    debug_sample = {}
    if raw_devices:
        d0 = raw_devices[0]
        debug_sample = {
            "keys": sorted(d0.keys()),
            "managementIpAddress": d0.get("managementIpAddress"),
            "ipAddress": d0.get("ipAddress"),
            "hostname": d0.get("hostname"),
            "type": d0.get("type"),
            "family": d0.get("family"),
            "reachabilityStatus": d0.get("reachabilityStatus"),
            "platformId": d0.get("platformId"),
            "softwareType": d0.get("softwareType"),
            "siteName": d0.get("siteName"),
            "siteHierarchy": d0.get("siteHierarchy"),
            "siteId": d0.get("siteId"),
        }
        # Collect available site names for reference
        site_samples = set()
        for d in raw_devices[:200]:
            s = d.get("siteName") or d.get("siteHierarchy") or ""
            if s:
                site_samples.add(s)
        if site_samples:
            debug_sample["available_sites_sample"] = sorted(site_samples)[:30]

    # Apply site filter
    if site_name and raw_devices:
        terms = [t.strip().lower() for t in site_name.replace("/", ",").split(",") if t.strip()]
        raw_devices = [
            d for d in raw_devices
            if any(
                term in (d.get("siteName", "") or "").lower()
                or term in (d.get("siteHierarchy", "") or "").lower()
                or term in (d.get("siteId", "") or "").lower()
                for term in terms
            )
        ]
        errors.append(f"Site filter '{site_name}' (terms: {terms}): matched {len(raw_devices)} of {raw_device_count_before} devices")

    # Map device IDs to IPs for topology link resolution
    device_by_id: dict[str, dict] = {}
    for d in raw_devices:
        device_by_id[str(d.get("id", d.get("instanceId", d.get("instanceUuid", ""))))] = d

    devices: list[dict] = []
    skipped_no_ip = 0
    for d in raw_devices:
        ip = (d.get("managementIpAddress") or d.get("ipAddress")
              or d.get("deviceIp") or d.get("networkDeviceIpAddress") or "")
        if not ip:
            skipped_no_ip += 1
            continue

        hostname = d.get("hostname", "") or d.get("dnsName", "")
        family = (d.get("family", "") or "").lower()
        typ = d.get("type", "") or ""
        device_type = ""

        if "access point" in typ.lower() or "ap" in family.lower():
            device_type = "access-point"
        elif "switch" in typ.lower() or "switch" in family:
            device_type = "switch"
        elif "router" in typ.lower() or "router" in family:
            device_type = "router"
        elif "firewall" in typ.lower() or "firewall" in family:
            device_type = "firewall"
        elif "wireless" in typ.lower() or "wireless" in family:
            device_type = "wireless-controller"

        devices.append({
            "ip": ip,
            "hostname": hostname,
            "vendor": d.get("softwareType", "") or "Cisco",
            "model": d.get("platformId", ""),
            "device_type": device_type,
            "confidence": 5,
            "open_ports": [161],
            "snmp_community": "",
            "snmp_identified": False,
            "interfaces": [],
            "neighbors": [],
        })

    # Build links from physical topology
    links: list[dict] = []
    for link in raw_topology:
        src = (link.get("source") or link.get("sourceDeviceId")
               or link.get("src") or link.get("networkElementA") or "")
        tgt = (link.get("target") or link.get("targetDeviceId")
               or link.get("dest") or link.get("networkElementB") or "")
        if not src or not tgt:
            continue
        # Try multiple field names for ports
        src_port = (link.get("startPortName") or link.get("sourcePort")
                     or link.get("interfaceA") or "")
        tgt_port = (link.get("endPortName") or link.get("targetPort")
                     or link.get("interfaceB") or "")
        src_dev = device_by_id.get(src, {})
        tgt_dev = device_by_id.get(tgt, {})
        src_ip = (src_dev.get("managementIpAddress") or src_dev.get("ipAddress")
                  or src_dev.get("deviceIp") or "")
        tgt_ip = (tgt_dev.get("managementIpAddress") or tgt_dev.get("ipAddress")
                  or tgt_dev.get("deviceIp") or "")
        if not src_ip or not tgt_ip:
            continue

        links.append({
            "source": src_ip,
            "target": tgt_ip,
            "source_interface": src_port,
            "target_interface": tgt_port,
            "protocol": link.get("linkType", "unknown").lower(),
            "source_hostname": src_dev.get("hostname", ""),
            "target_hostname": tgt_dev.get("hostname", ""),
        })

    debug = {
        "debug_sample": debug_sample,
        "skipped_no_ip": skipped_no_ip,
        "raw_devices": len(raw_devices),
        "raw_devices_fetched": raw_device_count_before,
        "raw_topology": len(raw_topology),
        "errors": errors,
    }
    return devices, links, debug
