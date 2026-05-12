#!/usr/bin/env bash
# Arranca la app en desarrollo.
set -e
cd "$(dirname "$0")"
[ -f .env ] || cp .env.example .env
PORT="${APP_PORT:-8600}"
exec python3 -m uvicorn app.main:app --reload --host 127.0.0.1 --port "$PORT"
