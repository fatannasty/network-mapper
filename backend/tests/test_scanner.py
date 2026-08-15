"""Scanner tests: CIDR parsing and localhost probing (no external network needed)."""

import socket

import pytest

import scanner


def test_hosts_from_cidr():
    hosts = scanner.hosts_from_cidr("192.168.0.0/30")
    assert hosts == ["192.168.0.1", "192.168.0.2"]


def test_hosts_from_cidr_invalid():
    with pytest.raises(ValueError):
        scanner.hosts_from_cidr("not-a-cidr")


def test_hosts_from_cidr_single_host():
    assert scanner.hosts_from_cidr("127.0.0.1/32") == ["127.0.0.1"]


def test_tcp_port_open_on_local_listener():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        port = srv.getsockname()[1]
        assert scanner.tcp_port_open("127.0.0.1", port) is True
    # Socket closed now.
    assert scanner.tcp_port_open("127.0.0.1", port) is False


def test_tcp_port_open_closed():
    assert scanner.tcp_port_open("127.0.0.1", 1) is False


def test_udp_port_open_listener():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as srv:
        srv.bind(("127.0.0.1", 0))
        port = srv.getsockname()[1]
        assert scanner.udp_port_open("127.0.0.1", port, timeout=0.5) is True


def test_udp_port_open_closed():
    # Port 1 on loopback: connect() succeeds (UDP), then ICMP unreachable.
    assert scanner.udp_port_open("127.0.0.1", 1, timeout=0.5) is False


def test_local_ip_is_an_ip():
    ip = scanner.local_ip()
    parts = ip.split(".")
    assert len(parts) == 4 and all(0 <= int(p) <= 255 for p in parts)


class _FakeResult:
    def __init__(self, returncode, stdout):
        self.returncode = returncode
        self.stdout = stdout


def test_ping_parses_latency(monkeypatch):
    monkeypatch.setattr(
        scanner.subprocess, "run",
        lambda *a, **k: _FakeResult(0, b"64 bytes from 1.2.3.4: icmp_seq=0 ttl=64 time=2.345 ms\n"),
    )
    ok, lat = scanner._ping("1.2.3.4")
    assert ok is True
    assert lat == pytest.approx(2.345)


def test_ping_unreachable_has_no_latency(monkeypatch):
    monkeypatch.setattr(scanner.subprocess, "run", lambda *a, **k: _FakeResult(1, b""))
    ok, lat = scanner._ping("1.2.3.4")
    assert ok is False
    assert lat is None


def test_discover_loopback_smoke():
    result = scanner.discover("127.0.0.1/32", communities=["public"])
    assert result["subnet"] == "127.0.0.1/32"
    assert result["scanned_hosts"] == 1
    assert result["alive_hosts"] == 1
    assert result["device_count"] <= 1
    assert isinstance(result["devices"], list)
