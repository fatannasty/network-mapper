#!/usr/bin/env python3
"""Daemonize a command: double-fork + setsid so it runs in its own session.

Usage: python3 detach.py <logfile> <workdir> <cmd> [args...]

The invoking shell returns immediately; the daemon survives the shell's
process-group cleanup (the reason `nohup ... &` alone got killed above).
"""
import os
import sys


def _redirect_to(path: str) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    os.dup2(fd, 0)
    os.dup2(fd, 1)
    os.dup2(fd, 2)
    if fd > 2:
        os.close(fd)


def main() -> int:
    if len(sys.argv) < 4:
        print("usage: detach.py <logfile> <workdir> <cmd> [args...]", file=sys.stderr)
        return 2
    logfile, workdir, cmd = sys.argv[1], sys.argv[2], sys.argv[3:]
    if not cmd:
        return 2

    pid = os.fork()
    if pid > 0:
        os._exit(0)  # parent returns immediately -> shell completes fast
    os.setsid()      # new session / process group / no controlling tty
    pid2 = os.fork()
    if pid2 > 0:
        os._exit(0)

    os.chdir(workdir)
    _redirect_to(logfile)
    try:
        os.execvp(cmd[0], cmd)
    except OSError as exc:
        print(f"exec failed: {exc}", file=sys.stderr)
        return 127


if __name__ == "__main__":
    sys.exit(main())