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
    """Fetch site hierarchy from Catalyst Center.

    Returns all site names and hierarchy paths as flat list plus debug info.
    """
    base = _resolve_base(base_url)

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
        # Return empty — sites are not configured
        return {"sites": [], "debug": {"raw_count": 0, "note": "No sites in API response"}}

    # Collect all site names and hierarchies regardless of type
    sites: list[dict] = []
    seen = set()
    for s in raw_sites:
        name = s.get("name", "")
        hier = s.get("siteHierarchy", "")
        if name and name not in seen:
            seen.add(name)
            sites.append({
                "name": name,
                "hierarchy": hier,
                "site_id": s.get("id", ""),
            })

    sites.sort(key=lambda x: x["hierarchy"] or x["name"])

    # Raw samples for debugging
    samples = []
    for s in raw_sites[:5]:
        samples.append({
            "name": s.get("name"),
            "hierarchy": s.get("siteHierarchy"),
            "type": s.get("siteType", s.get("groupType", s.get("type", ""))),
            "parentId": str(s.get("parentId", ""))[:12],
        })

    return {
        "sites": sites,
        "debug": {
            "raw_count": len(raw_sites),
            "parsed": len(sites),
            "samples": samples,
        },
    }


def get_site_members(base_url: str, token: str, site_id: str,
                     timeout: float = 30.0) -> set[str]:
    """Return network-device IDs assigned to a site (membership API)."""
    base = _resolve_base(base_url)
    urls = [
        f"{base}/dna/intent/api/v1/membership/{site_id}?limit=500",
        f"{base}/dna/intent/api/v1/site-member/{site_id}/member?memberType=networkdevice&limit=500",
    ]

    ids: set[str] = set()
    for url in urls:
        try:
            data = _request(url, token, timeout=timeout)
        except Exception:
            continue

        resp = data.get("response", data)
        # membership API: {"device": [{"response": [devices]}], "site": {...}}
        groups = []
        if isinstance(resp, dict):
            groups = resp.get("device", [])
        elif isinstance(data, dict) and "device" in data:
            groups = data.get("device", [])
        if isinstance(resp, list):
            for d in resp:
                did = str(d.get("instanceUuid") or d.get("id") or "")
                if did:
                    ids.add(did)
        for grp in groups:
            for d in grp.get("response", []):
                did = str(d.get("instanceUuid") or d.get("id") or "")
                if did:
                    ids.add(did)
        if ids:
            break

    return ids


def import_devices(base_url: str, username: str, password: str,
                   timeout: float = 120.0, site_name: str = "",
                   site_id: str = "") -> tuple[list[dict], list[dict], dict]:
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
            "hostname": d0.get("hostname"),
            "type": d0.get("type"),
            "family": d0.get("family"),
            "platformId": d0.get("platformId"),
            "softwareType": d0.get("softwareType"),
            "siteName": d0.get("siteName"),
            "siteHierarchy": d0.get("siteHierarchy"),
            "siteId": d0.get("siteId"),
            "location": d0.get("location"),
            "locationName": d0.get("locationName"),
        }
        # Collect available location/site names for reference
        loc_samples = set()
        for d in raw_devices[:500]:
            s = (d.get("locationName") or d.get("location")
                 or d.get("siteName") or d.get("siteHierarchy") or "")
            if s:
                loc_samples.add(s)
        if loc_samples:
            debug_sample["available_locations"] = sorted(loc_samples)[:50]

    # Site membership filter (preferred — works even when devices have no site fields)
    membership_applied = False
    if site_id and raw_devices:
        related_ids = [site_id]
        try:
            site_result = get_sites(base_url, token, timeout=timeout)
            for s in site_result["sites"]:
                if s["site_id"] != site_id and site_id in (s.get("hierarchy") or ""):
                    related_ids.append(s["site_id"])
        except Exception as e:
            errors.append(f"Child-site lookup skipped: {e}")

        member_ids: set[str] = set()
        for sid in related_ids[:30]:
            member_ids.update(get_site_members(base_url, token, sid, timeout=timeout))

        if member_ids:
            before = len(raw_devices)
            raw_devices = [
                d for d in raw_devices
                if str(d.get("id") or d.get("instanceUuid") or "") in member_ids
            ]
            errors.append(
                f"Site membership ({len(related_ids)} sites, {len(member_ids)} members): "
                f"matched {len(raw_devices)} of {before} devices")
            membership_applied = True
        else:
            errors.append(f"Site membership lookup for {len(related_ids)} sites returned no devices; "
                          f"falling back to name filter")

    # Apply site name filter (fallback)
    if site_name and raw_devices and not membership_applied:
        terms = [t.strip().lower() for t in site_name.replace("/", ",").split(",") if t.strip()]
        raw_devices = [
            d for d in raw_devices
            if any(
                term in (d.get("siteName", "") or "").lower()
                or term in (d.get("siteHierarchy", "") or "").lower()
                or term in (d.get("siteId", "") or "").lower()
                or term in (d.get("locationName", "") or "").lower()
                or term in (d.get("location", "") or "").lower()
                or term in (d.get("hostname", "") or "").lower()
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
        typ = (d.get("type", "") or "").lower()
        platform = (d.get("platformId", "") or "").lower()

        # Detect vendor
        vendor = d.get("softwareType", "") or ""
        if "meraki" in family or "meraki" in typ or "meraki" in platform:
            vendor = "Meraki"
        elif not vendor and "cisco" in family:
            vendor = "Cisco"

        # Detect device type from model prefix or family
        device_type = ""
        if "access point" in family or "ap" in family or typ.startswith("mr"):
            device_type = "access-point"
        elif "switch" in family or typ.startswith("ms"):
            device_type = "switch"
        elif "firewall" in family or "security" in family or typ.startswith("mx"):
            device_type = "firewall"
        elif "router" in family:
            device_type = "router"
        elif "wireless" in family or typ.startswith("wc") or "wlc" in typ:
            device_type = "wireless-controller"

        devices.append({
            "ip": ip,
            "hostname": hostname,
            "vendor": vendor,
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
