"""Verify Catalyst site/device filtering never silently imports everything."""

from unittest.mock import patch

import catalyst


def _dev(pid, hostname="", site_name=None, site_hier=None, site_id=None, loc=None, loc_name=None):
    return {
        "id": pid,
        "instanceUuid": pid,
        "managementIpAddress": f"10.0.0.{int(pid.split('-')[0][-1]) if '-' in pid else 1}",
        "hostname": hostname,
        "platformId": "C9300",
        "type": "Catalyst 9300 Switch",
        "family": "Switches and Hubs",
        "siteName": site_name,
        "siteHierarchy": site_hier,
        "siteId": site_id,
        "location": loc,
        "locationName": loc_name,
    }


def _fake_auth(*a, **k):
    return "token"


def _patch_import(mock_auth, mock_devices, mock_sites, mock_members):
    return patch.multiple(
        "catalyst",
        authenticate=_fake_auth,
        get_devices=lambda *a, **k: mock_devices,
        get_sites=lambda *a, **k: {"sites": mock_sites},
        get_site_members=lambda *a, **k: mock_members,
        get_physical_topology=lambda *a, **k: [],
        get_device_neighbors=lambda *a, **k: [],
        get_poe_interfaces=lambda *a, **k: [],
    )


def test_site_filter_with_membership_only_keeps_members():
    devs = [_dev("aaa"), _dev("bbb"), _dev("ccc")]
    sites = [{"name": "Miami", "hierarchy": "Global/United States/Florida/Miami",
              "hierarchy_ids": "a/b/c", "site_id": "site-x"}]
    # Membership API only knows device "bbb" belongs to site-x.
    with _patch_import(None, devs, sites, {"bbb"}):
        devices, links, debug = catalyst.import_devices(
            "https://cc", "u", "p", site_name="Florida > Miami", site_id="site-x")
    assert len(devices) == 1
    assert debug["raw_devices"] == 1
    assert any("matched 1 of 3" in e for e in debug["errors"])


def test_state_only_pick_resolves_children_via_site_name():
    devs = [_dev("aaa"), _dev("bbb"), _dev("ccc")]
    sites = [
        {"name": "Florida", "hierarchy": "Global/United States/Florida",
         "hierarchy_ids": "a/b/f", "site_id": "site-f"},
        {"name": "Miami", "hierarchy": "Global/United States/Florida/Miami",
         "hierarchy_ids": "a/b/f/m", "site_id": "site-m"},
        {"name": "Sanford", "hierarchy": "Global/United States/Florida/Sanford",
         "hierarchy_ids": "a/b/f/s", "site_id": "site-s"},
    ]
    # State-only pick has no site_id; must resolve via site_name and expand children.
    with _patch_import(None, devs, sites, {"aaa", "ccc"}):
        devices, links, debug = catalyst.import_devices(
            "https://cc", "u", "p", site_name="Florida")
    assert debug["raw_devices"] == 2
    assert any("Site filter" in e and "matched 2 of 3" in e for e in debug["errors"])


def test_site_filter_without_membership_never_leaks_all():
    devs = [_dev("aaa"), _dev("bbb"), _dev("ccc")]
    sites = [{"name": "Miami", "hierarchy": "Global/United States/Florida/Miami",
              "hierarchy_ids": "a/b/c", "site_id": "site-x"}]
    # Membership returns nothing: no devices imported, never all of them.
    with _patch_import(None, devs, sites, set()):
        devices, links, debug = catalyst.import_devices(
            "https://cc", "u", "p", site_name="Florida > Miami", site_id="site-x")
    assert len(devices) == 0
    assert debug["raw_devices"] == 0


def test_site_filter_matches_devices_by_site_hierarchy_when_membership_empty():
    # Membership returns nothing, but one device carries the readable
    # siteHierarchy path -> still matched via site fields.
    devs = [
        _dev("aaa", site_hier="Global/United States/Florida/Miami/Building1"),
        _dev("bbb"),
        _dev("ccc", site_hier="Global/United States/California/San Jose/Building2"),
    ]
    sites = [{"name": "Miami", "hierarchy": "Global/United States/Florida/Miami",
              "hierarchy_ids": "a/b/c", "site_id": "site-x"}]
    with _patch_import(None, devs, sites, set()):
        devices, links, debug = catalyst.import_devices(
            "https://cc", "u", "p", site_name="Florida > Miami", site_id="site-x")
    assert debug["raw_devices"] == 1
    assert devices[0]["hostname"] == ""


def test_site_filter_unions_membership_and_site_fields():
    # "aaa" is a membership member; "bbb" is not but has matching siteHierarchy.
    devs = [
        _dev("aaa"),
        _dev("bbb", site_hier="Global/United States/Florida/Miami/Floor1"),
        _dev("ccc"),
    ]
    sites = [{"name": "Miami", "hierarchy": "Global/United States/Florida/Miami",
              "hierarchy_ids": "a/b/c", "site_id": "site-x"}]
    with _patch_import(None, devs, sites, {"aaa"}):
        devices, links, debug = catalyst.import_devices(
            "https://cc", "u", "p", site_name="Florida > Miami", site_id="site-x")
    assert debug["raw_devices"] == 2
    assert debug["membership_ids_count"] == 1


def test_site_filter_matches_by_device_site_id_uuid():
    devs = [
        _dev("aaa", site_id="site-x"),
        _dev("bbb"),
    ]
    sites = [{"name": "Miami", "hierarchy": "Global/United States/Florida/Miami",
              "hierarchy_ids": "a/b/c", "site_id": "site-x"}]
    with _patch_import(None, devs, sites, set()):
        devices, links, debug = catalyst.import_devices(
            "https://cc", "u", "p", site_name="Florida > Miami", site_id="site-x")
    assert debug["raw_devices"] == 1


def test_full_import_no_site_filter_returns_everything():
    # No site_name/site_id/device_filter -> every device is imported, and each
    # carries a readable site derived from its siteHierarchy for reporting.
    devs = [
        _dev("1-aaa", site_hier="Global/United States/Florida/Miami/Building1"),
        _dev("2-bbb", site_hier="Global/United States/California/Sacramento"),
        _dev("3-ccc"),
    ]
    with _patch_import(None, devs, [], set()):
        devices, links, debug = catalyst.import_devices("https://cc", "u", "p")
    assert len(devices) == 3
    assert debug["raw_devices"] == 3
    by_ip = {d["ip"]: d for d in devices}
    assert by_ip["10.0.0.1"]["site"] == "Building1"
    assert by_ip["10.0.0.1"]["device_type"] == "switch"
    # device without a siteHierarchy falls back to locationName/location/siteName
    assert by_ip["10.0.0.2"]["site"] == "Sacramento"
    assert by_ip["10.0.0.3"]["site"] == ""


def test_ap_neighbors_walked_beyond_non_ap_cap():
    """Access points are always walked for CDP/LLDP neighbors, even past the
    non-AP device cap, so switch↔AP uplinks show up in site topology."""
    devs = [_dev("1-x", hostname="MIA-SW01")] + [
        _dev(f"{i}-x", hostname=f"DEV{i:02d}") for i in range(2, 32)
    ]
    devs.append({
        "id": "ap-1", "instanceUuid": "ap-1",
        "managementIpAddress": "10.0.0.99",
        "hostname": "MIA-AP01",
        "platformId": "AIR-AP2802I-B-K9",
        "type": "Wireless Access Point",
        "family": "Wireless Access Points",
        "siteName": "", "siteHierarchy": "", "siteId": "",
        "location": "", "locationName": "",
    })

    def fake_neighbors(base_url, token, device_id, **kwargs):
        if device_id == "ap-1":
            return [{"neighbor_device": "MIA-SW01", "neighbor_port": "GigabitEthernet1/0/24",
                     "local_port": "GigabitEthernet0", "neighbor_ip": ""}]
        return []

    with patch.multiple(
        "catalyst",
        authenticate=_fake_auth,
        get_devices=lambda *a, **k: devs,
        get_sites=lambda *a, **k: {"sites": []},
        get_site_members=lambda *a, **k: set(),
        get_physical_topology=lambda *a, **k: [],
        get_device_neighbors=fake_neighbors,
        get_poe_interfaces=lambda *a, **k: [],
    ):
        devices, links, debug = catalyst.import_devices("https://cc", "u", "p")

    assert any(d["device_type"] == "accesspoint" for d in devices)
    assert debug["ap_neighbors_queried"] == 1
    assert debug["ap_links_added"] == 1
    assert any(
        {l["source"], l["target"]} == {"10.0.0.99", "10.0.0.1"}
        and l["protocol"] == "cdp-lldp"
        for l in links
    )


def test_poe_data_links_access_points_to_their_switch():
    """POE interface inventory maps a powered AP to the switch port it is
    wired into, producing switch→AP links Catalyst's topology doesn't report."""
    sw = _dev("1-x", hostname="MIA-SW01")
    ap = {
        "id": "ap-1", "instanceUuid": "ap-1",
        "managementIpAddress": "10.0.0.99",
        "hostname": "MIA-AP01",
        "platformId": "AIR-AP2802I-B-K9",
        "type": "Wireless Access Point",
        "family": "Wireless Access Points",
        "siteName": "", "siteHierarchy": "", "siteId": "",
        "location": "", "locationName": "",
    }
    devs = [sw, ap]

    def fake_poe(base_url, token, device_id, **kwargs):
        if device_id == "1-x":
            return [{"name": "GigabitEthernet1/0/24", "pdDeviceName": "MIA-AP01",
                     "pdDeviceModel": "AIR-AP2802I-B-K9",
                     "poeOperStatus": "Delivering Power"}]
        return []

    with patch.multiple(
        "catalyst",
        authenticate=_fake_auth,
        get_devices=lambda *a, **k: devs,
        get_sites=lambda *a, **k: {"sites": []},
        get_site_members=lambda *a, **k: set(),
        get_physical_topology=lambda *a, **k: [],
        get_device_neighbors=lambda *a, **k: [],
        get_poe_interfaces=fake_poe,
    ):
        devices, links, debug = catalyst.import_devices("https://cc", "u", "p")

    assert debug["poe_devices_walked"] == 1
    assert debug["poe_links_added"] == 1
    assert any(
        l["source"] == "10.0.0.1" and l["target"] == "10.0.0.99"
        and l["protocol"] == "poe"
        and l["source_interface"] == "GigabitEthernet1/0/24"
        for l in links
    )


def test_detect_vlan90():
    assert catalyst.detect_vlan90("interface Vlan90\n description mgmt") is True
    assert catalyst.detect_vlan90("switchport access vlan 90") is True
    assert catalyst.detect_vlan90("vlan 90\n name Voice") is True
    assert catalyst.detect_vlan90("switchport trunk allowed vlan 90,100,200") is True
    assert catalyst.detect_vlan90("vlan 100\n name Data\n vlan 200\n name Guest") is False
    assert catalyst.detect_vlan90("vlan 900\n name Big") is False
    assert catalyst.detect_vlan90("vlan 190\n name Other") is False
    assert catalyst.detect_vlan90("") is False


def test_vlan90_prefers_stored_configs_and_flags_fetch_errors():
    devs = [_dev("aaa"), _dev("bbb"), _dev("ccc")]
    for i, d in enumerate(devs):
        d["managementIpAddress"] = f"10.9.0.{i + 1}"
    with _patch_import(None, devs, [], set()), \
         patch("catalyst.get_device_running_config",
               side_effect=Exception("dnac config api down")):
        devices, links, debug = catalyst.import_devices(
            "https://cc", "u", "p", flag_vlan90=True,
            stored_configs={"10.9.0.1": "interface Vlan90\n description mgmt"})
    by_ip = {d["ip"]: d for d in devices}
    assert by_ip["10.9.0.1"]["vlan_90"] is True   # detected via stored SSH config
    assert by_ip["10.9.0.2"]["vlan_90"] is None   # fetch failure -> unflagged, never False
    assert by_ip["10.9.0.3"]["vlan_90"] is None
    assert debug["vlan90_detected"] == 1
    assert debug["vlan90_from_stored"] == 1
    assert debug["vlan90_fetch_errors"] == 2


def test_backfill_vlan90_from_stored_configs():
    from database import SessionLocal
    from models import Device, DeviceConfig, Interface
    from fastapi.testclient import TestClient
    import main

    with SessionLocal() as db:
        d = Device(ip="10.9.0.50", hostname="sw-v90", device_type="switch",
                   site="Test")
        db.add(d)
        db.flush()
        db.add(DeviceConfig(device_id=d.id, config_text="interface Vlan90\n",
                            config_type="running"))
        # SNMP VLAN signal: no config, but an interface tagged VLAN 90.
        d2 = Device(ip="10.9.0.51", hostname="sw-vlan-walk", device_type="switch",
                    site="Test")
        db.add(d2)
        db.flush()
        db.add(Interface(device_id=d2.id, if_name="Gi1/0/1", vlan_id=90))
        db.commit()
        dev_id = d.id
        dev2_id = d2.id

    client = TestClient(main.app)
    client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    resp = client.post("/api/backfill/vlan90")
    assert resp.status_code == 200
    data = resp.json()
    assert data["backfilled"] is True
    assert data["vlan90_detected"] >= 2

    with SessionLocal() as db:
        assert db.get(Device, dev_id).vlan_90 is True     # from stored config
        assert db.get(Device, dev2_id).vlan_90 is True    # from SNMP VLAN walk

    with SessionLocal() as db:
        db.query(DeviceConfig).filter(DeviceConfig.device_id.in_([dev_id, dev2_id])).delete()
        db.query(Interface).filter(Interface.device_id.in_([dev_id, dev2_id])).delete()
        for did in (dev_id, dev2_id):
            flagged = db.get(Device, did)
            if flagged is not None:
                db.delete(flagged)
        db.commit()
