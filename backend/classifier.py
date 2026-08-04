"""Device identification: vendor, model, and device-type classification.

Input is the SNMP sysDescr/sysObjectID/sysName tuple (optionally a hostname).
Output is a deterministic classification with a confidence score.

Confidence levels:
    4 - strong vendor + explicit device-type match (sysObjectID + sysDescr)
    3 - strong keyword match in sysDescr or sysObjectID vendor match
    2 - hostname-based match
    0 - unknown
"""

from __future__ import annotations

from dataclasses import dataclass

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


def classify(snmp_data: dict | None = None, hostname: str = "", ) -> Classification:
    """Classify a device from optional SNMP data and/or a hostname."""
    cls = Classification()

    sys_descr = (snmp_data or {}).get("sysDescr", "") or ""
    sys_object_id = (snmp_data or {}).get("sysObjectID", "") or ""
    sys_name = (snmp_data or {}).get("sysName", "") or ""
    name = sys_name or hostname

    oid_vendor = _vendor_from_oid(sys_object_id)
    type_vendor, descr_vendor = _type_from_descr(sys_descr)

    if sys_descr:
        cls.model = _extract_model(sys_descr)

    # Priority: explicit sysDescr device-type rule beats OID vendor.
    if type_vendor:
        cls.device_type = type_vendor
        cls.vendor = descr_vendor or oid_vendor
        cls.confidence = 4 if oid_vendor else 3
        return cls

    if oid_vendor:
        cls.vendor = oid_vendor
        # Vendor is known but type is ambiguous without keywords.
        cls.confidence = 3
        if name:
            host_type = _type_from_hostname(name)
            if host_type:
                cls.device_type = host_type
        return cls

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
