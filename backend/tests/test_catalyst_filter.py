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
