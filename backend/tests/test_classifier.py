"""Classifier tests: the Sprint 1 success criteria are accurate identification
of Cisco, Aruba, Fortinet, and VeloCloud devices."""

from classifier import classify, NETWORK_DEVICE_TYPES


def _snmp(descr="", oid="", name=""):
    return {"sysDescr": descr, "sysObjectID": oid, "sysName": name}


# ── Cisco ────────────────────────────────────────────────────────────────────

def test_cisco_c9300_switch():
    cls = classify(_snmp(
        descr="Cisco IOS Software, C9300L Software (C9300L-24P-4G), Version 17.3.3, RELEASE SOFTWARE",
        oid=".1.3.6.1.4.1.9.1.2463",
        name="sw1",
    ))
    assert cls.vendor == "Cisco"
    assert cls.device_type == "switch"
    assert cls.confidence == 4


def test_cisco_c9200_access_switch():
    cls = classify(_snmp(
        descr="Cisco IOS Software, C9200L Software (C9200L-24P-4X), Version 17.9.4",
        oid=".1.3.6.1.4.1.9.1.2583",
    ))
    assert cls.device_type == "access-switch"
    assert cls.confidence == 4  # sysDescr type rule + Cisco OID confirmation


def test_cisco_c9200_access_switch_no_oid():
    cls = classify(_snmp(
        descr="Cisco IOS Software, C9200L Software (C9200L-24P-4X), Version 17.9.4",
    ))
    assert cls.device_type == "access-switch"
    assert cls.confidence == 3


def test_cisco_c9500_core_switch():
    cls = classify(_snmp(descr="Cisco IOS XE Software, Version 17.12.1, C9500-48Y4C"))
    assert cls.device_type == "core-switch"
    assert cls.confidence == 3


def test_cisco_aironet_ap():
    cls = classify(_snmp(descr="Cisco IOS Software, Aironet Software (C9120AXI-...)"))
    assert cls.device_type == "accesspoint"
    assert cls.vendor == "Cisco"


def test_cisco_asr_router():
    cls = classify(_snmp(descr="Cisco IOS XE Software, Version 17.6.4, ASR1000-..."))
    assert cls.device_type == "router"


def test_cisco_asa_firewall():
    cls = classify(_snmp(descr="Cisco Adaptive Security Appliance Version 9.16"))
    assert cls.device_type == "firewall"


# ── Aruba ────────────────────────────────────────────────────────────────────

def test_aruba_switch():
    cls = classify(_snmp(
        descr="ArubaOS-Switch 2930F, Version WC.16.10.0005",
        oid=".1.3.6.1.4.1.14823.1.1.1",
    ))
    assert cls.vendor == "Aruba Networks"
    assert cls.device_type == "switch"
    assert cls.confidence == 4


def test_aruba_access_point():
    cls = classify(_snmp(
        descr="ArubaOS 10.4.0.1, AP-515",
        oid=".1.3.6.1.4.1.14823.1.1.1.1",
    ))
    assert cls.device_type == "accesspoint"


# ── Fortinet ─────────────────────────────────────────────────────────────────

def test_fortinet_firewall():
    cls = classify(_snmp(
        descr="FortiGate-100F v7.2.5,build1347",
        oid=".1.3.6.1.4.1.12356.101.1.12345",
    ))
    assert cls.vendor == "Fortinet"
    assert cls.device_type == "firewall"
    assert cls.confidence == 4


# ── VeloCloud ────────────────────────────────────────────────────────────────

def test_velocloud_via_descr():
    cls = classify(_snmp(
        descr="VeloCloud Edge 510, Software Version 4.5.0",
        oid=".1.3.6.1.4.1.43772.0.1",
    ))
    assert cls.vendor == "VMware VeloCloud"
    assert cls.device_type == "velocloud-edge"
    assert cls.confidence == 4


def test_velocloud_via_hostname():
    cls = classify(snmp_data=None, hostname="vce-miami-01")
    assert cls.device_type == "velocloud-edge"
    assert cls.confidence == 2


# ── Unknown / misc ───────────────────────────────────────────────────────────

def test_unknown_device():
    cls = classify(_snmp(descr="random embedded device"))
    assert cls.device_type == ""
    assert cls.confidence == 0


def test_hostname_only_switch():
    cls = classify(snmp_data=None, hostname="access-sw-3")
    assert cls.device_type == "switch"


def test_network_device_types_include_core():
    assert "velocloud-edge" in NETWORK_DEVICE_TYPES
    assert "core-switch" in NETWORK_DEVICE_TYPES
    assert "accesspoint" in NETWORK_DEVICE_TYPES
    assert "pc" not in NETWORK_DEVICE_TYPES
