"""Host discovery and identification.

Pure-stdlib implementation: ICMP ping sweep (via system ping), TCP connect
scan for well-known ports, and a UDP probe for SNMP. Identifies each host by
polling SNMP (when UDP/161 is open) and running the classifier.
"""

from __future__ import annotations

import ipaddress
import socket
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from classifier import NETWORK_DEVICE_TYPES, DEVICE_TYPE_ORDER, classify
from snmp import SNMP_PORT, snmp_poll

TCP_PORTS = [22, 23, 80, 443, 3389, 8080, 8443]
PORT_SCAN_TIMEOUT = 0.8
PING_TIMEOUT_MS = 1000
SNMP_PROBE_TIMEOUT = 0.6


# ── CIDR helpers ─────────────────────────────────────────────────────────────

def hosts_from_cidr(cidr: str) -> list[str]:
    try:
        return [str(ip) for ip in ipaddress.ip_network(cidr, strict=False).hosts()]
    except ValueError as exc:
        raise ValueError(f"Invalid CIDR '{cidr}': {exc}") from exc


def local_ip() -> str:
    """Best-effort local IPv4 address (first non-loopback interface)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


# ── Probes ───────────────────────────────────────────────────────────────────

def ping_host(ip: str) -> bool:
    """ICMP ping via system ping; returns True if the host is alive."""
    cmd = ["ping", "-c", "1", "-W", str(PING_TIMEOUT_MS // 1000)]
    if sys.platform == "darwin":
        cmd = ["ping", "-c", "1", "-W", str(PING_TIMEOUT_MS), ip]
    else:
        cmd = ["ping", "-c", "1", "-W", str(PING_TIMEOUT_MS // 1000), ip]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=2)
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def tcp_port_open(ip: str, port: int) -> bool:
    try:
        with socket.create_connection((ip, port), timeout=PORT_SCAN_TIMEOUT):
            return True
    except OSError:
        return False


def udp_port_open(ip: str, port: int = SNMP_PORT, timeout: float = SNMP_PROBE_TIMEOUT) -> bool:
    """Connected UDP probe.

    An ICMP port-unreachable surfaces as ECONNREFUSED on a connected UDP
    socket (closed port -> False). Silence is treated as open to avoid
    false negatives on networks that filter ICMP unreachable.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        sock.connect((ip, port))
        sock.send(b"\x00")
        try:
            sock.recv(1)
            return True
        except socket.timeout:
            return True
    except OSError:
        return False
    finally:
        sock.close()


# ── Identification ───────────────────────────────────────────────────────────

def identify_host(ip: str, communities: list[str], snmp_port: int = SNMP_PORT) -> dict:
    """Port-scan one host, optionally SNMP-poll it, and classify."""
    tcp_ports = [p for p in TCP_PORTS if tcp_port_open(ip, p)]
    snmp_open = udp_port_open(ip, snmp_port)
    open_ports = sorted(tcp_ports + ([snmp_port] if snmp_open else []))

    snmp_data = None
    if snmp_open:
        snmp_data = snmp_poll(ip, communities, port=snmp_port)

    hostname = snmp_data.get("sysName", "") if snmp_data else ""
    cls = classify(snmp_data, hostname=hostname)

    device = {
        "ip": ip,
        "open_ports": open_ports,
        "hostname": hostname,
        "vendor": cls.vendor,
        "model": cls.model,
        "device_type": cls.device_type,
        "confidence": cls.confidence,
        "snmp_community": snmp_data.get("community", "") if snmp_data else "",
    }
    return device


# ── Orchestration ────────────────────────────────────────────────────────────

def discover(cidr: str, communities: list[str] | None = None, exclude_pcs: bool = True,
             progress_cb=None, snmp_port: int = SNMP_PORT) -> dict:
    """Scan a subnet and return identified devices plus summary stats."""
    communities = communities or ["public"]
    hosts = hosts_from_cidr(cidr)

    def report(percent: float, phase: str):
        if progress_cb:
            progress_cb({"phase": phase, "percent": int(percent)})

    report(0, "ping")

    alive: list[str] = []
    with ThreadPoolExecutor(max_workers=64) as pool:
        futures = {pool.submit(ping_host, ip): ip for ip in hosts}
        for future in as_completed(futures):
            if future.result():
                alive.append(futures[future])

    alive.sort(key=lambda ip: int(ipaddress.ip_address(ip)))
    report(50, "identify")

    devices: list[dict] = []
    with ThreadPoolExecutor(max_workers=32) as pool:
        futures = {pool.submit(identify_host, ip, communities, snmp_port): ip for ip in alive}
        for future in as_completed(futures):
            try:
                devices.append(future.result())
            except Exception:
                continue
            report(50 + 50 * len(devices) / max(len(alive), 1), "identify")

    devices.sort(key=lambda d: (
        DEVICE_TYPE_ORDER.get(d["device_type"], 99),
        int(ipaddress.ip_address(d["ip"])),
    ))

    if exclude_pcs:
        devices = [d for d in devices if d["device_type"] in NETWORK_DEVICE_TYPES]

    snmp_identified = sum(1 for d in devices if d["snmp_community"])
    report(100, "done")

    return {
        "subnet": cidr,
        "local_ip": local_ip(),
        "scanned_hosts": len(hosts),
        "alive_hosts": len(alive),
        "device_count": len(devices),
        "snmp_identified": snmp_identified,
        "devices": devices,
        "connections": [],
    }
