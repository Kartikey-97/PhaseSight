#!/usr/bin/env bash
set -euo pipefail

# PhaseSight Unified Development Launcher
# Starts FastAPI backend (port 8000) and Next.js frontend (port 3000)

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  echo ""
  echo "Shutting down PhaseSight development servers..."
  if [ -n "$FRONTEND_PID" ] && kill -0 "$FRONTEND_PID" 2>/dev/null; then
    kill "$FRONTEND_PID" 2>/dev/null || true
  fi
  if [ -n "$BACKEND_PID" ] && kill -0 "$BACKEND_PID" 2>/dev/null; then
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
  wait 2>/dev/null || true
  echo "Shutdown complete."
}

trap cleanup EXIT INT TERM

# 1. Start FastAPI Backend
echo "[1/3] Starting FastAPI backend on http://127.0.0.1:8000..."
export MPLCONFIGDIR=/tmp
.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 &
BACKEND_PID=$!

# 2. Wait for backend health endpoint
echo "[2/3] Waiting for backend health check..."
MAX_RETRIES=30
RETRY_COUNT=0
until curl -sf http://127.0.0.1:8000/api/v1/health >/dev/null 2>&1; do
  sleep 0.5
  RETRY_COUNT=$((RETRY_COUNT + 1))
  if [ "$RETRY_COUNT" -ge "$MAX_RETRIES" ]; then
    echo "ERROR: Backend failed to become healthy within 15 seconds."
    exit 1
  fi
done
echo "Backend is healthy."

# 3. Start Next.js Frontend
echo "[3/3] Starting Next.js frontend on http://0.0.0.0:3000..."
cd frontend
npm run dev -- --hostname 0.0.0.0 --port 3000 &
FRONTEND_PID=$!

wait "$FRONTEND_PID"
