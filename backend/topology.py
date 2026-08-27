"""Sprint 5: LLDP/CDP neighbor discovery and link building.

Walks the LLDP-MIB (IEEE 802.1AB) remote table and the Cisco CDP cache table
over SNMPv2c or SNMPv3, parses the raw varbinds into neighbor dicts, and turns
per-device neighbor lists into deduplicated topology links.
"""

from __future__ import annotations

import socket

from snmp import _to_str, snmp_walk
from snmpv3 import snmpv3_walk

# ── LLDP-MIB (1.0.8802.1.1.2.1.4) ────────────────────────────────────────────
# lldpRemEntry OIDs: 1.0.8802.1.1.2.1.4.1.1.<column>.<timeMark>.<localPortNum>.<remIndex>
LLDP_REM_TABLE = "1.0.8802.1.1.2.1.4.1.1"
LLDP_COL_CHASSIS_ID = 5
LLDP_COL_PORT_ID = 7
LLDP_COL_PORT_DESC = 8
LLDP_COL_SYS_NAME = 9
LLDP_COL_SYS_DESC = 10

# ── CISCO-CDP-MIB (1.3.6.1.4.1.9.9.23.1.2.1.1) ───────────────────────────────
# cdpCacheEntry OIDs: 1.3.6.1.4.1.9.9.23.1.2.1.1.<column>.<ifIndex>.<deviceIndex>
CDP_CACHE_TABLE = "1.3.6.1.4.1.9.9.23.1.2.1.1"
CDP_COL_ADDRESS_TYPE = 2
CDP_COL_ADDRESS = 3
CDP_COL_DEVICE_ID = 6
CDP_COL_DEVICE_PORT = 7
CDP_COL_PLATFORM = 8
CDP_COL_CAPABILITIES = 9


def _fmt_octets(value) -> str:
    if isinstance(value, bytes):
        return ":".join(f"{b:02x}" for b in value)
    return "" if value is None else str(value)


def _fmt_ipv4(value) -> str:
    if isinstance(value, bytes) and len(value) == 4:
        return ".".join(str(b) for b in value)
    return ""


def parse_lldp_neighbors(raw: dict) -> list[dict]:
    """Group lldpRemTable varbinds into per-neighbor dicts."""
    cols: dict[tuple[str, str], dict[int, object]] = {}
    prefix = LLDP_REM_TABLE + "."
    for oid, val in raw.items():
        if oid.startswith(prefix):
            parts = oid.split(".")
            col = parts[-4]
            key = (parts[-2], parts[-1])  # (localPortNum, remIndex)
            cols.setdefault(key, {})[int(col)] = val

    neighbors: list[dict] = []
    for (local_port, _rem), vals in sorted(cols.items()):
        neighbors.append({
            "protocol": "lldp",
            "local_port": local_port,
            "remote_sysname": _to_str(vals.get(LLDP_COL_SYS_NAME, "")),
            "remote_chassis_id": _fmt_octets(vals.get(LLDP_COL_CHASSIS_ID, b"")),
            "remote_port_id": _fmt_octets(vals.get(LLDP_COL_PORT_ID, b"")),
            "remote_port_desc": _to_str(vals.get(LLDP_COL_PORT_DESC, "")),
            "remote_sysdesc": _to_str(vals.get(LLDP_COL_SYS_DESC, "")),
        })
    return neighbors


def parse_cdp_neighbors(raw: dict) -> list[dict]:
    """Group cdpCacheTable varbinds into per-neighbor dicts."""
    cols: dict[tuple[str, str], dict[int, object]] = {}
    prefix = CDP_CACHE_TABLE + "."
    for oid, val in raw.items():
        if oid.startswith(prefix):
            parts = oid.split(".")
            col = parts[-3]
            key = (parts[-2], parts[-1])  # (ifIndex, deviceIndex)
            cols.setdefault(key, {})[int(col)] = val

    neighbors: list[dict] = []
    for (if_index, _dev), vals in sorted(cols.items()):
        neighbors.append({
            "protocol": "cdp",
            "local_port": if_index,
            "remote_device_id": _to_str(vals.get(CDP_COL_DEVICE_ID, "")),
            "remote_port": _to_str(vals.get(CDP_COL_DEVICE_PORT, "")),
            "remote_ip": _fmt_ipv4(vals.get(CDP_COL_ADDRESS, b"")),
            "remote_platform": _to_str(vals.get(CDP_COL_PLATFORM, "")),
            "remote_capabilities": int(vals[CDP_COL_CAPABILITIES]) if CDP_COL_CAPABILITIES in vals else 0,
        })
    return neighbors


# ── Neighbor collection (v2c / v3) ───────────────────────────────────────────

def collect_lldp_v2c(host: str, community: str, port: int = 161,
                     timeout: float = 2.0) -> list[dict]:
    return parse_lldp_neighbors(snmp_walk(host, LLDP_REM_TABLE, community, port=port, timeout=timeout))


def collect_cdp_v2c(host: str, community: str, port: int = 161,
                    timeout: float = 2.0) -> list[dict]:
    return parse_cdp_neighbors(snmp_walk(host, CDP_CACHE_TABLE, community, port=port, timeout=timeout))


def collect_lldp_v3(host: str, username: str, auth_protocol: str = "sha",
                    auth_password: str = "", privacy_protocol: str = "none",
                    privacy_password: str | None = None,
                    port: int = 161, timeout: float = 2.0) -> list[dict]:
    raw = snmpv3_walk(host, LLDP_REM_TABLE, username, auth_protocol=auth_protocol,
                      auth_password=auth_password, privacy_protocol=privacy_protocol,
                      privacy_password=privacy_password, timeout=timeout, port=port)
    return parse_lldp_neighbors(raw)


def collect_cdp_v3(host: str, username: str, auth_protocol: str = "sha",
                   auth_password: str = "", privacy_protocol: str = "none",
                   privacy_password: str | None = None,
                   port: int = 161, timeout: float = 2.0) -> list[dict]:
    raw = snmpv3_walk(host, CDP_CACHE_TABLE, username, auth_protocol=auth_protocol,
                      auth_password=auth_password, privacy_protocol=privacy_protocol,
                      privacy_password=privacy_password, timeout=timeout, port=port)
    return parse_cdp_neighbors(raw)


# ── Link building ─────────────────────────────────────────────────────────────

def _local_iface_name(interfaces: list[dict], index: str) -> str:
    if not index:
        return ""
    for iface in interfaces or []:
        if iface.get("ifIndex") == index:
            return iface.get("ifDescr") or iface.get("ifName") or index
    return index


def build_links(devices: list[dict]) -> list[dict]:
    """Turn per-device neighbor lists into canonical, deduplicated links.

    A link connects two endpoints (IP or best-known name). Bidirectional
    reports of the same physical link collapse into a single entry with the
    endpoint pair sorted.
    """
    by_ip: dict[str, dict] = {}
    by_hostname: dict[str, dict] = {}
    for device in devices:
        ip = device.get("ip", "")
        if ip:
            by_ip[ip] = device
        hostname = (device.get("hostname") or "").lower()
        if hostname:
            by_hostname[hostname] = device
            by_hostname.setdefault(hostname.split(".")[0], device)

    links: dict[tuple, dict] = {}
    for device in devices:
        interfaces = device.get("interfaces", [])
        for neighbor in device.get("neighbors", []):
            proto = neighbor.get("protocol", "lldp")
            if proto == "cdp":
                remote_ip = neighbor.get("remote_ip", "")
                remote_name = neighbor.get("remote_device_id", "")
                target = by_ip.get(remote_ip) if remote_ip else None
                target_iface = neighbor.get("remote_port", "")
                target_name = target.get("hostname") if target else remote_name
                target_id = remote_ip or remote_name
            else:
                remote_name = neighbor.get("remote_sysname", "")
                target = by_hostname.get(remote_name.lower()) if remote_name else None
                target_iface = neighbor.get("remote_port_desc") or neighbor.get("remote_port_id", "")
                target_name = target.get("hostname") if target else remote_name
                target_id = target.get("ip") if target else remote_name
            if not target_id:
                continue

            local_iface = _local_iface_name(interfaces, neighbor.get("local_port", ""))
            a, b = sorted((device["ip"], target_id))
            key = (a, b)
            if key in links:
                continue
            source_first = a == device["ip"]
            links[key] = {
                "source": a,
                "target": b,
                "source_interface": local_iface if source_first else target_iface,
                "target_interface": target_iface if source_first else local_iface,
                "protocol": proto,
                "source_hostname": device.get("hostname", "") if source_first else target_name,
                "target_hostname": target_name if source_first else device.get("hostname", ""),
            }

    return list(links.values())
