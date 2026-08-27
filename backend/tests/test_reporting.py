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


def test_exec_health_summary():
    from fastapi.testclient import TestClient
    from database import SessionLocal
    from models import Device, Interface
    import main

    with SessionLocal() as db:
        db.query(Device).filter(Device.site == "ExecSite").delete()
        d_up = Device(ip="10.30.0.1", hostname="SW-UP", device_type="switch", site="ExecSite")
        d_dn = Device(ip="10.30.0.2", hostname="SW-DN", device_type="switch", site="ExecSite")
        db.add_all([d_up, d_dn])
        db.flush()
        db.add_all([
            Interface(device_id=d_up.id, if_name="Gi1", if_oper_status="up"),
            Interface(device_id=d_dn.id, if_name="Gi1", if_oper_status="down"),
        ])
        db.commit()

    client = TestClient(main.app)
    client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    data = client.get("/api/health/exec").json()

    assert data["total_devices"] >= 2
    assert "spof_count" in data["kpis"]
    assert "config_coverage" in data["kpis"]
    assert data["state"] in ("healthy", "warning", "critical")
    assert isinstance(data["sites"], list)
    assert isinstance(data["risks"], list)
    # One of the risk rows should be our down switch.
    ips = {r["ip"] for r in data["risks"]}
    assert "10.30.0.2" in ips


def test_exec_report_generate_and_serve():
    from conftest import make_client

    client = make_client("admin")
    meta = client.post("/api/report/executive/generate").json()
    assert "id" in meta and meta["id"] > 0

    lst = client.get("/api/report/executive").json()
    assert any(r["id"] == meta["id"] for r in lst["reports"])

    html = client.get(f"/api/report/executive/{meta['id']}")
    assert html.status_code == 200
    assert "Executive Network Health Report" in html.text

    pdf = client.get(f"/api/report/executive/{meta['id']}/pdf")
    assert pdf.status_code == 200
    assert pdf.headers.get("content-type", "").startswith("application/pdf")
    assert len(pdf.content) > 200


def test_exec_pdf_robust_and_has_charts():
    import os
    import tempfile
    from reports import build_exec_pdf, _status_donut, _coverage_bars, _score_line, _util_bars

    # Empty/edge data must never crash the PDF.
    summary = {"total_devices": 0, "state": "healthy", "score": 0,
               "kpis": {}, "sites": [], "risks": [], "spof_devices": []}
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "empty.pdf")
        build_exec_pdf(summary, p, history=[], top_util=[])
        assert os.path.getsize(p) > 100
        assert open(p, "rb").read()[:5] == b"%PDF-"

    # Chart builders degrade to None (skipped) when there's nothing to draw.
    assert _status_donut({"kpis": {}}) is None
    assert _score_line([]) is None
    assert _util_bars([]) is None

    # And produce drawings when data is present.
    assert _status_donut({"kpis": {"devices_up": 10, "devices_down": 2}}) is not None
    assert _coverage_bars({"kpis": {"site_coverage": 50, "interface_coverage": 60,
                                    "config_coverage": 70, "link_validation": 80}}) is not None
    assert _score_line([{"score": 50}, {"score": 60}]) is not None
    assert _util_bars([{"hostname": "sw1", "ip": "10.0.0.1", "if_name": "Gi1",
                        "avg_in_rate": 1e6, "avg_out_rate": 5e5}]) is not None

    # Full PDF build with real history + utilization (regression: line chart
    # data must be y-values, not (x, y) tuples).
    summary = {"total_devices": 120, "state": "warning", "score": 70,
               "kpis": {"devices_up": 100, "devices_down": 5, "devices_degraded": 3,
                        "devices_flapping": 2, "devices_unknown": 10,
                        "up_pct": 85.8, "config_coverage": 88, "site_coverage": 92,
                        "interface_coverage": 95, "link_validation": 70},
               "sites": [{"site": "Chicago", "devices": 60, "up": 55, "down": 2,
                          "degraded": 1, "flapping": 1, "unknown": 1}],
               "risks": [], "spof_devices": []}
    history = [{"t": f"2026-01-0{i}T00:00:00", "score": s} for i, s in enumerate([70, 72, 71, 75, 74])]
    top_util = [{"hostname": f"sw{i}", "ip": f"10.0.0.{i}", "if_name": "Gi1",
                 "avg_in_rate": 1e6, "avg_out_rate": 5e5} for i in range(1, 4)]
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "charts.pdf")
        build_exec_pdf(summary, p, history=history, top_util=top_util)
        assert os.path.getsize(p) > 500
        assert open(p, "rb").read()[:5] == b"%PDF-"


def test_delete_exec_report_removes_pdf():
    import os
    from conftest import make_client
    import reports

    client = make_client("admin")
    meta = client.post("/api/report/executive/generate").json()
    rid = meta["id"]
    path = reports.pdf_path(rid)
    assert os.path.exists(path)

    resp = client.delete(f"/api/report/executive/{rid}")
    assert resp.status_code == 200 and resp.json()["deleted"] is True
    assert not os.path.exists(path)

    assert client.get(f"/api/report/executive/{rid}").status_code == 404
    lst = client.get("/api/report/executive").json()
    assert all(r["id"] != rid for r in lst["reports"])


def test_catalyst_import_recomputes_vlan90():
    from unittest.mock import patch
    from conftest import make_client
    from database import SessionLocal
    from models import Device, DeviceConfig
    import catalyst, main

    # A stored config that references VLAN 90; import will wipe vlan_90 then
    # the recompute must restore it.
    with SessionLocal() as db:
        db.query(Device).filter(Device.site == "V90Import").delete()
        d = Device(ip="10.12.0.1", hostname="SW-V90I", device_type="switch", site="V90Import")
        db.add(d)
        db.flush()
        db.add(DeviceConfig(device_id=d.id, config_text="interface Vlan90\n", config_type="running"))
        db.commit()
        dev_id = d.id
    with SessionLocal() as db:
        dev = db.get(Device, dev_id)
        dev.vlan_90 = None  # simulate an import wiping the flag
        db.commit()

    import_dev = [{
        "ip": "10.12.0.1", "hostname": "SW-V90I", "vendor": "Cisco",
        "model": "C9300", "device_type": "switch", "site": "V90Import",
        "confidence": 5, "open_ports": [161], "snmp_community": "",
        "interfaces": [], "neighbors": [], "_id": "xyz",
        "vlan_90": None,
    }]
    client = make_client("operator")
    with patch.object(catalyst, "import_devices",
                      return_value=(import_dev, [], {"raw_devices": 1})), \
         patch.object(catalyst, "authenticate", return_value="t"):
        resp = client.post("/api/catalyst/import", json={
            "base_url": "https://cc", "username": "u", "password": "p",
        })
    assert resp.status_code == 200
    assert resp.json()["debug"]["vlan90_after_import"]["vlan90_detected"] >= 1

    with SessionLocal() as db:
        assert db.get(Device, dev_id).vlan_90 is True
        db.query(DeviceConfig).filter(DeviceConfig.device_id == dev_id).delete()
        db.query(Device).filter(Device.id == dev_id).delete()
        db.commit()
