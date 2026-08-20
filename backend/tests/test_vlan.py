"""VLAN discovery parsing tests."""

from vlan import parse_vlan_assignments, _decode_portlist


def test_decode_portlist_big_endian():
    # First octet's MSB = bridge port 1.
    assert _decode_portlist(bytes([0xC0])) == {1, 2}      # 0b11000000
    assert _decode_portlist(bytes([0x20])) == {3}         # 0b00100000
    assert _decode_portlist(bytes([0x80])) == {1}         # port 1 only
    assert _decode_portlist(bytes([0x00, 0x80])) == {9}   # 2nd octet MSB = port 9


def test_parse_vlan_assignments():
    vlan_names = {
        "1.3.6.1.2.1.17.7.1.4.3.1.1.10": b"Management",
        "1.3.6.1.2.1.17.7.1.4.3.1.1.20": b"Users",
    }
    bridge = {
        "1.3.6.1.2.1.17.1.4.1.2.1": 1,
        "1.3.6.1.2.1.17.1.4.1.2.2": 2,
        "1.3.6.1.2.1.17.1.4.1.2.3": 3,
    }
    untagged = {
        "1.3.6.1.2.1.17.7.1.4.3.1.4.10": bytes([0xC0]),  # vlan 10 -> ports 1,2
        "1.3.6.1.2.1.17.7.1.4.3.1.4.20": bytes([0x20]),  # vlan 20 -> port 3
    }

    result = parse_vlan_assignments(vlan_names, untagged, bridge)

    assert result["1"] == [{"vlan_id": 10, "vlan_name": "Management"}]
    assert result["2"] == [{"vlan_id": 10, "vlan_name": "Management"}]
    assert result["3"] == [{"vlan_id": 20, "vlan_name": "Users"}]


def test_parse_vlan_assignments_ignores_unknown_ports():
    # A port bit with no bridge-port->ifIndex mapping is skipped.
    vlan_names = {"1.3.6.1.2.1.17.7.1.4.3.1.1.5": b"Data"}
    bridge = {"1.3.6.1.2.1.17.1.4.1.2.1": 1}
    untagged = {"1.3.6.1.2.1.17.7.1.4.3.1.4.5": bytes([0xC0])}  # ports 1,2; port 2 unmapped

    result = parse_vlan_assignments(vlan_names, untagged, bridge)
    assert "1" in result and result["1"] == [{"vlan_id": 5, "vlan_name": "Data"}]
    assert "2" not in result
