"""Collect CDP neighbors via SSH `show cdp neighbors detail`.

Some devices disable CDP over SNMP or require CLI access; this runs the exact
command over SSH (reusing the config-collector shell pattern) and parses the
text output into the same neighbor shape the SNMP report uses.
"""

from __future__ import annotations

import re
import time

import paramiko

from config_collector import ConfigCollectorError, _read_until_prompt

CDP_COMMAND = "show cdp neighbors detail"

CAP_ROUTER = 0x01
CAP_SWITCH = 0x08


def _caps_to_bits(text: str) -> int:
    bits = 0
    lowered = (text or "").lower()
    if "router" in lowered:
        bits |= CAP_ROUTER
    if "switch" in lowered:
        bits |= CAP_SWITCH
    return bits


def _grab(text: str, pattern: str) -> str:
    m = re.search(pattern, text, re.IGNORECASE)
    return m.group(1).strip() if m else ""


def parse_cdp_neighbors_detail(text: str) -> list[dict]:
    """Parse `show cdp neighbors detail` output into per-neighbor dicts."""
    neighbors: list[dict] = []
    for block in re.split(r"-{15,}", text):
        if "Device ID" not in block:
            continue
        ips = re.findall(r"IP address:\s*([0-9]+(?:\.[0-9]+){3})", block)
        caps_text = _grab(block, r"Capabilities:\s*([^\n]+)")
        neighbors.append({
            "protocol": "cdp",
            "remote_device_id": _grab(block, r"Device ID:\s*([^\n]+)"),
            "remote_ip": ips[0] if ips else "",
            "remote_platform": _grab(block, r"Platform:\s*([^,]+)"),
            "remote_capabilities": _caps_to_bits(caps_text),
            "local_port": _grab(block, r"Interface:\s*([^,]+),"),
            "remote_port": _grab(block, r"Port ID \(outgoing port\):\s*([^\n]+)"),
        })
    return neighbors


def collect_cdp_neighbors_detail(ip: str, username: str, password: str,
                                 port: int = 22, timeout: float = 30.0,
                                 command: str = CDP_COMMAND) -> list[dict]:
    """SSH into *ip*, run the CDP command, return parsed neighbors.

    Raises ConfigCollectorError on connection/auth/command failures.
    """
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            ip, port=port, username=username, password=password,
            timeout=timeout, look_for_keys=False, allow_agent=False,
            banner_timeout=15,
        )
    except paramiko.AuthenticationException:
        raise ConfigCollectorError(f"Authentication failed for {username}@{ip}")
    except (OSError, paramiko.SSHException) as e:
        raise ConfigCollectorError(f"Connection to {ip} failed: {e}")

    try:
        shell = client.invoke_shell()
        shell.settimeout(timeout)
        shell.send("terminal length 0\n")
        time.sleep(0.5)
        _read_until_prompt(shell, timeout=15)
        shell.send(command + "\n")
        output = _read_until_prompt(shell, timeout=timeout, min_len=10)
        if not output.strip() or len(output.strip()) < 10:
            raise ConfigCollectorError(
                f"No CDP output received from {ip} for '{command}'")
        return parse_cdp_neighbors_detail(output)
    finally:
        client.close()