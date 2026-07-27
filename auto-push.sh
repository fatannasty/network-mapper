#!/bin/bash

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_DIR" || exit 1

echo "Auto-push watcher started in: $REPO_DIR"
echo "Watching for changes... (Ctrl+C to stop)"
echo ""

LAST_COMMIT=""

while true; do
  CHANGED=$(git status --porcelain 2>/dev/null)

  if [ -n "$CHANGED" ]; then
    TIMESTAMP=$(date "+%Y-%m-%d %H:%M:%S")
    git add -A
    git commit -m "Auto-save: $TIMESTAMP" --quiet

    if git push --quiet 2>/dev/null; then
      echo "[$TIMESTAMP] Pushed changes"
    else
      echo "[$TIMESTAMP] Push failed (will retry)"
    fi
  fi

  sleep 2
done
