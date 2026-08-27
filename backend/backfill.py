"""Sprint 13: data-quality backfill jobs.

Runs in the request thread (synchronously) with a bounded thread pool so a
one-shot campaign doesn't need a queue — Redis/Celery stays deferred per the
Q3 decision. The vault's SNMP communities are used to walk IF-MIB (interfaces)
and LLDP/CDP (link validation) on the target device set.

All jobs return a summary dict with per-device results so the UI can render
progress/outcomes without extra state.
"""

from __future__ import annotations

import socket
from concurrent.futures import ThreadPoolExecutor, as_completed

from snmp import walk_if_table
from topology import collect_cdp_v2c, collect_lldp_v2c

DEFAULT_MAX_WORKERS = 25
DEFAULT_TIMEOUT = 8.0


# ── Interface walks ──────────────────────────────────────────────────────────

def _v3_kwargs(snmpv3: dict, timeout: float) -> dict:
    return {
        "username": snmpv3["username"],
        "auth_protocol": (snmpv3.get("auth_protocol") or "sha").lower(),
        "auth_password": snmpv3.get("auth_password", ""),
        "privacy_protocol": (snmpv3.get("privacy_protocol") or "none").lower(),
        "privacy_password": snmpv3.get("privacy_password") or snmpv3.get("auth_password", ""),
        "timeout": timeout,
    }


def walk_device_interfaces(device, communities: list[str], timeout: float = DEFAULT_TIMEOUT,
                           snmpv3: dict | None = None):
    """Walk IF-MIB + dot1q VLANs for one device (v2c or v3). Returns (device, interfaces, error)."""
    ip = device.get("ip", "")
    if not ip:
        return device, [], "no ip"
    try:
        if snmpv3:
            from snmpv3 import walk_if_table as v3_walk_if_table
            from vlan import walk_vlans_v3
            interfaces = v3_walk_if_table(ip, **_v3_kwargs(snmpv3, timeout))
            assignments = walk_vlans_v3(ip, snmpv3, timeout=timeout)
        else:
            interfaces = walk_if_table(ip, communities, timeout=timeout)
            from vlan import walk_vlans_v2c
            assignments = walk_vlans_v2c(ip, communities, timeout=timeout)
        for iface in interfaces:
            vlans = assignments.get(str(iface.get("ifIndex", "")))
            if vlans:
                iface["vlanId"] = vlans[0]["vlan_id"]
                iface["vlanName"] = vlans[0]["vlan_name"]
        return device, interfaces, ""
    except (socket.timeout, OSError, ValueError) as e:
        return device, [], str(e)


def backfill_interfaces(devices: list[dict], communities: list[str],
                        max_workers: int = DEFAULT_MAX_WORKERS,
                        timeout: float = DEFAULT_TIMEOUT,
                        snmpv3: dict | None = None) -> dict:
    """Walk interfaces on all given devices (threaded, v2c or v3). Returns summary."""
    devices = list(devices)
    results: list[dict] = []
    successful = 0
    total_interfaces = 0
    errors: list[str] = []

    def work(device):
        return walk_device_interfaces(device, communities, timeout=timeout, snmpv3=snmpv3)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(work, d) for d in devices]
        for future in as_completed(futures):
            device, interfaces, err = future.result()
            count = len(interfaces)
            if err:
                errors.append(err)
            else:
                successful += 1
                total_interfaces += count
            results.append({
                "ip": device.get("ip", ""),
                "hostname": device.get("hostname", ""),
                "device_type": device.get("device_type", ""),
                "device_id": device.get("id"),
                "interfaces": interfaces,
                "interface_count": count,
                "error": err,
            })

    results.sort(key=lambda r: (bool(r["error"]), r["ip"]))
    return {
        "total": len(devices),
        "successful": successful,
        "failed": len(devices) - successful,
        "interfaces_walked": total_interfaces,
        "sample_errors": sorted(set(e for e in errors if e))[:10],
        "results": results,
    }


# ── CDP neighbor report (show cdp neighbors detail, via SNMP) ────────────────

NETWORK_TYPES = ("switch", "core-switch", "router", "firewall")

# CISCO-CDP-MIB capabilities bits.
CAP_ROUTER = 0x01
CAP_SWITCH = 0x08


def _cdp_neighbor_kind(peer_type: str | None, capabilities: int) -> str:
    """Classify a CDP neighbor: network | ap | other.

    Network = switch/router/firewall; access points and host/endpoint devices
    are excluded from the report.
    """
    if peer_type in NETWORK_TYPES:
        return "network"
    if peer_type == "access-point":
        return "ap"
    if capabilities:
        if capabilities & CAP_SWITCH or capabilities & CAP_ROUTER:
            return "network"
    return "other"


def cdp_neighbor_report(db, devices: list[dict], communities: list[str],
                        snmpv3: dict | None = None,
                        max_workers: int = DEFAULT_MAX_WORKERS,
                        timeout: float = DEFAULT_TIMEOUT) -> dict:
    """Collect CDP neighbors for network devices and build a switch-to-switch
    report, excluding access points and non-network neighbors.

    Equivalent to `show cdp neighbors detail` per switch, but via the SNMP CDP
    cache table (scalable across the whole network). Returns row dicts for a
    spreadsheet export.
    """
    from models import Device

    type_by_ip = {d.ip: d.device_type for d in db.query(Device).all()}

    def work(device):
        ip = device.get("ip", "")
        if not ip:
            return device, [], "no ip"
        try:
            if snmpv3:
                from topology import collect_cdp_v3
                neighbors = collect_cdp_v3(ip, **_v3_kwargs(snmpv3, timeout))
            else:
                from topology import collect_cdp_v2c
                neighbors = (collect_cdp_v2c(ip, communities[0], timeout=timeout)
                             if communities else [])
            return device, neighbors, ""
        except (socket.timeout, OSError, ValueError) as e:
            return device, [], str(e)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(work, d) for d in devices]
        results = [f.result() for f in futures]

    rows: list[dict] = []
    errors: list[str] = []
    switches_checked = neighbors_found = excluded = 0
    for device, neighbors, err in results:
        if err or not neighbors:
            if err:
                errors.append(f"{device.get('ip', '')}: {err}")
            continue
        switches_checked += 1
        for n in neighbors:
            neighbors_found += 1
            n_ip = n.get("remote_ip", "")
            peer_type = type_by_ip.get(n_ip)
            kind = _cdp_neighbor_kind(peer_type, int(n.get("remote_capabilities", 0) or 0))
            if kind != "network":
                excluded += 1
                continue
            rows.append({
                "switch_hostname": device.get("hostname", ""),
                "switch_ip": device.get("ip", ""),
                "switch_site": device.get("site", ""),
                "neighbor_hostname": n.get("remote_device_id", ""),
                "neighbor_ip": n_ip,
                "neighbor_port": n.get("remote_port", ""),
                "local_port": n.get("local_port", ""),
                "neighbor_platform": n.get("remote_platform", ""),
                "neighbor_type": peer_type or "",
            })

    rows.sort(key=lambda r: (r["switch_hostname"], r["neighbor_hostname"]))
    return {
        "devices_targeted": len(devices),
        "switches_checked": switches_checked,
        "neighbors_found": neighbors_found,
        "excluded": excluded,
        "row_count": len(rows),
        "sample_errors": sorted(set(e for e in errors))[:10],
        "rows": rows,
    }


# ── Link validation (LLDP/CDP) ───────────────────────────────────────────────

def validate_device_links(device, communities: list[str], timeout: float = DEFAULT_TIMEOUT,
                          snmpv3: dict | None = None):
    """Walk LLDP + CDP on one device (v2c or v3); returns (device, neighbors, error)."""
    ip = device.get("ip", "")
    if not ip:
        return device, [], "no ip"
    if snmpv3:
        from topology import collect_lldp_v3, collect_cdp_v3
        kwargs = {"host": ip, **_v3_kwargs(snmpv3, timeout)}
        neighbors: list[dict] = []
        try:
            neighbors = collect_lldp_v3(**kwargs)
        except (socket.timeout, OSError, ValueError) as e:
            return device, [], f"lldp: {e}"
        try:
            neighbors += collect_cdp_v3(**kwargs)
        except (socket.timeout, OSError, ValueError) as e:
            neighbors = neighbors or []
            return device, neighbors, f"cdp: {e}"
        return device, neighbors, ""
    neighbors: list[dict] = []
    try:
        neighbors = collect_lldp_v2c(ip, communities[0], timeout=timeout) if communities else []
    except (socket.timeout, OSError, ValueError) as e:
        return device, [], f"lldp: {e}"
    try:
        neighbors += collect_cdp_v2c(ip, communities[0], timeout=timeout) if communities else []
    except (socket.timeout, OSError, ValueError) as e:
        # LLDP data is still usable; note the CDP failure only.
        neighbors = neighbors or []
        return device, neighbors, f"cdp: {e}"
    return device, neighbors, ""


def backfill_link_validation(devices: list[dict], communities: list[str],
                             max_workers: int = DEFAULT_MAX_WORKERS,
                             timeout: float = DEFAULT_TIMEOUT,
                             snmpv3: dict | None = None) -> dict:
    """Walk LLDP/CDP on the given devices (threaded, v2c or v3). Returns summary."""
    devices = list(devices)
    results: list[dict] = []
    total_neighbors = 0
    successful = 0
    errors: list[str] = []

    def work(device):
        return validate_device_links(device, communities, timeout=timeout, snmpv3=snmpv3)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(work, d) for d in devices]
        for future in as_completed(futures):
            device, neighbors, err = future.result()
            count = len(neighbors)
            if err and not neighbors:
                errors.append(err)
            else:
                successful += 1
                total_neighbors += count
            results.append({
                "ip": device.get("ip", ""),
                "hostname": device.get("hostname", ""),
                "device_type": device.get("device_type", ""),
                "device_id": device.get("id"),
                "neighbors": neighbors,
                "neighbor_count": count,
                "error": err,
            })

    results.sort(key=lambda r: (bool(r["error"]), r["ip"]))
    return {
        "total": len(devices),
        "successful": successful,
        "failed": len(devices) - successful,
        "neighbors_discovered": total_neighbors,
        "sample_errors": sorted(set(e for e in errors if e))[:10],
        "results": results,
    }
