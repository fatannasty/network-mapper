"""Config collector tests (Sprint 9)."""

from unittest.mock import MagicMock, patch

import config_collector


def test_collect_config_success():
    with patch("config_collector.paramiko.SSHClient") as mock_client_class:
        client = MagicMock()
        mock_client_class.return_value = client

        chan = MagicMock()
        chan.exit_status_ready.return_value = True
        chan.recv_ready.side_effect = [True, False]
        chan.recv.return_value = b"hostname Switch1\n!\ninterface GigabitEthernet1/0/1\n!\nend\n"

        transport = MagicMock()
        transport.open_session.return_value = chan
        client.get_transport.return_value = transport

        result = config_collector.collect_config(
            ip="10.0.0.1", username="admin", password="pass")

        assert "hostname Switch1" in result["config_text"]
        assert result["command"] in ("show running-config", "show run", "display current-configuration")
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
