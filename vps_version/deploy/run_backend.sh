#!/usr/bin/env bash
set -euo pipefail
APP_HOME="$(cd "$(dirname "$0")/.." && pwd)"
cd "$APP_HOME"
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
pip install -r backend/requirements.txt
cd backend
mkdir -p data
exec uvicorn app:app --host "${POLY_VPS_HOST:-127.0.0.1}" --port "${POLY_VPS_PORT:-8787}"
