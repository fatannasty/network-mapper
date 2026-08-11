"""VMware VeloCloud SD-WAN Orchestrator REST API client.

Provides edge inventory import with site/link data for Sprint 13 data quality.
"""

from __future__ import annotations

import json
import ssl
import urllib.request
from typing import Optional


class VeloCloudError(Exception):
    pass


def _request(base_url: str, token: str, endpoint: str,
             body: Optional[dict] = None, timeout: float = 30.0) -> dict | list:
    """Call a VeloCloud Orchestrator REST endpoint and return the parsed JSON."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    url = f"{base_url.rstrip('/')}/portal/rest/{endpoint.lstrip('/')}"
    data = json.dumps(body or {}).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Authorization", f"Token {token}")
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as e:
        raise VeloCloudError(f"Invalid JSON: {e}") from e
    except urllib.error.HTTPError as e:
        msg = e.read().decode()[:500] if e.fp else str(e)
        raise VeloCloudError(f"HTTP {e.code}: {msg}") from e
    except OSError as e:
        raise VeloCloudError(f"Connection failed: {e}") from e


def authenticate(base_url: str, username: str, password: str,
                 timeout: float = 30.0) -> str:
    """Authenticate with VeloCloud Orchestrator and return a token.

    Tries the enterprise login endpoint. Returns the auth token string.
    """
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    url = f"{base_url.rstrip('/')}/portal/rest/login/enterpriseLogin"
    body = json.dumps({
        "username": username,
        "password": password,
    }).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        msg = e.read().decode()[:500] if e.fp else str(e)
        raise VeloCloudError(f"Authentication failed (HTTP {e.code}): {msg}") from e
    except OSError as e:
        raise VeloCloudError(f"Connection failed: {e}") from e

    token = data.get("token") or data.get("enterpriseToken") or ""
    if not token:
        raise VeloCloudError(f"No token in response: {json.dumps(data)[:300]}")
    return token


def get_edges(base_url: str, token: str, timeout: float = 60.0) -> list[dict]:
    """Return all enterprise edges with site info and recent WAN links.

    The ``with`` array requests embedded site objects and per-edge WAN link
    data so a single call returns everything needed for device matching,
    site attribution, and interface extraction.
    """
    body = {"with": ["site", "recentLinks"]}
    result = _request(base_url, token, "enterprise/getEnterpriseEdges",
                      body=body, timeout=timeout)
    if isinstance(result, list):
        return result
    if isinstance(result, dict) and "error" in result:
        raise VeloCloudError(f"API error: {result['error']}")
    return []


def get_edge_detail(base_url: str, token: str, edge_id: int,
                    timeout: float = 30.0) -> dict:
    """Return a single edge with full detail including WAN interfaces."""
    return _request(base_url, token, "edge/getEdge",
                    body={"id": edge_id}, timeout=timeout)


def get_edge_config(base_url: str, token: str, edge_id: int,
                    timeout: float = 30.0) -> list[dict]:
    """Return the configuration stack for an edge."""
    return _request(base_url, token, "edge/getEdgeConfigurationStack",
                    body={"edgeId": edge_id}, timeout=timeout)


def import_edges(base_url: str, username: str, password: str,
                 timeout: float = 60.0) -> tuple[list[dict], list[dict], dict]:
    """Authenticate, fetch edges, return (devices, links, debug).

    Normalizes VeloCloud edges into the standard device/link format used by
    the network mapper so they appear in inventory and topology.

    Devices are normalized to:
        {ip, hostname, vendor, model, device_type, site, ...}

    Links are normalized to:
        {source, target, source_interface, target_interface, protocol}
    """
    token = authenticate(base_url, username, password, timeout=timeout)

    errors: list[str] = []
    try:
        raw_edges = get_edges(base_url, token, timeout=timeout)
    except VeloCloudError as e:
        errors.append(f"Edge fetch failed: {e}")
        raw_edges = []

    devices: list[dict] = []
    links: list[dict] = []
    skipped_no_ip = 0

    for edge in raw_edges:
        # Extract IP from various VeloCloud fields
        ip = (
            edge.get("managementIPAddress", {}).get("address", "")
            if isinstance(edge.get("managementIPAddress"), dict)
            else str(edge.get("managementIPAddress") or "")
        )
        if not ip:
            ip = edge.get("managementIP", "") or edge.get("ipAddress", "") or ""
        if not ip:
            # Try interfaces for a LAN IP
            for iface in edge.get("interfaces", []):
                if isinstance(iface, dict):
                    ip_list = iface.get("ipAddress", [])
                    if isinstance(ip_list, list) and ip_list:
                        ip = ip_list[0]
                        break
                    elif isinstance(ip_list, str) and ip_list:
                        ip = ip_list
                        break
        if not ip:
            skipped_no_ip += 1
            continue

        hostname = edge.get("name", "") or edge.get("hostname", "") or edge.get("description", "")
        site_name = ""
        site_info = edge.get("site", {})
        if isinstance(site_info, dict):
            site_name = site_info.get("name", "") or site_info.get("siteName", "")

        devices.append({
            "ip": ip,
            "hostname": hostname,
            "vendor": "VMware VeloCloud",
            "model": edge.get("modelNumber", "") or edge.get("edgeModelNumber", ""),
            "device_type": "velocloud-edge",
            "site": site_name,
            "confidence": 5,
            "open_ports": [],
            "snmp_community": "",
            "snmp_identified": False,
            "interfaces": [],
            "neighbors": [],
            "_id": str(edge.get("id", "")),
        })

    # Build links from edge-to-edge links reported by VeloCloud
    edge_by_id: dict[str, dict] = {}
    for d in devices:
        edge_by_id[d["_id"]] = d

    for edge in raw_edges:
        edge_id = str(edge.get("id", ""))
        src_dev = edge_by_id.get(edge_id)
        if not src_dev:
            continue

        # recentLinks contains link data to other edges
        recent_links = edge.get("recentLinks", [])
        if not isinstance(recent_links, list):
            continue

        for link in recent_links:
            if not isinstance(link, dict):
                continue
            link_type = link.get("linkType", "")
            state = link.get("state", "")
            # Only include active or recently active links
            if state not in ("good", "steady", "active", ""):
                continue

            remote_ip = link.get("remoteIP", "") or link.get("peerIP", "")
            if not remote_ip:
                continue

            local_iface = link.get("interface", "") or link.get("internalName", "")
            remote_iface = link.get("remoteInterface", "")

            links.append({
                "source": src_dev["ip"],
                "target": remote_ip,
                "source_interface": local_iface,
                "target_interface": remote_iface or "",
                "protocol": "velocloud",
                "source_hostname": src_dev["hostname"],
                "target_hostname": "",
            })

    debug = {
        "raw_edges": len(raw_edges),
        "devices": len(devices),
        "links": len(links),
        "skipped_no_ip": skipped_no_ip,
        "errors": errors,
    }
    return devices, links, debug


def test_connection(base_url: str, username: str, password: str,
                    timeout: float = 30.0) -> dict:
    """Test connectivity and return edge count without importing."""
    token = authenticate(base_url, username, password, timeout=timeout)
    edges = get_edges(base_url, token, timeout=timeout)
    return {
        "connected": True,
        "edge_count": len(edges),
        "sample": edges[0] if edges else None,
    }
