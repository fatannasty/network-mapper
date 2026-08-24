"""Sprint 13: data-quality features — site mappings, scan_kind, DoD gates,
backfill persistence, and blank classification."""

from conftest import make_client
from database import SessionLocal
from models import Device, Link, ScanJob, SiteMapping
import repositories

admin = make_client("admin")
operator = make_client("operator")


# ── Scan kind ────────────────────────────────────────────────────────────────

def test_create_scan_job_has_scan_kind_default():
    with SessionLocal() as db:
        job = repositories.create_scan_job(db, "sk1", "10.0.0.0/24", ["public"], True)
        assert job.scan_kind == "subnet"
        data = job.to_dict()
        assert data["scan_kind"] == "subnet"


def test_catalyst_import_sets_full_env_scan_kind(monkeypatch):
    """A site-less Catalyst import must be labelled full_env."""
    import catalyst

    def fake_import(base_url, username, password, **kwargs):
        return (
            [{"ip": "10.1.0.1", "hostname": "AMTRCHIIL01S1", "site": "",
              "catalyst_id": "abc123", "vendor": "Cisco", "model": "C9300",
              "device_type": "switch", "confidence": 5, "open_ports": [161],
              "snmp_community": "", "snmp_identified": False, "interfaces": []}],
            [],
            {"errors": []},
        )

    monkeypatch.setattr(catalyst, "import_devices", fake_import)
    resp = operator.post("/api/catalyst/import", json={
        "base_url": "https://catc.example.com", "username": "u", "password": "p",
    })
    assert resp.status_code == 200
    scan_id = resp.json()["scan_id"]
    with SessionLocal() as db:
        job = db.get(ScanJob, scan_id)
        assert job.scan_kind == "full_env"
        dev = db.query(Device).filter(Device.ip == "10.1.0.1").first()
        assert dev.catalyst_id == "abc123"


def test_catalyst_import_site_scan_kind(monkeypatch):
    import catalyst

    def fake_import(base_url, username, password, **kwargs):
        return ([{"ip": "10.1.0.2", "hostname": "x", "site": "Boston",
                  "vendor": "Cisco", "model": "M", "device_type": "switch",
                  "confidence": 5, "open_ports": [], "snmp_community": "",
                  "snmp_identified": False, "interfaces": []}], [], {})

    monkeypatch.setattr(catalyst, "import_devices", fake_import)
    resp = operator.post("/api/catalyst/import", json={
        "base_url": "https://catc.example.com", "username": "u", "password": "p",
        "site_name": "Massachusetts > Boston",
    })
    assert resp.status_code == 200
    with SessionLocal() as db:
        job = db.get(ScanJob, resp.json()["scan_id"])
        assert job.scan_kind == "site:Massachusetts > Boston"


# ── Site mappings ────────────────────────────────────────────────────────────

def test_site_mapping_crud():
    resp = admin.post("/api/inventory/site-mappings", json={"prefix": "AMTRCHIIL", "site": "Chicago"})
    assert resp.status_code == 200
    mid = resp.json()["id"]

    body = admin.get("/api/inventory/site-mappings").json()
    assert body["count"] == 1
    assert body["mappings"][0]["prefix"] == "AMTRCHIIL"

    assert admin.delete(f"/api/inventory/site-mappings/{mid}").status_code == 200
    assert admin.get("/api/inventory/site-mappings").json()["count"] == 0


def test_site_mapping_duplicate_conflict():
    admin.post("/api/inventory/site-mappings", json={"prefix": "DUP", "site": "A"})
    assert admin.post("/api/inventory/site-mappings", json={"prefix": "DUP", "site": "B"}).status_code == 409


def test_site_decoder_chain_prefix():
    import site_decoder
    assert site_decoder.decode("MRSAMTRCHIIL01S.amtrak.ad.nrpc") == "Chicago, IL"
    assert site_decoder.decode("USNRPCPHLPA01S.amtrak.ad.nrpc") == "Philadelphia, PA"
    assert site_decoder.decode("MRSAMTRBEEIN10S") == "Beech Grove, IN"


def test_site_decoder_amtr_block():
    import site_decoder
    assert site_decoder.decode("AMTRMIAFL10S.amtrak.ad.nrpc") == "Miami, FL"
    assert site_decoder.decode("AMTRWASDC01S07") == "Washington, DC"
    assert site_decoder.decode("AMTRNCAMD02S") == "New Carrollton, MD"


def test_site_decoder_legacy_and_overrides():
    import site_decoder
    assert site_decoder.decode("ALB-NY-AP01") == "Albany, NY"
    assert site_decoder.decode("SSY-AP01") == "Sunnyside, NY"
    assert site_decoder.decode("AMTRWASDCIVY01S") == "Washington, DC"
    assert site_decoder.decode("SanDiego-mx67-01") == "San Diego, CA"


def test_site_decoder_unknown_or_conflict_returns_none():
    import site_decoder
    assert site_decoder.decode("MRSAMTRZGOCT03S10") is None
    assert site_decoder.decode("MRSAMTRBERDE01S4") is None  # BER is Berlin CT, hostname says DE
    assert site_decoder.decode("1801-8-AP0") is None
    assert site_decoder.decode("") is None


def test_site_decoder_propose_mappings_longest_prefix_wins():
    import site_decoder
    m = site_decoder.propose_mappings(["ALB-NY-AP01", "ALB-NY-AP02"])
    assert m.get("ALB-NY") == "Albany, NY"
    m2 = site_decoder.propose_mappings(["MRSAMTRCHIIL01S", "MRSAMTRCHIIL02S"])
    assert m2.get("MRSAMTRCHIIL") == "Chicago, IL"
    # unknown hostnames produce no rule
    assert site_decoder.propose_mappings(["MRSAMTRZGOCT03S10"]) == {}


def test_apply_site_mappings_backfills_blank_sites():
    with SessionLocal() as db:
        db.query(Device).delete()
        repositories.create_site_mapping(db, "AMTRCHIIL", "Chicago")
        repositories.upsert_device(db, {
            "ip": "10.9.9.1", "hostname": "AMTRCHIIL01S1", "site": "",
        }, "scan-x")
        repositories.upsert_device(db, {
            "ip": "10.9.9.2", "hostname": "OTHERHOST1", "site": "",
        }, "scan-x")

    resp = operator.post("/api/inventory/site-mappings/apply")
    assert resp.status_code == 200
    assert resp.json()["matched"] == 1
    assert resp.json()["updated"] == 1

    with SessionLocal() as db:
        assert db.query(Device).filter(Device.ip == "10.9.9.1").first().site == "Chicago"
        assert db.query(Device).filter(Device.ip == "10.9.9.2").first().site == ""


def test_seed_site_mappings_from_devices():
    with SessionLocal() as db:
        db.query(SiteMapping).delete()
        repositories.upsert_device(db, {
            "ip": "10.7.0.1", "hostname": "MRSAMTRCH-01", "site": "Chicago",
        }, "scan-y")
        repositories.upsert_device(db, {
            "ip": "10.7.0.2", "hostname": "MRSAMTRWA-02", "site": "Washington",
        }, "scan-y")

    resp = admin.post("/api/inventory/site-mappings/seed")
    assert resp.status_code == 200
    assert resp.json()["created"] >= 1

    with SessionLocal() as db:
        prefixes = [m.prefix for m in repositories.list_site_mappings(db)]
        assert "MRSAMTRCH" in prefixes


# ── Definition of Done gates ─────────────────────────────────────────────────

def test_dod_gates_metrics():
    with SessionLocal() as db:
        db.query(Device).delete()
        db.query(Link).delete()
        db.query(ScanJob).filter(ScanJob.subnet != "sk1").delete()
        repositories.upsert_device(db, {
            "ip": "10.5.0.1", "hostname": "SW1", "device_type": "switch", "site": "Chicago",
        }, "scan-z")
        repositories.upsert_device(db, {
            "ip": "10.5.0.2", "hostname": "SW2", "device_type": "switch", "site": "",
        }, "scan-z")
        repositories.upsert_device(db, {
            "ip": "10.5.0.3", "hostname": "RT1", "device_type": "router", "site": "NY",
        }, "scan-z")
        # one link validated via SNMP, one catalyst (unvalidated)
        db.add(Link(scan_id="scan-z", endpoint_a="10.5.0.1", endpoint_b="10.5.0.3", protocol="lldp"))
        db.add(Link(scan_id="scan-z", endpoint_a="10.5.0.1", endpoint_b="10.5.0.2", protocol="catalyst"))
        db.commit()

    gates = repositories.dod_gates(SessionLocal())
    assert gates["site"]["devices_with_site"] == 2
    assert gates["site"]["devices_total"] == 3
    assert gates["links"]["validated"] == 1
    assert gates["links"]["links_total"] == 2
    assert gates["interfaces"]["target"] == 95
    assert gates["configs"]["target"] == 90


def test_report_includes_dod_gates():
    resp = admin.get("/api/inventory/report")
    assert resp.status_code == 200
    data = resp.json()
    assert "dod_gates" in data
    assert set(data["dod_gates"].keys()) == {"site", "interfaces", "links", "configs"}


# ── Blank classification ─────────────────────────────────────────────────────

def test_classify_blank_devices_ap_and_printer():
    with SessionLocal() as db:
        db.query(Device).delete()
        repositories.upsert_device(db, {
            "ip": "10.6.0.1", "hostname": "BLDN-WRH-AP01", "device_type": "",
        }, "scan-a")
        repositories.upsert_device(db, {
            "ip": "10.6.0.2", "hostname": "printer-x", "device_type": "",
            "open_ports": [80, 9100],
        }, "scan-a")
        repositories.upsert_device(db, {
            "ip": "10.6.0.3", "hostname": "unknown-host", "device_type": "",
        }, "scan-a")

    resp = operator.post("/api/backfill/classify-blanks")
    assert resp.status_code == 200
    assert resp.json()["changed"] == 2

    with SessionLocal() as db:
        by_ip = {d.ip: d for d in db.query(Device).all()}
        assert by_ip["10.6.0.1"].device_type == "accesspoint"
        assert by_ip["10.6.0.2"].device_type == "printer"
        assert by_ip["10.6.0.3"].device_type == ""


# ── Vault communities ────────────────────────────────────────────────────────

def test_vault_communities_dedupe():
    with SessionLocal() as db:
        repositories.create_credential(db, "dq-c1", snmp_community="comm-a")
        repositories.create_credential(db, "dq-c2", snmp_community="comm-a")
        repositories.create_credential(db, "dq-c3", snmp_community="comm-b")
        comms = repositories.vault_communities(db)
        # deduped, ordered by first occurrence, includes our two new ones
        assert comms.count("comm-a") == 1
        assert comms.count("comm-b") == 1
        assert comms.index("comm-a") < comms.index("comm-b")


# ── Backfill endpoints (mocked SNMP) ─────────────────────────────────────────

def test_backfill_interfaces_persists(monkeypatch):
    import backfill as backfill_mod

    def fake_walk(ip, communities, port=None, timeout=None, max_oids=2048):
        return [{"ifIndex": "1", "ifDescr": "Gi0/0", "ifName": "Gi0/0",
                 "ifOperStatus": "up"}]

    monkeypatch.setattr(backfill_mod, "walk_if_table", fake_walk)
    with SessionLocal() as db:
        db.query(Device).delete()
        repositories.upsert_device(db, {
            "ip": "10.4.0.1", "hostname": "SW-1", "device_type": "switch", "site": "X",
        }, "scan-q")

    resp = operator.post("/api/backfill/interfaces", json={"communities": ["public"]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["successful"] == 1
    assert data["persisted_interfaces"] == 1

    with SessionLocal() as db:
        dev = db.query(Device).filter(Device.ip == "10.4.0.1").first()
        assert len(dev.interfaces) == 1
        assert dev.interfaces[0].if_descr == "Gi0/0"


def test_backfill_interfaces_v3(monkeypatch):
    import backfill as backfill_mod
    import snmpv3

    def fake_v3_walk(host, username, auth_protocol="sha", auth_password="",
                     privacy_protocol="none", privacy_password=None,
                     timeout=2.0, port=161, max_oids=1024):
        return [{"ifIndex": "1", "ifDescr": "Gi0/0", "ifName": "Gi0/0",
                 "ifOperStatus": "up"}]

    monkeypatch.setattr(snmpv3, "walk_if_table", fake_v3_walk)
    import vlan as vlan_mod
    monkeypatch.setattr(vlan_mod, "walk_vlans_v3", lambda *a, **k: {})

    with SessionLocal() as db:
        db.query(Device).delete()
        repositories.upsert_device(db, {
            "ip": "10.5.0.1", "hostname": "SW-V3", "device_type": "switch", "site": "X",
        }, "scan-q")

    resp = operator.post("/api/backfill/interfaces", json={
        "snmpv3": {
            "username": "monitor", "auth_protocol": "sha",
            "auth_password": "secret", "privacy_protocol": "aes",
        },
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["successful"] == 1
    assert data["persisted_interfaces"] == 1


def test_backfill_links_creates_validation_scan(monkeypatch):
    import backfill as backfill_mod

    def fake_lldp(host, community, port=161, timeout=2.0):
        return [{"protocol": "lldp", "local_port": "1",
                 "remote_sysname": "CORE-SW2", "remote_port_id": "2"}]

    def fake_cdp(host, community, port=161, timeout=2.0):
        return []

    monkeypatch.setattr(backfill_mod, "collect_lldp_v2c", fake_lldp)
    monkeypatch.setattr(backfill_mod, "collect_cdp_v2c", fake_cdp)

    with SessionLocal() as db:
        db.query(Device).delete()
        db.query(Link).delete()
        repositories.upsert_device(db, {
            "ip": "10.3.0.1", "hostname": "CORE-SW1", "device_type": "core-switch",
        }, "scan-r")
        repositories.upsert_device(db, {
            "ip": "10.3.0.2", "hostname": "CORE-SW2", "device_type": "core-switch",
        }, "scan-r")

    resp = operator.post("/api/backfill/links", json={"communities": ["public"]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["validation_links"] == 1

    with SessionLocal() as db:
        links = db.query(Link).all()
        assert len(links) == 1
        assert links[0].protocol == "lldp"
