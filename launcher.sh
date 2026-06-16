#!/bin/bash
# Started by systemd (depot.service). Pulls the latest code, then runs the app.
set -u

DEPOT_DIR="$(dirname "$(readlink -f "$0")")"
cd "$DEPOT_DIR" || exit 1

# Avoid git "dubious ownership" errors when systemd runs as root.
git config --global --add safe.directory "$DEPOT_DIR"

echo "--- LAUNCHER: checking for git updates ---"
git pull origin main || echo "LAUNCHER: git pull failed; starting with local code"

echo "--- LAUNCHER: starting app ---"
# exec so systemd tracks the Python process directly (clean stop/restart).
exec .venv/bin/python3 -m depot
