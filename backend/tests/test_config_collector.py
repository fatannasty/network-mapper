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
