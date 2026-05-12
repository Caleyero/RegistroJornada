#!/usr/bin/env bash
# Arranca la app en desarrollo. Si hay .venv, lo activa; si no, usa python3 del sistema.
set -e
cd "$(dirname "$0")"
[ -f .env ] || cp .env.example .env
PORT="${APP_PORT:-8600}"
if [ -f .venv/bin/activate ]; then
    # shellcheck disable=SC1091
    source .venv/bin/activate
    exec python -m uvicorn app.main:app --reload --host 127.0.0.1 --port "$PORT"
fi
exec python3 -m uvicorn app.main:app --reload --host 127.0.0.1 --port "$PORT"
