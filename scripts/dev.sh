#!/bin/sh
set -eu

BACKEND_PORT="${BACKEND_PORT:-8001}"
FRONTEND_PORT="${PORT:-3000}"
FRONTEND_PID=""
BACKEND_PID=""

bunx next dev --hostname 0.0.0.0 --port "$FRONTEND_PORT" &
FRONTEND_PID=$!

cleanup() {
  if [ -n "$FRONTEND_PID" ]; then kill "$FRONTEND_PID" 2>/dev/null || true; fi
  if [ -n "$BACKEND_PID" ]; then kill "$BACKEND_PID" 2>/dev/null || true; fi
}
trap cleanup INT TERM EXIT

sleep 2
sh ./scripts/python.sh -m uvicorn python_backend.main:app --host 0.0.0.0 --port "$BACKEND_PORT" &
BACKEND_PID=$!

wait "$FRONTEND_PID"
