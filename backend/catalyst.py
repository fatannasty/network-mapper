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
                timeout: float = 60.0, extra_params: str = "") -> list[dict]:
    """Fetch all network devices from Catalyst Center.

    If extra_params is given (e.g. 'platformId=VeloCloud'), it is appended to
    the query string so Catalyst Center does the filtering server-side.
    """
    base = _resolve_base(base_url)
    url = f"{base}/dna/intent/api/v1/network-device"

    all_devices: list[dict] = []
    offset = 1
    last_error = ""
    while True:
        query = f"limit={limit}&offset={offset}"
        if extra_params:
            query += "&" + extra_params
        try:
            data = _request(f"{url}?{query}", token, timeout=timeout)
        except CatalystError as e:
            if last_error and offset > 1:
                break  # partial page failure: keep what we have
            last_error = f"offset={offset}: {e}"
            if offset > 1:
                break
            # Try offset=0 fallback (newer API) once
            try:
                data = _request(f"{url}?limit={limit}&offset=0"
                                + (f"&{extra_params}" if extra_params else ""),
                                token, timeout=timeout)
                devices = data.get("response", [])
                if devices:
                    return devices
            except CatalystError as e2:
                last_error = f"offset=0: {e2}"
            break

        devices = data.get("response", [])
        if not devices:
            break
        all_devices.extend(devices)
        if len(devices) < limit:
            break
        offset += limit

    if all_devices:
        return all_devices
    raise CatalystError(f"Failed to fetch devices from {base}: {last_error or 'empty response'}")


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
        name = (
            s.get("name")
            or s.get("siteNameHierarchy")
            or s.get("groupNameHierarchy")
            or ""
        )
        hier = (
            s.get("siteNameHierarchy")
            or s.get("groupNameHierarchy")
            or s.get("siteHierarchy")
            or name
        )
        site_id = str(s.get("id") or s.get("siteId") or "")
        if name and site_id and site_id not in seen:
            seen.add(site_id)
            sites.append({
                "name": name,
                "hierarchy": hier,
                "hierarchy_ids": s.get("siteHierarchy", "") or s.get("groupNameHierarchy", ""),
                "site_id": site_id,
            })

    sites.sort(key=lambda x: x["hierarchy"] or x["name"])

    # Raw samples for debugging
    samples = []
    for s in raw_sites[:5]:
        samples.append({
            "name": s.get("name"),
            "siteNameHierarchy": s.get("siteNameHierarchy"),
            "groupNameHierarchy": s.get("groupNameHierarchy"),
            "siteHierarchy": s.get("siteHierarchy"),
            "id": str(s.get("id", ""))[:12],
            "siteId": str(s.get("siteId", ""))[:12],
            "type": s.get("siteType", s.get("groupType", s.get("type", ""))),
            "parentId": str(s.get("parentId", ""))[:12],
            "all_keys": sorted(s.keys())[:30],
        })

    return {
        "sites": sites,
        "debug": {
            "raw_count": len(raw_sites),
            "parsed": len(sites),
            "samples": samples,
        },
    }


def _extract_member_ids(data: dict) -> set[str]:
    """Pull device IDs out of a membership/site-member API response."""
    ids: set[str] = set()
    resp = data.get("response", data)
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
    return ids


def get_site_members(base_url: str, token: str, site_id: str,
                     timeout: float = 30.0) -> set[str]:
    """Return network-device IDs assigned to a site.

    Tries both the membership API and the network-device API filtered by
    siteId (which mirrors the Catalyst UI's per-location device view).
    Results are unioned so we never under-import a site.
    """
    base = _resolve_base(base_url)

    ids: set[str] = set()
    for url in (
        f"{base}/dna/intent/api/v1/membership/{site_id}?limit=500",
        f"{base}/dna/intent/api/v1/network-device?siteId={site_id}&limit=500",
    ):
        try:
            data = _request(url, token, timeout=timeout)
        except Exception:
            continue
        ids.update(_extract_member_ids(data))

    return ids


def debug_site_membership(base_url: str, username: str, password: str,
                          site_id: str, timeout: float = 30.0) -> dict:
    """Dump raw responses from the membership APIs for a site (debugging)."""
    token = authenticate(base_url, username, password, timeout=timeout)
    base = _resolve_base(base_url)
    urls = [
        f"{base}/dna/intent/api/v1/membership/{site_id}?limit=500",
        f"{base}/dna/intent/api/v1/site-member/{site_id}/member?memberType=networkdevice&limit=500",
        f"{base}/dna/intent/api/v1/network-device?siteId={site_id}&limit=500",
    ]

    results = []
    for url in urls:
        entry: dict = {"url": url, "error": None, "status": None, "raw": None,
                       "member_ids_count": 0, "member_id_sample": []}
        try:
            data = _request(url, token, timeout=timeout)
            entry["status"] = "ok"
            # Truncate deeply to keep the response readable
            entry["raw"] = _truncate_json(data, depth=3, max_items=20)
            m = _extract_member_ids(data)
            entry["member_ids_count"] = len(m)
            entry["member_id_sample"] = sorted(m)[:5]
        except Exception as e:
            entry["status"] = "error"
            entry["error"] = str(e)
        results.append(entry)

    parsed = None
    try:
        parsed = {
            "ids": sorted(get_site_members(base_url, token, site_id, timeout=timeout)),
        }
    except Exception as e:
        parsed = {"ids": [], "error": str(e)}

    return {"site_id": site_id, "endpoints": results, "parsed": parsed}


def _truncate_json(obj, depth: int = 0, max_items: int = 20):
    """Deeply truncate a JSON structure to keep it readable for debug output."""
    if depth > 3:
        return "..."
    if isinstance(obj, dict):
        out = {}
        for i, (k, v) in enumerate(obj.items()):
            if i >= max_items:
                out["..."] = f"{len(obj) - max_items} more keys"
                break
            out[k] = _truncate_json(v, depth + 1, max_items)
        return out
    if isinstance(obj, list):
        out = [_truncate_json(v, depth + 1, max_items) for v in obj[:max_items]]
        if len(obj) > max_items:
            out.append(f"... {len(obj) - max_items} more")
        return out
    if isinstance(obj, str) and len(obj) > 200:
        return obj[:200] + "..."
    return obj


def get_device_neighbors(base_url: str, token: str, device_id: str,
                         timeout: float = 30.0, max_interfaces: int = 500) -> list[dict]:
    """Fetch CDP/LLDP neighbors for a device via per-interface lookup.

    Returns a list of neighbor dicts with keys:
        {neighbor_device, neighbor_port, local_port, neighbor_ip}
    """
    base = _resolve_base(base_url)
    neighbors: list[dict] = []

    # 1. Get the device's interfaces
    try:
        data = _request(f"{base}/dna/intent/api/v1/interface?deviceId={device_id}&limit=500",
                        timeout=timeout, token=token)
    except CatalystError:
        return neighbors
    interfaces = data.get("response", [])
    if not isinstance(interfaces, list):
        return neighbors

    for iface in interfaces[:max_interfaces]:
        if_uuid = iface.get("id") or iface.get("interfaceId") or iface.get("instanceUuid")
        if not if_uuid:
            continue
        local_port = (iface.get("portName") or iface.get("interfaceName")
                      or iface.get("name") or "")
        try:
            nd = _request(
                f"{base}/dna/intent/api/v1/network-device/{device_id}"
                f"/interface/{if_uuid}/neighbor",
                token, timeout=timeout)
        except CatalystError:
            continue
        resp = nd.get("response", [])
        if isinstance(resp, dict):
            resp = [resp]
        if not isinstance(resp, list):
            continue
        for r in resp:
            neighbor_device = (r.get("neighborDevice")
                               or r.get("deviceName")
                               or r.get("hostname") or "")
            neighbor_port = (r.get("neighborPort")
                             or r.get("portId")
                             or r.get("remotePort") or "")
            if not neighbor_device and not neighbor_port:
                continue
            neighbors.append({
                "neighbor_device": neighbor_device,
                "neighbor_port": neighbor_port,
                "local_port": local_port,
                "neighbor_ip": "",
            })

    return neighbors


def import_devices(base_url: str, username: str, password: str,
                   timeout: float = 120.0, site_name: str = "",
                   site_id: str = "", device_filter: str = "") -> tuple[list[dict], list[dict], dict]:
    """Authenticate, fetch devices and topology, return (devices, links, debug).

    If site_name is given, filters devices by case-insensitive substring match
    on siteName or siteHierarchy, and keeps only topology links between matching devices.

    If device_filter is given, only devices whose hostname, platformId, type,
    family or management IP contains the term are imported, along with all links
    touching them.

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

    # Site filter: union of membership API matches + device site-field matches.
    # The membership endpoint only returns directly-assigned devices, while
    # Catalyst inventory records carry siteHierarchy/siteId/locationName for
    # devices that live under the site's hierarchy. Match either so we never
    # under-import a site.
    membership_applied = False
    resolved_site_count = 0
    membership_ids_count = 0
    site_filter_requested = bool(site_id or site_name)
    if site_filter_requested and raw_devices:
        # Resolve the site to UUIDs. site_id may be empty for state-only picks,
        # so match the readable path (site_name) against the site tree first.
        related_ids = set()
        if site_id:
            related_ids.add(site_id)
        try:
            site_result = get_sites(base_url, token, timeout=30.0)
            if site_name:
                terms = [t.strip().lower() for t in site_name.replace(">", "/").replace(",", "/").split("/") if t.strip()]
                for s in site_result["sites"]:
                    hay = ((s.get("hierarchy") or "") + "/" + (s.get("name") or "")).lower()
                    if all(t in hay for t in terms):
                        related_ids.add(s["site_id"])
            for s in site_result["sites"]:
                for rid in list(related_ids):
                    if s["site_id"] != rid and rid in (s.get("hierarchy_ids") or ""):
                        related_ids.add(s["site_id"])
        except Exception as e:
            errors.append(f"Site/child lookup skipped: {e}")

        member_ids: set[str] = set()
        site_ids_to_query = list(related_ids)[:5]
        skipped_sites = len(related_ids) - len(site_ids_to_query)
        if skipped_sites > 0:
            errors.append(f"Site filter resolved {len(related_ids)} sites; querying first 5")
        for sid in site_ids_to_query:
            member_ids.update(get_site_members(base_url, token, sid, timeout=15.0))

        resolved_site_count = len(related_ids)
        membership_ids_count = len(member_ids)

        before = len(raw_devices)
        terms = [t.strip().lower() for t in site_name.replace(">", "/").replace(",", "/").split("/") if t.strip()] if site_name else []
        leaf_term = terms[-1] if terms else ""
        uuids = [str(x) for x in related_ids]
        kept: list[dict] = []
        for d in raw_devices:
            did = str(d.get("id") or d.get("instanceUuid") or "")
            d_site_id = str(d.get("siteId") or "")
            d_site_hier = str(d.get("siteHierarchy") or "")
            loc_name = (d.get("locationName") or d.get("location") or "") or ""
            site_name_field = (d.get("siteName") or "") or ""
            hay = (d_site_hier + "/" + site_name_field + "/" + loc_name).lower()
            matches = did in member_ids
            matches = matches or (d_site_id and d_site_id in uuids)
            matches = matches or (d_site_hier and any(u in d_site_hier for u in uuids))
            matches = matches or (terms and all(t in hay for t in terms))
            matches = matches or (leaf_term and (leaf_term in loc_name.lower() or leaf_term == site_name_field.lower()))
            if matches:
                kept.append(d)
        raw_devices = kept
        errors.append(
            f"Site filter ({len(related_ids)} site(s), {len(member_ids)} members): "
            f"matched {len(raw_devices)} of {before} devices")
        membership_applied = True

    # Apply site name filter (fallback for environments where membership is unavailable)
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

    # Apply device filter (hostname/model/type/IP substring)
    if device_filter and raw_devices:
        term = device_filter.strip().lower()
        before = len(raw_devices)
        raw_devices = [
            d for d in raw_devices
            if term in (d.get("hostname", "") or "").lower()
            or term in (d.get("platformId", "") or "").lower()
            or term in (d.get("type", "") or "").lower()
            or term in (d.get("family", "") or "").lower()
            or term in (d.get("managementIpAddress", "") or "").lower()
            or term in (d.get("ipAddress", "") or "").lower()
        ]
        errors.append(f"Device filter '{device_filter}': matched {len(raw_devices)} of {before} devices")

    # Map device IDs to IPs for topology link resolution
    device_by_id: dict[str, dict] = {}
    for d in raw_devices:
        device_by_id[str(d.get("id", d.get("instanceId", d.get("instanceUuid", ""))))] = d

    # Lazy import classifier to avoid circular dependency at module level
    from classifier import classify_from_platform

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
        platform = (d.get("platformId", "") or "")

        # Classify using shared rules (same device_type labels as SNMP scanner)
        cls = classify_from_platform(
            platform_id=platform, family=family, device_type=typ)
        device_type = cls.device_type

        # Vendor from softwareType or platformId
        vendor = d.get("softwareType", "") or ""
        if vendor in ("", "IOS-XE", "IOS", "IOS XE"):
            vendor = "Cisco"
        elif "meraki" in family or "meraki" in typ or "meraki" in platform.lower():
            vendor = "Cisco Meraki"

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
            "_id": d.get("id", ""),
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

    # Enrich with per-device CDP/LLDP neighbor links (helps SD-WAN edges and
    # devices missing from the physical/site topology). Hostname-based lookup.
    # Cap the work so large imports don't stall on hundreds of API calls.
    neighbor_links_added = 0
    max_enrich_devices = 30
    max_enrich_interfaces = 16
    enrich_skipped = 0
    if devices:
        ip_by_hostname: dict[str, str] = {}
        for dev in devices:
            if dev.get("hostname"):
                ip_by_hostname[dev["hostname"].lower()] = dev["ip"]

        existing = {(l["source"], l["target"]) for l in links}
        for dev in devices[:max_enrich_devices]:
            dev_id = dev.get("_id", "")
            if not dev_id:
                continue
            try:
                nb = get_device_neighbors(base_url, token, dev_id, timeout=timeout,
                                          max_interfaces=max_enrich_interfaces)
            except Exception:
                continue
            for n in nb:
                nhost = (n.get("neighbor_device") or "").lower()
                tgt_ip = ip_by_hostname.get(nhost, "")
                if not tgt_ip or tgt_ip == dev["ip"]:
                    continue
                pair = (dev["ip"], tgt_ip)
                if pair in existing:
                    continue
                existing.add(pair)
                links.append({
                    "source": dev["ip"],
                    "target": tgt_ip,
                    "source_interface": n.get("local_port", ""),
                    "target_interface": n.get("neighbor_port", ""),
                    "protocol": "cdp-lldp",
                    "source_hostname": dev.get("hostname", ""),
                    "target_hostname": n.get("neighbor_device", ""),
                })
                neighbor_links_added += 1
        if len(devices) > max_enrich_devices:
            enrich_skipped = len(devices) - max_enrich_devices

    debug = {
        "debug_sample": debug_sample,
        "skipped_no_ip": skipped_no_ip,
        "raw_devices": len(raw_devices),
        "raw_devices_fetched": raw_device_count_before,
        "raw_topology": len(raw_topology),
        "neighbor_links_added": neighbor_links_added,
        "neighbor_enrich_skipped": enrich_skipped,
        "resolved_site_count": resolved_site_count,
        "membership_ids_count": membership_ids_count,
        "errors": errors,
    }
    return devices, links, debug
