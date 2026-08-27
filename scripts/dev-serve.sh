#!/bin/bash
# Start the network-mapper dev servers DETACHED (daemonized).
#
# Why: processes started with `npm run start` in a terminal get suspended
# (SIGSTOP) when the terminal session is suspended/closed, which looks like a
# hang. This script daemonizes them (double-fork + setsid via detach.py) so
# they run in their own session: no terminal, survive close, can't be Ctrl+Z'd.
# (launchd is NOT viable because macOS TCC blocks background processes from
# reading ~/Documents.)
#
# Usage:
#   ./scripts/dev-serve.sh          # start both servers
#   ./scripts/dev-serve.sh status   # show running processes
#   ./scripts/dev-serve.sh stop     # stop both servers
#
# Logs: /tmp/nm-backend.log, /tmp/nm-frontend.log

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DETACH="$ROOT/scripts/detach.py"
PYTHON="$(command -v python3 || echo /usr/bin/python3)"

# Load optional environment (SMTP, report schedule, poll intervals...) from
# $ROOT/.env if present, so daemonized servers pick up the same config as Docker.
if [ -f "$ROOT/.env" ]; then
  set -a
  . "$ROOT/.env"
  set +a
fi

start_backend() {
  if lsof -tiTCP:8000 -sTCP:LISTEN >/dev/null 2>&1; then
    echo "backend already listening on :8000"
  else
    "$PYTHON" "$DETACH" /tmp/nm-backend.log "$ROOT/backend" \
      "$ROOT/backend/.venv/bin/uvicorn" main:app --host 0.0.0.0 --port 8000 --reload
    echo "backend started -> /tmp/nm-backend.log"
  fi
}

start_frontend() {
  if lsof -tiTCP:5173 -sTCP:LISTEN >/dev/null 2>&1; then
    echo "frontend already listening on :5173"
  else
    "$PYTHON" "$DETACH" /tmp/nm-frontend.log "$ROOT/frontend" \
      /usr/local/bin/node "$ROOT/frontend/node_modules/vite/bin/vite.js" --port 5173 --strictPort
    echo "frontend started -> /tmp/nm-frontend.log"
  fi
}

case "${1:-start}" in
  status)
    echo "backend:";  lsof -nP -iTCP:8000 -sTCP:LISTEN 2>/dev/null | tail -n +2 || echo "  not running"
    echo "frontend:"; lsof -nP -iTCP:5173 -sTCP:LISTEN 2>/dev/null | tail -n +2 || echo "  not running"
    ;;
  stop)
    pkill -f "uvicorn main:app" 2>/dev/null
    pkill -f "node_modules/vite/bin/vite.js" 2>/dev/null
    echo "stopped"
    ;;
  *)
    start_backend
    start_frontend
    sleep 5
    curl -s -m 5 http://localhost:8000/health >/dev/null && echo "backend: OK http://localhost:8000" || echo "backend: not ready (see /tmp/nm-backend.log)"
    curl -s -m 5 -o /dev/null -w "frontend: %{http_code} http://localhost:5173\n" http://localhost:5173/
    ;;
esac