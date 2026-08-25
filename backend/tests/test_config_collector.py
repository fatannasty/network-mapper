"""Config collector tests (Sprint 9)."""

from unittest.mock import MagicMock, patch

import config_collector


def _fast_time():
    """Return a mock time.time() that ticks 0.05s each call."""
    t = [0]
    def _time():
        t[0] += 0.05
        return t[0]
    return _time


def test_collect_config_no_output():
    with patch("config_collector.paramiko.SSHClient") as mock_client_class, \
         patch("config_collector.time.sleep"), \
         patch("config_collector.time.time") as mock_time:
        client = MagicMock()
        mock_client_class.return_value = client

        shell = MagicMock()
        shell.recv_ready.return_value = False
        shell.recv.return_value = b""
        client.invoke_shell.return_value = shell
        mock_time.side_effect = _fast_time()

        try:
            config_collector.collect_config(ip="10.0.0.1", username="a", password="b")
            assert False, "expected error"
        except config_collector.ConfigCollectorError as e:
            assert "No config output" in str(e)


def test_collect_config_gets_output():
    with patch("config_collector.paramiko.SSHClient") as mock_client_class, \
         patch("config_collector.time.sleep"), \
         patch("config_collector.time.time") as mock_time:
        client = MagicMock()
        mock_client_class.return_value = client

        shell = MagicMock()
        # recv_ready: True only at specific call #s (1-based)
        call = [0]
        def _ready():
            call[0] += 1
            return call[0] == 2 or call[0] == 35
        shell.recv_ready.side_effect = _ready
        shell.recv.side_effect = iter([
            b"#\n",
            b"hostname Switch1\n!\ninterface GigabitEthernet1/0/1\n switchport mode access\n switchport access vlan 10\n!\ninterface GigabitEthernet1/0/2\n switchport mode trunk\n!\nend\n\nSwitch#\n",
        ])
        client.invoke_shell.return_value = shell
        mock_time.side_effect = _fast_time()

        result = config_collector.collect_config(
            ip="10.0.0.1", username="admin", password="pass")

        assert "hostname Switch1" in result["config_text"]
        client.connect.assert_called_once()
        client.close.assert_called_once()


def test_collect_config_auth_failure():
    with patch("config_collector.paramiko.SSHClient") as mock_client_class:
        client = MagicMock()
        mock_client_class.return_value = client
        import paramiko
        client.connect.side_effect = paramiko.AuthenticationException()

        try:
            config_collector.collect_config(
                ip="10.0.0.1", username="bad", password="bad")
            assert False, "expected ConfigCollectorError"
        except config_collector.ConfigCollectorError as e:
            assert "Authentication failed" in str(e)


def test_collect_config_connection_failure():
    with patch("config_collector.paramiko.SSHClient") as mock_client_class:
        client = MagicMock()
        mock_client_class.return_value = client
        client.connect.side_effect = OSError("Connection refused")

        try:
            config_collector.collect_config(
                ip="10.0.0.1", username="admin", password="pass")
            assert False, "expected ConfigCollectorError"
        except config_collector.ConfigCollectorError as e:
            assert "Connection" in str(e) or "refused" in str(e)


def test_config_diff_and_changes():
    from database import SessionLocal
    from models import Device, DeviceConfig
    from fastapi.testclient import TestClient
    import main

    with SessionLocal() as db:
        db.query(DeviceConfig).filter(DeviceConfig.device_id.in_(
            db.query(Device.id).filter(Device.site == "DiffSite"))).delete(synchronize_session=False)
        db.query(Device).filter(Device.site == "DiffSite").delete()
        d = Device(ip="10.6.0.1", hostname="SW-DIFF", device_type="switch", site="DiffSite")
        db.add(d)
        db.flush()
        c1 = DeviceConfig(device_id=d.id, config_text="hostname SW-DIFF\ninterface Gi1\n vlan 10\n", config_type="running")
        db.add(c1)
        db.flush()
        c2 = DeviceConfig(device_id=d.id, config_text="hostname SW-DIFF\ninterface Gi1\n vlan 20\n", config_type="running")
        db.add(c2)
        db.commit()
        c1_id, c2_id, dev_id = c1.id, c2.id, d.id

    from conftest import make_client

    client = make_client("admin")

    resp = client.get("/api/inventory/config-diff",
                      params={"device_id": dev_id, "from_id": c1_id, "to_id": c2_id})
    assert resp.status_code == 200
    data = resp.json()
    assert data["changed"] is True
    assert data["added"] >= 1
    assert data["removed"] >= 1
    assert any(r["type"] == "add" for r in data["diff"])

    changes = client.get("/api/inventory/config-changes").json()
    assert changes["count"] >= 1
    assert any(c["ip"] == "10.6.0.1" for c in changes["changes"])
