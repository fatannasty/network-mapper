"""Cisco Meraki Dashboard REST API client.

Provides device inventory and topology import from the Meraki cloud dashboard.

Authentication uses an API key (X-Cisco-Meraki-API-Key header) generated
from the Meraki dashboard under Organization > Settings > Dashboard API access.
"""

from __future__ import annotations

import json
import ssl
import urllib.request
from typing import Optional


class MerakiError(Exception):
    pass


def _request(base_url: str, api_key: str, endpoint: str,
             method: str = "GET", body: Optional[dict] = None,
             timeout: float = 30.0) -> dict | list:
    """Call a Meraki Dashboard API endpoint and return the parsed JSON."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    url = f"{base_url.rstrip('/')}/api/v1/{endpoint.lstrip('/')}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("X-Cisco-Meraki-API-Key", api_key)
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as e:
        raise MerakiError(f"Invalid JSON: {e}") from e
    except urllib.error.HTTPError as e:
        msg = e.read().decode()[:500] if e.fp else str(e)
        raise MerakiError(f"HTTP {e.code}: {msg}") from e
    except OSError as e:
        raise MerakiError(f"Connection failed: {e}") from e


def _paginate(base_url: str, api_key: str, endpoint: str,
              timeout: float = 60.0) -> list[dict]:
    """Fetch all pages of a paginated Meraki endpoint."""
    all_items: list[dict] = []
    per_page = 1000
    start_after = None
    for _ in range(50):  # safety limit
        sep = "&" if "?" in endpoint else "?"
        query = f"{endpoint}{sep}perPage={per_page}"
        if start_after:
            query += f"&startingAfter={start_after}"
        try:
            result = _request(base_url, api_key, query, timeout=timeout)
        except MerakiError:
            break
        if not isinstance(result, list) or not result:
            break
        all_items.extend(result)
        if len(result) < per_page:
            break
        start_after = result[-1].get("serial") or result[-1].get("id", "")
    return all_items


def get_organizations(base_url: str, api_key: str,
                      timeout: float = 30.0) -> list[dict]:
    """Return all organizations accessible by the API key."""
    return _request(base_url, api_key, "organizations", timeout=timeout)


def get_org_devices(base_url: str, api_key: str, org_id: str,
                    timeout: float = 60.0) -> list[dict]:
    """Return all devices in an organization (paginated)."""
    return _paginate(base_url, api_key, f"organizations/{org_id}/devices", timeout)


def get_org_networks(base_url: str, api_key: str, org_id: str,
                     timeout: float = 30.0) -> list[dict]:
    """Return all networks in an organization."""
    return _paginate(base_url, api_key, f"organizations/{org_id}/networks", timeout)


def get_device_lldp_cdp(base_url: str, api_key: str, serial: str,
                        timeout: float = 30.0) -> dict:
    """Return LLDP/CDP neighbor data for a single device."""
    return _request(base_url, api_key, f"devices/{serial}/lldpCdp", timeout=timeout)


def import_devices(base_url: str, api_key: str,
                   timeout: float = 120.0) -> tuple[list[dict], list[dict], dict]:
    """Fetch all org devices and LLDP/CDP neighbors, return (devices, links, debug).

    Normalizes Meraki devices into the standard device/link format used by the
    network mapper so they appear in inventory and topology.

    Devices are normalized to:
        {ip, hostname, vendor, model, device_type, site, ...}

    Links are normalized to:
        {source, target, source_interface, target_interface, protocol}
    """
    errors: list[str] = []

    try:
        orgs = get_organizations(base_url, api_key, timeout=timeout)
    except MerakiError as e:
        raise MerakiError(f"Failed to list organizations: {e}") from e

    if not orgs:
        raise MerakiError("No organizations accessible by this API key")

    all_devices: list[dict] = []
    all_raw_devices: list[dict] = []
    all_links: list[dict] = []
    skipped_no_ip = 0

    for org in orgs:
        org_id = str(org.get("id", ""))
        org_name = org.get("name", "")
        try:
            raw_devices = get_org_devices(base_url, api_key, org_id, timeout=timeout)
        except MerakiError as e:
            errors.append(f"Org {org_name}: {e}")
            continue
        all_raw_devices.extend(raw_devices)

        for device in raw_devices:
            ip = device.get("lanIp", "") or device.get("managementIp", "") or ""
            if not ip:
                skipped_no_ip += 1
                continue

            serial = device.get("serial", "")
            hostname = device.get("name", "") or serial
            model = device.get("model", "")
            network_name = device.get("networkName", "") or ""
            tags = device.get("tags", [])

            # Classify by model prefix
            device_type = "unknown"
            if model:
                prefix = model[:2].upper()
                if prefix == "MR":
                    device_type = "accesspoint"
                elif prefix == "MS":
                    device_type = "switch"
                elif prefix == "MX":
                    device_type = "firewall"
                elif prefix == "MG":
                    device_type = "cellular-gateway"
                elif prefix == "MV":
                    device_type = "camera"
                elif prefix == "MT":
                    device_type = "sensor"

            all_devices.append({
                "ip": ip,
                "hostname": hostname,
                "vendor": "Cisco Meraki",
                "model": model,
                "device_type": device_type,
                "site": network_name,
                "confidence": 5,
                "open_ports": [],
                "snmp_community": "",
                "snmp_identified": False,
                "interfaces": [],
                "neighbors": [],
                "_serial": serial,
                "_org": org_name,
            })

        # Fetch LLDP/CDP data for each device with a LAN IP
        ip_by_serial: dict[str, dict] = {d["_serial"]: d for d in all_devices if d.get("_org") == org_name}
        for serial, dev in ip_by_serial.items():
            try:
                lldp_data = get_device_lldp_cdp(base_url, api_key, serial, timeout=timeout)
            except MerakiError:
                continue

            # lldpCdp returns {"ports": {"wan1": {"lldp": {...}, "cdp": {...}}, ...}}
            ports = lldp_data.get("ports", {})
            if not isinstance(ports, dict):
                continue

            for port_name, port_data in ports.items():
                if not isinstance(port_data, dict):
                    continue

                # Try LLDP first, then CDP
                for proto in ("lldp", "cdp"):
                    neighbor = port_data.get(proto, {})
                    if not isinstance(neighbor, dict):
                        continue
                    remote_name = neighbor.get("systemName", "") or neighbor.get("deviceId", "")
                    remote_port = neighbor.get("portId", "") or neighbor.get("devicePort", "")
                    remote_ip = neighbor.get("managementAddress", "") or neighbor.get("address", "")

                    if not remote_name and not remote_ip:
                        continue

                    all_links.append({
                        "source": dev["ip"],
                        "target": remote_ip or remote_name,
                        "source_interface": port_name,
                        "target_interface": remote_port,
                        "protocol": proto,
                        "source_hostname": dev["hostname"],
                        "target_hostname": remote_name,
                    })

    debug = {
        "organizations": len(orgs),
        "raw_devices": len(all_raw_devices),
        "devices": len(all_devices),
        "links": len(all_links),
        "skipped_no_ip": skipped_no_ip,
        "errors": errors,
    }
    return all_devices, all_links, debug


def test_connection(base_url: str, api_key: str,
                    timeout: float = 30.0) -> dict:
    """Test connectivity and return org count + device count without importing."""
    orgs = get_organizations(base_url, api_key, timeout=timeout)
    total_devices = 0
    for org in orgs[:5]:  # limit to first 5 orgs for test
        org_id = str(org.get("id", ""))
        try:
            devices = get_org_devices(base_url, api_key, org_id, timeout=timeout)
            total_devices += len(devices)
        except MerakiError:
            continue
    return {
        "connected": True,
        "organizations": len(orgs),
        "device_count": total_devices,
    }
