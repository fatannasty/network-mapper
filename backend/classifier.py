"""Device identification: vendor, model, and device-type classification.

Input is the SNMP sysDescr/sysObjectID/sysName tuple (optionally a hostname).
Output is a deterministic classification with a confidence score.

Confidence levels:
    5 - exact sysObjectID match in database (vendor + model + type known)
    4 - sysObjectID partial match in database (model family)
    3 - vendor OID prefix match or strong sysDescr keyword match
    2 - hostname-based match
    0 - unknown
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Enterprise OID prefixes per vendor (http://www.iana.org/assignments/enterprise-numbers)
VENDOR_OIDS = [
    (".1.3.6.1.4.1.9.", "Cisco"),
    (".1.3.6.1.4.1.29671.", "Cisco Meraki"),
    (".1.3.6.1.4.1.14823.", "Aruba Networks"),
    (".1.3.6.1.4.1.11863.", "Aruba Networks"),
    (".1.3.6.1.4.1.11.", "Hewlett Packard Enterprise"),
    (".1.3.6.1.4.1.25506.", "H3C"),
    (".1.3.6.1.4.1.2636.", "Juniper Networks"),
    (".1.3.6.1.4.1.12356.", "Fortinet"),
    (".1.3.6.1.4.1.25461.", "Palo Alto Networks"),
    (".1.3.6.1.4.1.30065.", "Arista Networks"),
    (".1.3.6.1.4.1.14988.", "MikroTik"),
    (".1.3.6.1.4.1.674.", "Dell EMC"),
    (".1.3.6.1.4.1.890.", "Zyxel"),
    (".1.3.6.1.4.1.43772.", "VMware VeloCloud"),
    (".1.3.6.1.4.1.6876.", "VMware"),
    (".1.3.6.1.4.1.8072.", "Net-SNMP"),
    (".1.3.6.1.4.1.2021.", "UCD-SNMP"),
]


@dataclass
class SysObjEntry:
    oid: str
    vendor: str
    model: str
    device_type: str


def _load_sysobj_db() -> list[SysObjEntry]:
    path = Path(__file__).with_name("sysobj_db.json")
    if not path.is_file():
        return []
    with open(path, "rb") as f:
        raw = json.load(f)
    return [
        SysObjEntry(
            oid=e["oid"],
            vendor=e["vendor"],
            model=e.get("model", ""),
            device_type=e.get("device_type", ""),
        )
        for e in raw
    ]


SYSOBJ_DB: list[SysObjEntry] = _load_sysobj_db()


def _match_sysobj_db(sys_object_id: str) -> Optional[SysObjEntry]:
    if not sys_object_id:
        return None
    for entry in SYSOBJ_DB:
        if sys_object_id == entry.oid:
            return entry
    return None

# Ordered keyword rules: (match_fn_keyword, device_type, vendor)
# sysDescr is matched case-insensitively.
DESCR_RULES = [
    # ── VeloCloud / SD-WAN ──
    (("velocloud",), "velocloud-edge", "VMware VeloCloud"),
    # ── Fortinet ──
    (("fortigate",), "firewall", "Fortinet"),
    (("fortios",), "firewall", "Fortinet"),
    # ── Cisco wireless ──
    (("aironet",), "accesspoint", "Cisco"),
    (("meraki mr",), "accesspoint", "Cisco Meraki"),
    (("cisco ios", "ap", "wireless"), "accesspoint", "Cisco"),
    # ── Cisco routers ──
    (("isr", "router"), "router", "Cisco"),
    (("asr",), "router", "Cisco"),
    (("router",), "router", "Cisco"),
    # ── Cisco firewalls ──
    (("asa",), "firewall", "Cisco"),
    (("ftd",), "firewall", "Cisco"),
    (("adaptive security appliance",), "firewall", "Cisco"),
    (("catalyst 9000",), "switch", "Cisco"),
    # ── Cisco switches (platform tokens) ──
    (("c9300",), "switch", "Cisco"),
    (("c9200",), "access-switch", "Cisco"),
    (("c9500",), "core-switch", "Cisco"),
    (("c9400",), "core-switch", "Cisco"),
    (("c2960",), "access-switch", "Cisco"),
    (("c3560",), "switch", "Cisco"),
    (("c3750",), "switch", "Cisco"),
    (("c3850",), "switch", "Cisco"),
    (("catalyst 2960",), "access-switch", "Cisco"),
    (("nexus",), "core-switch", "Cisco"),
    (("ios", "xe"), "switch", "Cisco"),  # generic Cisco IOS-XE fallback
    # ── Aruba ──
    (("arubaos", "ap"), "accesspoint", "Aruba Networks"),
    (("arubaos-switch",), "switch", "Aruba Networks"),
    (("provision",), "switch", "Aruba Networks"),
    (("arubaos",), "switch", "Aruba Networks"),
    # ── Juniper ──
    (("junos", "ex"), "switch", "Juniper Networks"),
    (("junos", "mx"), "router", "Juniper Networks"),
    (("junos", "srx"), "firewall", "Juniper Networks"),
    (("junos",), "switch", "Juniper Networks"),
    # ── Palo Alto / Arista / others ──
    (("panos",), "firewall", "Palo Alto Networks"),
    (("pa-",), "firewall", "Palo Alto Networks"),
    (("arista",), "switch", "Arista Networks"),
    (("mikrotik", "routeros"), "router", "MikroTik"),
]

HOSTNAME_RULES = [
    (("velocloud",), "velocloud-edge"),
    (("vce-",), "velocloud-edge"),
    (("switch",), "switch"),
    (("sw-",), "switch"),
    (("core",), "core-switch"),
    (("ap",), "accesspoint"),
    (("router",), "router"),
    (("fw",), "firewall"),
    (("firewall",), "firewall"),
]


@dataclass
class Classification:
    vendor: str = ""
    model: str = ""
    device_type: str = ""
    confidence: int = 0


def _vendor_from_oid(sys_object_id: str) -> str:
    if not sys_object_id:
        return ""
    for prefix, vendor in VENDOR_OIDS:
        if sys_object_id.startswith(prefix):
            return vendor
    return ""


def _type_from_descr(descr: str) -> tuple[str, str]:
    """Return (device_type, vendor) from a sysDescr string, or ('', '')."""
    lowered = descr.lower()
    for keywords, device_type, vendor in DESCR_RULES:
        if all(k in lowered for k in keywords):
            return device_type, vendor
    return "", ""


def _type_from_hostname(hostname: str) -> str:
    lowered = hostname.lower()
    for keywords, device_type in HOSTNAME_RULES:
        if any(k in lowered for k in keywords):
            return device_type
    return ""


def _extract_model(descr: str) -> str:
    """Best-effort model extraction from sysDescr."""
    if not descr:
        return ""
    first_line = descr.strip().splitlines()[0].strip()[:120]
    return first_line


def classify_from_platform(platform_id: str = "", family: str = "",
                          device_type: str = "") -> Classification:
    """Determine device type from Catalyst Center platformId/family/type fields.

    Matches against known platform keywords so Catalyst imports get the same
    device_type labels used for SNMP-discovered devices.
    """
    cls = Classification()
    pid = (platform_id or "").lower()
    fam = (family or "").lower()
    dt = (device_type or "").lower()

    if any(k in pid for k in ("c9300", "c3850", "c3750", "c3650", "c9200")):
        cls.device_type = "switch"; cls.confidence = 4
    elif any(k in pid for k in ("c9500", "c9400", "nexus", "n9k")):
        cls.device_type = "core-switch"; cls.confidence = 4
    elif any(k in pid for k in ("c2960",)):
        cls.device_type = "access-switch"; cls.confidence = 4
    elif any(k in pid for k in ("isr", "asr", "csr")):
        cls.device_type = "router"; cls.confidence = 4
    elif any(k in pid for k in ("asa", "ftd")):
        cls.device_type = "firewall"; cls.confidence = 4
    elif "meraki" in fam or "meraki" in pid or "meraki" in dt:
        if "ms" in pid or "switch" in fam:
            cls.device_type = "switch"
        elif "mr" in pid or "access point" in fam or ("ap " in fam or fam.endswith(" ap")):
            cls.device_type = "accesspoint"
        elif "mx" in pid or "firewall" in fam or "security" in fam:
            cls.device_type = "firewall"
        cls.confidence = 4
    elif "switch" in fam or "switches" in fam:
        cls.device_type = "switch"; cls.confidence = 3
    elif "router" in fam or "routers" in fam:
        cls.device_type = "router"; cls.confidence = 3
    elif "firewall" in fam or "security" in fam:
        cls.device_type = "firewall"; cls.confidence = 3
    elif "access point" in fam or "wireless" in fam or ("ap " in fam or fam.endswith(" ap")):
        cls.device_type = "accesspoint"; cls.confidence = 3
    elif "controller" in fam or "wlc" in fam:
        cls.device_type = "wireless-controller"; cls.confidence = 3
    elif "velocloud" in pid or "velocloud" in fam or "velocloud" in dt:
        cls.device_type = "velocloud-edge"; cls.confidence = 4
    elif "load balancer" in fam:
        cls.device_type = "load-balancer"; cls.confidence = 3

    return cls


def classify(snmp_data: dict | None = None, hostname: str = "", ) -> Classification:
    """Classify a device from optional SNMP data and/or a hostname.

    Priority:
      1. Exact sysObjectID match (confidence 5) — precise vendor/model/type
      2. sysDescr keyword rules (confidence 3–4)
      3. Vendor OID prefix match (confidence 3)
      4. Hostname-based match (confidence 2)
    """
    cls = Classification()

    sys_descr = (snmp_data or {}).get("sysDescr", "") or ""
    sys_object_id = (snmp_data or {}).get("sysObjectID", "") or ""
    sys_name = (snmp_data or {}).get("sysName", "") or ""
    name = sys_name or hostname

    # 1. Exact sysObjectID database match — highest confidence
    entry = _match_sysobj_db(sys_object_id)
    if entry:
        cls.vendor = entry.vendor
        cls.model = entry.model
        cls.device_type = entry.device_type
        cls.confidence = 5
        return cls

    oid_vendor = _vendor_from_oid(sys_object_id)
    type_vendor, descr_vendor = _type_from_descr(sys_descr)

    if sys_descr:
        cls.model = _extract_model(sys_descr)

    # 2. Explicit sysDescr device-type rule beats OID vendor.
    if type_vendor:
        cls.device_type = type_vendor
        cls.vendor = descr_vendor or oid_vendor
        cls.confidence = 4 if oid_vendor else 3
        return cls

    # 3. Vendor known from OID prefix, but type ambiguous.
    if oid_vendor:
        cls.vendor = oid_vendor
        cls.confidence = 3
        if name:
            host_type = _type_from_hostname(name)
            if host_type:
                cls.device_type = host_type
        return cls

    # 4. Hostname-based fallback.
    if name:
        host_type = _type_from_hostname(name)
        if host_type:
            cls.device_type = host_type
            cls.vendor = "unknown"
            cls.confidence = 2

    return cls


# Type -> ordering used when sorting scan results (lower sorts first).
DEVICE_TYPE_ORDER = {
    "router": 0,
    "velocloud-edge": 1,
    "firewall": 1,
    "core-switch": 2,
    "switch": 3,
    "access-switch": 4,
    "accesspoint": 5,
}

# Device types that are kept for network topology display.
NETWORK_DEVICE_TYPES = {
    "router", "velocloud-edge", "switch", "access-switch", "core-switch", "accesspoint",
}
