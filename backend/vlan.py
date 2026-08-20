"""VLAN discovery (dot1q / BRIDGE MIB) and parsing.

Walks the standard VLAN MIBs to map each interface to its (access) VLAN, so
topology/interface views can show the VLAN a port belongs to.

MIBs walked (dot1q / BRIDGE):
    dot1qVlanStaticName       1.3.6.1.2.1.17.7.1.4.3.1.1  (indexed by vlanId)
    dot1qVlanStaticUntagged   1.3.6.1.2.1.17.7.1.4.3.1.4  (PortList of access ports)
    dot1dBasePortIfIndex      1.3.6.1.2.1.17.1.4.1.2      (bridge port -> ifIndex)
"""

from __future__ import annotations

VLAN_NAME_TABLE = "1.3.6.1.2.1.17.7.1.4.3.1.1"
VLAN_UNTAGGED_TABLE = "1.3.6.1.2.1.17.7.1.4.3.1.4"
BRIDGE_PORT_IFINDEX = "1.3.6.1.2.1.17.1.4.1.2"


def _last_oid_index(oid: str) -> int | None:
    parts = oid.rstrip(".").split(".")
    try:
        return int(parts[-1])
    except (ValueError, IndexError):
        return None


def _decode_portlist(value) -> set[int]:
    """Decode a dot1q PortList octet string into a set of bridge-port numbers.

    The first octet's most-significant bit is bridge port 1 (big-endian).
    """
    if isinstance(value, bytes):
        data = value
    elif isinstance(value, str):
        data = value.encode("utf-8")
    else:
        return set()
    ports: set[int] = set()
    bit = 1
    for byte in data:
        for shift in range(7, -1, -1):
            if byte & (1 << shift):
                ports.add(bit)
            bit += 1
    return ports


def parse_vlan_assignments(vlan_names: dict, untagged_ports: dict, bridge_ifindex: dict) -> dict[str, list[dict]]:
    """Map interfaces to their access VLAN(s).

    Returns {ifIndex(str): [{"vlan_id": int, "vlan_name": str}]}.
    """
    names: dict[int, str] = {}
    for oid, val in vlan_names.items():
        idx = _last_oid_index(oid)
        if idx is not None:
            names[idx] = val.decode("utf-8", "replace") if isinstance(val, bytes) else str(val)

    port_ifindex: dict[int, int] = {}
    for oid, val in bridge_ifindex.items():
        idx = _last_oid_index(oid)
        if idx is not None:
            try:
                port_ifindex[idx] = int(val)
            except (ValueError, TypeError):
                continue

    result: dict[str, list[dict]] = {}
    for oid, val in untagged_ports.items():
        vlan_id = _last_oid_index(oid)
        if vlan_id is None:
            continue
        for port in _decode_portlist(val):
            if_index = port_ifindex.get(port)
            if if_index is None:
                continue
            entry = {"vlan_id": vlan_id, "vlan_name": names.get(vlan_id, "")}
            bucket = result.setdefault(str(if_index), [])
            if entry not in bucket:
                bucket.append(entry)
    return result


def walk_vlans_v2c(host: str, communities: list[str], port: int = 161,
                   timeout: float = 2.0, max_oids: int = 1024) -> dict[str, list[dict]]:
    """Collect VLAN assignments for a device over SNMP v2c (best-effort)."""
    from snmp import snmp_walk, SNMP_PORT

    for community in communities:
        names = snmp_walk(host, VLAN_NAME_TABLE, community, port=port or SNMP_PORT,
                          timeout=timeout, max_oids=max_oids)
        if not names:
            continue
        untagged = snmp_walk(host, VLAN_UNTAGGED_TABLE, community, port=port or SNMP_PORT,
                             timeout=timeout, max_oids=max_oids)
        bridge = snmp_walk(host, BRIDGE_PORT_IFINDEX, community, port=port or SNMP_PORT,
                           timeout=timeout, max_oids=max_oids)
        if untagged and bridge:
            return parse_vlan_assignments(names, untagged, bridge)
    return {}


def walk_vlans_v3(host: str, params: dict, snmp_port: int = 161,
                  timeout: float = 2.0, max_oids: int = 1024) -> dict[str, list[dict]]:
    """Collect VLAN assignments for a device over SNMP v3 (best-effort)."""
    from snmpv3 import snmpv3_walk, AUTH_SHA, PRIV_NONE

    kwargs = dict(
        username=params["username"],
        auth_protocol=(params.get("auth_protocol") or AUTH_SHA).lower(),
        auth_password=params.get("auth_password", ""),
        privacy_protocol=(params.get("privacy_protocol") or PRIV_NONE).lower(),
        privacy_password=params.get("privacy_password") or params.get("auth_password", ""),
        timeout=timeout, port=snmp_port, max_oids=max_oids,
    )
    try:
        names = snmpv3_walk(host, VLAN_NAME_TABLE, **kwargs)
        untagged = snmpv3_walk(host, VLAN_UNTAGGED_TABLE, **kwargs)
        bridge = snmpv3_walk(host, BRIDGE_PORT_IFINDEX, **kwargs)
    except Exception:
        return {}
    if not (names and untagged and bridge):
        return {}
    return parse_vlan_assignments(names, untagged, bridge)
