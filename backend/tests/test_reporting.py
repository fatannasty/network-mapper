"""Sprint 12: reporting — extended report shape + CSV export."""

from conftest import make_client

client = make_client("admin")


def _seed():
    _run = client.post("/api/discover", json={
        "subnet": "127.0.0.1/32", "communities": ["public"], "exclude_pcs": False,
    })
    assert _run.status_code == 200
    return _run.json()["scan_id"]


def test_report_includes_full_report_set():
    _seed()
    report = client.get("/api/inventory/report").json()
    assert report["total_devices"] >= 1
    assert "total_links" in report
    assert "total_interfaces" in report
    assert "by_device_type" in report
    assert "by_vendor" in report
    assert "by_site" in report
    assert "link_protocols" in report
    assert "interface_status" in report
    assert "config_coverage" in report
    assert "stale_devices_90d" in report
    assert "scan_history" in report
    assert "recent_scans" in report
    assert report["config_coverage"]["total_configs"] >= 0


def test_config_coverage_shape():
    _seed()
    report = client.get("/api/inventory/report").json()
    coverage = report["config_coverage"]
    assert {"total_configs", "devices_with_config", "by_device_type"} <= set(coverage)


def test_export_devices_csv():
    _seed()
    resp = client.get("/api/inventory/report/export", params={"report": "devices"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "attachment" in resp.headers.get("content-disposition", "")
    body = resp.text
    assert body.startswith("ip,hostname,vendor,model,device_type")
    assert "127.0.0.1" in body


def test_export_links_csv():
    _seed()
    resp = client.get("/api/inventory/report/export", params={"report": "links"})
    assert resp.status_code == 200
    assert resp.text.startswith("source,target,source_interface")


def test_export_scans_csv():
    _seed()
    resp = client.get("/api/inventory/report/export", params={"report": "scans"})
    assert resp.status_code == 200
    assert resp.text.startswith("id,subnet,status,device_count,links")


def test_export_configs_csv():
    _seed()
    resp = client.get("/api/inventory/report/export", params={"report": "configs"})
    assert resp.status_code == 200
    assert resp.text.startswith("ip,hostname,config_type,collected_at,collected_by,error")


def test_export_invalid_report_returns_400():
    resp = client.get("/api/inventory/report/export", params={"report": "nope"})
    assert resp.status_code == 400
