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
    """Authenticate with Catalyst Center and return a token."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    auth = base64.b64encode(f"{username}:{password}".encode()).decode()
    url = f"{base_url.rstrip('/')}/dna/system/api/v1/auth/token"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Basic {auth}")

    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            data = json.loads(resp.read().decode())
            token = data.get("Token", "")
            if not token:
                raise CatalystError("No token in response")
            return token
    except urllib.error.HTTPError as e:
        msg = e.read().decode()[:500] if e.fp else str(e)
        raise CatalystError(f"Auth failed (HTTP {e.code}): {msg}") from e
    except OSError as e:
        raise CatalystError(f"Connection failed: {e}") from e


def get_devices(base_url: str, token: str, limit: int = 1000,
                timeout: float = 60.0) -> list[dict]:
    """Fetch all network devices from Catalyst Center."""
    url = f"{base_url.rstrip('/')}/dna/intent/api/v1/network-device"
    params = f"?limit={limit}&offset=1"
    data = _request(f"{url}{params}", token, timeout=timeout)
    devices = data.get("response", [])
    return devices


def get_physical_topology(base_url: str, token: str,
                          timeout: float = 60.0) -> list[dict]:
    """Fetch physical topology links from Catalyst Center."""
    url = f"{base_url.rstrip('/')}/dna/intent/api/v1/topology/physical-topology"
    data = _request(url, token, timeout=timeout)
    return data.get("response", {}).get("links", [])


def get_device_detail(base_url: str, token: str, device_id: str,
                      timeout: float = 30.0) -> dict:
    """Fetch detailed info for a single device."""
    url = f"{base_url.rstrip('/')}/dna/intent/api/v1/network-device/{device_id}"
    data = _request(url, token, timeout=timeout)
    return data.get("response", {})


def get_device_interfaces(base_url: str, token: str, device_id: str,
                          timeout: float = 30.0) -> list[dict]:
    """Fetch interfaces for a device."""
    url = f"{base_url.rstrip('/')}/dna/intent/api/v1/interface"
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

    raw_devices = get_devices(base_url, token, timeout=timeout)
    raw_topology = get_physical_topology(base_url, token, timeout=timeout)

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
