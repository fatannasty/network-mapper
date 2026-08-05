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
            return json.loads(resp.read().decode()) if resp.status < 300 else {}
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
                    timeout: float = 15.0) -> dict:
    """Test connectivity and return device count without importing."""
    token = authenticate(base_url, username, password, timeout=timeout)
    base = _resolve_base(base_url)
    devices = get_devices(base, token, limit=1, timeout=timeout)
    all_devices = get_devices(base, token, limit=500, timeout=timeout)
    return {
        "connected": True,
        "device_count": len(all_devices),
        "sample": devices[0] if devices else None,
    }


def get_devices(base_url: str, token: str, limit: int = 1000,
                timeout: float = 60.0) -> list[dict]:
    """Fetch all network devices from Catalyst Center."""
    base = _resolve_base(base_url)
    url = f"{base}/dna/intent/api/v1/network-device"

    # Try offset=0 first (newer API), fallback to offset=1 (classic)
    for offset in (0, 1):
        try:
            data = _request(f"{url}?limit={limit}&offset={offset}", token, timeout=timeout)
            devices = data.get("response", [])
            if devices:
                return devices
        except CatalystError:
            continue

    return []


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


def import_devices(base_url: str, username: str, password: str,
                   timeout: float = 120.0) -> tuple[list[dict], list[dict]]:
    """Authenticate, fetch devices and topology, return (devices, links).

    Devices are normalized to our standard dict format:
        {ip, hostname, vendor, model, device_type, interfaces, ...}

    Links are normalized to:
        {source, target, source_interface, target_interface, protocol}
    """
    token = authenticate(base_url, username, password, timeout=timeout)

    try:
        raw_devices = get_devices(base_url, token, timeout=timeout)
    except CatalystError as e:
        raise CatalystError(f"Failed to fetch devices: {e}") from e

    errors: list[str] = []
    try:
        raw_topology = get_physical_topology(base_url, token, timeout=timeout)
    except CatalystError as e:
        errors.append(f"Topology fetch failed: {e}")
        raw_topology: list[dict] = []

    # Map device IDs to IPs for topology link resolution
    device_by_id: dict[str, dict] = {}
    for d in raw_devices:
        device_by_id[d["id"]] = d

    devices: list[dict] = []
    for d in raw_devices:
        ip = d.get("managementIpAddress", "") or d.get("ipAddress", "")
        if not ip:
            continue

        hostname = d.get("hostname", "") or d.get("dnsName", "")
        family = (d.get("family", "") or "").lower()
        typ = d.get("type", "") or ""
        device_type = ""

        if "switch" in typ.lower() or "switch" in family:
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
        src = link.get("source", "")
        tgt = link.get("target", "")
        if not src or not tgt:
            continue
        src_dev = device_by_id.get(src, {})
        tgt_dev = device_by_id.get(tgt, {})
        src_ip = src_dev.get("managementIpAddress", "") or src_dev.get("ipAddress", "")
        tgt_ip = tgt_dev.get("managementIpAddress", "") or tgt_dev.get("ipAddress", "")
        if not src_ip or not tgt_ip:
            continue

        links.append({
            "source": src_ip,
            "target": tgt_ip,
            "source_interface": link.get("startPortName", ""),
            "target_interface": link.get("endPortName", ""),
            "protocol": link.get("linkType", "unknown").lower(),
            "source_hostname": src_dev.get("hostname", ""),
            "target_hostname": tgt_dev.get("hostname", ""),
        })

    return devices, links
