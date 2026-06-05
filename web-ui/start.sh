#!/bin/bash
# Startup wrapper: starts Hermes Agent gateway + Web UI
set -e

echo "╔═══════════════════════════════════════════════╗"
echo "║     🏰 Hanna — Hermes Agent + Web UI         ║"
echo "╚═══════════════════════════════════════════════╝"

# ── Start Hermes Gateway (background) ──
echo "[start] Starting Hermes Agent gateway..."
/opt/hermes/venv/bin/python -m hermes_cli.main gateway &
HERMES_PID=$!
echo "[start] Hermes PID: $HERMES_PID"

# Wait for Hermes API to be ready
echo "[start] Waiting for Hermes API (port 8642)..."
for i in $(seq 1 30); do
  if curl -sf http://127.0.0.1:8642/health > /dev/null 2>&1; then
    echo "[start] Hermes API is ready!"
    break
  fi
  sleep 2
done

# ── Start Web UI (foreground) ──
echo "[start] Starting Web UI on port ${WEB_PORT:-8080}..."
exec /opt/hermes/venv/bin/python /opt/hermes-web/hermes-web.py
