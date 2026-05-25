#!/usr/bin/env bash
set -euo pipefail
APP_HOME="$(cd "$(dirname "$0")/.." && pwd)"
cd "$APP_HOME"
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r backend/requirements.txt
cat > deploy/polymarket-vps.service.generated <<SERVICE
[Unit]
Description=Polymarket VPS Backend
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$APP_HOME/backend
Environment=POLY_VPS_HOST=127.0.0.1
Environment=POLY_VPS_PORT=8787
Environment=POLY_VPS_VAULT_PATH=$APP_HOME/backend/data/encrypted_vault.json
ExecStart=$APP_HOME/.venv/bin/uvicorn app:app --host \${POLY_VPS_HOST} --port \${POLY_VPS_PORT}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICE
echo "Generated deploy/polymarket-vps.service.generated"
