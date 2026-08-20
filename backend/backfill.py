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

def walk_device_interfaces(device, communities: list[str], timeout: float = DEFAULT_TIMEOUT):
    """Walk IF-MIB for one device; returns (device, interfaces, error)."""
    ip = device.get("ip", "")
    if not ip:
        return device, [], "no ip"
    try:
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
                        timeout: float = DEFAULT_TIMEOUT) -> dict:
    """Walk interfaces on all given devices (threaded). Returns summary."""
    devices = list(devices)
    results: list[dict] = []
    successful = 0
    total_interfaces = 0
    errors: list[str] = []

    def work(device):
        return walk_device_interfaces(device, communities, timeout=timeout)

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


# ── Link validation (LLDP/CDP) ───────────────────────────────────────────────

def validate_device_links(device, communities: list[str], timeout: float = DEFAULT_TIMEOUT):
    """Walk LLDP + CDP on one device; returns (device, neighbors, error)."""
    ip = device.get("ip", "")
    if not ip:
        return device, [], "no ip"
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
                             timeout: float = DEFAULT_TIMEOUT) -> dict:
    """Walk LLDP/CDP on the given devices (threaded). Returns summary."""
    devices = list(devices)
    results: list[dict] = []
    total_neighbors = 0
    successful = 0
    errors: list[str] = []

    def work(device):
        return validate_device_links(device, communities, timeout=timeout)

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
