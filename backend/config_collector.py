"""SSH configuration collection (Sprint 9).

Connects to switches via SSH, runs 'show running-config', and returns
the output text. Handles Cisco IOS/IOS-XE, ArubaOS-Switch, and other
common switch platforms.
"""

from __future__ import annotations

import time
from typing import Optional

import paramiko

# Commands to try in order, with lightweight fallbacks
SWITCH_COMMANDS = [
    "show running-config",
    "show run",
    "display current-configuration",  # H3C / Comware
]

BACKUP_COMMANDS = [
    "show version",
    "show system",
]


class ConfigCollectorError(Exception):
    pass


def collect_config(
    ip: str,
    username: str = "",
    password: str = "",
    port: int = 22,
    timeout: float = 30.0,
    command: Optional[str] = None,
) -> dict:
    """SSH into *ip*, run the switch config command, return {config_text, command, version_info}.

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

    config_text = ""
    version_text = ""
    used_command = (command or SWITCH_COMMANDS[0])

    try:
        chan = client.get_transport().open_session()
        chan.settimeout(timeout)

        # Run the main config command
        if command:
            cmds_to_try = [command]
        else:
            cmds_to_try = list(SWITCH_COMMANDS)

        for cmd in cmds_to_try:
            chan.exec_command(cmd)
            config_text = _read_channel(chan, timeout)
            if config_text and "invalid" not in config_text.lower().startswith("invalid") and len(config_text) > 50:
                used_command = cmd
                break
            config_text = ""

        # Try to grab show version for context
        try:
            chan2 = client.get_transport().open_session()
            chan2.settimeout(timeout)
            for cmd in BACKUP_COMMANDS:
                chan2.exec_command(cmd)
                v = _read_channel(chan2, timeout)
                if v and len(v) > 20:
                    version_text = v
                    break
        except Exception:
            pass
    finally:
        client.close()

    if not config_text.strip():
        raise ConfigCollectorError(f"No config output received from {ip}")

    return {
        "config_text": config_text,
        "command": used_command,
        "version_info": version_text[:2000] if version_text else "",
    }


def _read_channel(chan: paramiko.Channel, timeout: float) -> str:
    """Read all output from a channel, waiting for EOF or timeout."""
    deadline = time.time() + timeout
    chunks: list[bytes] = []
    while time.time() < deadline:
        if chan.exit_status_ready():
            break
        if chan.recv_ready():
            chunks.append(chan.recv(65536))
        else:
            time.sleep(0.1)
    # Drain any remaining data
    while chan.recv_ready():
        chunks.append(chan.recv(65536))
    return b"".join(chunks).decode("utf-8", errors="replace")
