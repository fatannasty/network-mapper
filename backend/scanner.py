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
from snmp import SNMP_PORT, _to_str, snmp_poll
from snmpv3 import (AUTH_MD5, AUTH_NONE, AUTH_SHA, PRIV_AES, PRIV_DES, PRIV_NONE,
                    snmpv3_get, walk_if_table)
from topology import build_links

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

def snmpv3_poll(host: str, params: dict, snmp_port: int = SNMP_PORT,
                timeout: float = 2.0) -> dict | None:
    """SNMPv3 poll using the given USM params dict."""
    auth_protocol = (params.get("auth_protocol") or AUTH_SHA).lower()
    privacy_protocol = (params.get("privacy_protocol") or PRIV_NONE).lower()
    if auth_protocol not in (AUTH_MD5, AUTH_SHA, AUTH_NONE):
        raise ValueError(f"unsupported auth_protocol: {auth_protocol}")
    if privacy_protocol not in (PRIV_AES, PRIV_DES, PRIV_NONE):
        raise ValueError(f"unsupported privacy_protocol: {privacy_protocol}")
    if auth_protocol != AUTH_NONE and not params.get("auth_password"):
        raise ValueError("auth_password is required for SNMPv3 auth")
    if privacy_protocol != PRIV_NONE and not params.get("privacy_password") and not params.get("auth_password"):
        raise ValueError("privacy_password is required for SNMPv3 privacy")

    result = snmpv3_get(
        host,
        username=params["username"],
        auth_protocol=auth_protocol,
        auth_password=params.get("auth_password", ""),
        privacy_protocol=privacy_protocol,
        privacy_password=params.get("privacy_password") or params.get("auth_password", ""),
        timeout=timeout,
        port=snmp_port,
    )
    if result is None:
        return None
    result["community"] = ""
    return result


def snmpv3_interfaces(host: str, params: dict, snmp_port: int = SNMP_PORT,
                      timeout: float = 2.0) -> list[dict]:
    """Walk ifTable + ifXTable for an SNMPv3 device; [] on failure."""
    auth_protocol = (params.get("auth_protocol") or AUTH_SHA).lower()
    privacy_protocol = (params.get("privacy_protocol") or PRIV_NONE).lower()
    try:
        return walk_if_table(
            host,
            username=params["username"],
            auth_protocol=auth_protocol,
            auth_password=params.get("auth_password", ""),
            privacy_protocol=privacy_protocol,
            privacy_password=params.get("privacy_password") or params.get("auth_password", ""),
            timeout=timeout,
            port=snmp_port,
        )
    except (socket.timeout, OSError, ValueError):
        return []


def identify_host(ip: str, communities: list[str], snmp_port: int = SNMP_PORT,
                  snmpv3: dict | None = None) -> dict:
    """Port-scan one host, optionally SNMP-poll it (v2c or v3), and classify."""
    tcp_ports = [p for p in TCP_PORTS if tcp_port_open(ip, p)]
    snmp_open = udp_port_open(ip, snmp_port)
    open_ports = sorted(tcp_ports + ([snmp_port] if snmp_open else []))

    snmp_debug: dict = {"port_open": snmp_open, "communities_tried": communities if not snmpv3 else [],
                       "community_used": "", "vendor": "", "sys_name": "", "error": ""}
    snmp_data = None
    if snmp_open:
        if snmpv3:
            snmp_data = snmpv3_poll(ip, snmpv3, snmp_port=snmp_port)
            snmp_debug["communities_tried"] = ["(snmpv3)"]
        else:
            snmp_data = snmp_poll(ip, communities, port=snmp_port)
        if snmp_data:
            snmp_debug["community_used"] = snmp_data.get("community", "")
            snmp_debug["vendor"] = _to_str(snmp_data.get("sysDescr", ""))[:80]
            snmp_debug["sys_name"] = _to_str(snmp_data.get("sysName", ""))
        else:
            snmp_debug["error"] = "No response to any community"
    else:
        snmp_debug["error"] = "SNMP port not open"

    hostname = snmp_data.get("sysName", "") if snmp_data else ""
    snmp_debug["hostname"] = hostname
    if not hostname:
        try:
            hostname = socket.gethostbyaddr(ip)[0]
            snmp_debug["hostname"] = hostname
            snmp_debug["hostname_source"] = "reverse dns"
        except (socket.herror, socket.gaierror, OSError):
            pass
    cls = classify(snmp_data, hostname=hostname)

    interfaces: list[dict] = []
    if snmp_data and snmpv3:
        interfaces = snmpv3_interfaces(ip, snmpv3, snmp_port=snmp_port)

    device = {
        "ip": ip,
        "open_ports": open_ports,
        "hostname": hostname,
        "vendor": cls.vendor,
        "model": cls.model,
        "device_type": cls.device_type,
        "confidence": cls.confidence,
        "snmp_community": snmp_data.get("community", "") if snmp_data else "",
        "snmp_identified": bool(snmp_data),
        "interfaces": interfaces,
        "snmp_debug": snmp_debug,
    }
    return device


# ── Topology collection (Sprint 5) ───────────────────────────────────────────

def _neighbors_v2c(host: str, community: str, snmp_port: int, timeout: float) -> list[dict]:
    from topology import collect_cdp_v2c, collect_lldp_v2c

    try:
        return collect_lldp_v2c(host, community, port=snmp_port, timeout=timeout) \
            + collect_cdp_v2c(host, community, port=snmp_port, timeout=timeout)
    except (socket.timeout, OSError, ValueError):
        return []


def _neighbors_v3(host: str, params: dict, snmp_port: int, timeout: float) -> list[dict]:
    from topology import collect_cdp_v3, collect_lldp_v3

    auth_protocol = (params.get("auth_protocol") or AUTH_SHA).lower()
    privacy_protocol = (params.get("privacy_protocol") or PRIV_NONE).lower()
    try:
        return collect_lldp_v3(host, params["username"], auth_protocol=auth_protocol,
                               auth_password=params.get("auth_password", ""),
                               privacy_protocol=privacy_protocol,
                               privacy_password=params.get("privacy_password") or params.get("auth_password", ""),
                               port=snmp_port, timeout=timeout) \
            + collect_cdp_v3(host, params["username"], auth_protocol=auth_protocol,
                             auth_password=params.get("auth_password", ""),
                             privacy_protocol=privacy_protocol,
                             privacy_password=params.get("privacy_password") or params.get("auth_password", ""),
                             port=snmp_port, timeout=timeout)
    except (socket.timeout, OSError, ValueError):
        return []


def collect_topology(devices: list[dict], communities: list[str] | None = None,
                     snmpv3: dict | None = None, snmp_port: int = SNMP_PORT,
                     timeout: float = 2.0, progress_cb=None) -> dict[str, list[dict]]:
    """Walk LLDP/CDP on each SNMP-identified device; return {ip: [neighbors]}."""
    communities = communities or ["public"]

    def report(percent: float, phase: str):
        if progress_cb:
            progress_cb(percent, phase)

    report(50, "topology")
    identified = [d for d in devices if d.get("snmp_identified")]
    neighbors_by_ip: dict[str, list[dict]] = {}

    if identified:
        def work(device: dict):
            if snmpv3:
                return device["ip"], _neighbors_v3(device["ip"], snmpv3, snmp_port, timeout)
            community = device.get("snmp_community") or communities[0]
            return device["ip"], _neighbors_v2c(device["ip"], community, snmp_port, timeout)

        with ThreadPoolExecutor(max_workers=16) as pool:
            futures = [pool.submit(work, d) for d in identified]
            done = 0
            for future in as_completed(futures):
                ip, neighbors = future.result()
                neighbors_by_ip[ip] = neighbors
                done += 1
                report(50 + 50 * done / max(len(identified), 1), "topology")

    report(100, "topology")
    return neighbors_by_ip


# ── Orchestration ────────────────────────────────────────────────────────────

def discover(cidr: str, communities: list[str] | None = None, exclude_pcs: bool = True,
             progress_cb=None, snmp_port: int = SNMP_PORT,
             snmpv3: dict | None = None, verbose: bool = False) -> dict:
    """Scan a subnet and return identified devices plus summary stats.

    When verbose=True, each device includes an 'snmp_debug' dict with
    SNMP port status, communities tried, community used, vendor string,
    and any errors.
    """
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
        futures = {pool.submit(identify_host, ip, communities, snmp_port, snmpv3): ip for ip in alive}
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

    neighbors = collect_topology(devices, communities, snmpv3=snmpv3,
                                 snmp_port=snmp_port, progress_cb=report)
    for device in devices:
        device["neighbors"] = neighbors.get(device["ip"], [])
    connections = build_links(devices)

    snmp_identified = sum(1 for d in devices if d.get("snmp_identified"))
    report(100, "done")

    return {
        "subnet": cidr,
        "local_ip": local_ip(),
        "scanned_hosts": len(hosts),
        "alive_hosts": len(alive),
        "device_count": len(devices),
        "snmp_identified": snmp_identified,
        "devices": devices,
        "connections": connections,
    }
