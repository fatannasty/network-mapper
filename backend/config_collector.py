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
        # Use interactive shell so we can send 'terminal length 0' before
        # the config command and avoid Cisco --More-- pagination issues.
        shell = client.invoke_shell()
        shell.settimeout(timeout)

        # Disable pagination on Cisco / similar switches
        shell.send("terminal length 0\n")
        time.sleep(0.5)

        # Drain the banner + initial prompt
        banner = _read_until_prompt(shell, timeout=15)

        # Try commands in order
        if command:
            cmds_to_try = [command]
        else:
            cmds_to_try = list(SWITCH_COMMANDS)

        for cmd in cmds_to_try:
            shell.send(cmd + "\n")
            config_text = _read_until_prompt(shell, timeout=timeout, min_len=50)
            if config_text.strip() and len(config_text.strip()) > 50:
                used_command = cmd
                break
            config_text = ""

        # Try to grab show version for context
        if version_text or config_text:
            for cmd in BACKUP_COMMANDS:
                shell.send(cmd + "\n")
                v = _read_until_prompt(shell, timeout=10, min_len=20)
                if v.strip():
                    version_text = v[:2000]
                    break

        shell.close()
    finally:
        client.close()

    if not config_text.strip():
        raise ConfigCollectorError(
            f"No config output received from {ip} (banner: {banner[:200]!r}, "
            f"used cmd: {used_command})")

    return {
        "config_text": config_text,
        "command": used_command,
        "version_info": version_text[:2000] if version_text else "",
    }


def _read_until_prompt(shell: paramiko.Channel, timeout: float,
                       min_len: int = 0) -> str:
    """Read from an interactive shell until a switch prompt appears or timeout.

    A prompt is detected when the accumulated output ends with common
    switch/router prompt characters (``#``, ``>``, ``]``) followed by
    trailing whitespace after a brief quiet period.
    """
    PROMPT_SUFFIXES = ("#", ">", "]#", ")>", ")#", ")> ", ":$ ", "$ ")
    deadline = time.time() + timeout
    chunks: list[bytes] = []
    quiet_start = 0.0

    while time.time() < deadline:
        if shell.recv_ready():
            chunks.append(shell.recv(65536))
            quiet_start = time.time()
        elif quiet_start == 0:
            quiet_start = time.time()
        elif time.time() - quiet_start > 2.0 and chunks:
            # Been quiet 2+ seconds — check for prompt
            text = b"".join(chunks).decode("utf-8", errors="replace")
            stripped = text.rstrip()
            if stripped and any(stripped.endswith(s) for s in PROMPT_SUFFIXES):
                break
            if min_len and len(stripped) >= min_len:
                break
        time.sleep(0.05)

    while shell.recv_ready():
        chunks.append(shell.recv(65536))

    raw = b"".join(chunks).decode("utf-8", errors="replace")
    # Strip the command line (first line) and trailing prompt
    lines = [l for l in raw.split("\n")]
    if lines and any(cmd_word in lines[0].lower()
                     for cmd_word in ("show", "display", "terminal")):
        lines = lines[1:]
    # Drop the trailing prompt line (last non-empty line if it ends with a prompt suffix)
    for i in range(len(lines) - 1, -1, -1):
        line = lines[i].rstrip()
        if line and any(line.endswith(s) for s in PROMPT_SUFFIXES):
            lines = lines[:i]
            break
    return "\n".join(lines)
