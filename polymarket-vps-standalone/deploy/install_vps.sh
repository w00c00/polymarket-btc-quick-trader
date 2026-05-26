#!/usr/bin/env bash
set -euo pipefail

APP_SRC="$(cd "$(dirname "$0")/.." && pwd)"
INSTALL_DIR="${POLY_VPS_INSTALL_DIR:-/opt/polymarket-vps}"
DATA_DIR="${POLY_VPS_DATA_DIR:-/var/lib/polymarket-vps}"
SERVICE_USER="${POLY_VPS_USER:-polymm}"
SERVICE_NAME="${POLY_VPS_SERVICE:-polymarket-vps}"
HOST="${POLY_VPS_HOST:-127.0.0.1}"
PORT="${POLY_VPS_PORT:-8787}"

if [ "$(id -u)" -ne 0 ]; then
  exec sudo -E bash "$0" "$@"
fi

echo "Installing Polymarket VPS backend"
echo "  source:  $APP_SRC"
echo "  app:     $INSTALL_DIR"
echo "  data:    $DATA_DIR"
echo "  service: $SERVICE_NAME"

if command -v apt-get >/dev/null 2>&1; then
  apt-get update
  apt-get install -y python3 python3-venv python3-pip rsync curl
fi

if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  useradd --system --home "$DATA_DIR" --shell /usr/sbin/nologin "$SERVICE_USER"
fi

install -d -m 0755 "$INSTALL_DIR"
install -d -m 0750 -o "$SERVICE_USER" -g "$SERVICE_USER" "$DATA_DIR"

rsync -a --delete \
  --exclude ".venv" \
  --exclude "__pycache__" \
  --exclude "*.pyc" \
  --exclude "backend/data/*" \
  "$APP_SRC/" "$INSTALL_DIR/"

python3 -m venv "$INSTALL_DIR/.venv"
"$INSTALL_DIR/.venv/bin/pip" install --upgrade pip
"$INSTALL_DIR/.venv/bin/pip" install -r "$INSTALL_DIR/backend/requirements.txt"

chown -R root:root "$INSTALL_DIR"
chown -R "$SERVICE_USER:$SERVICE_USER" "$DATA_DIR"

cat > "/etc/systemd/system/$SERVICE_NAME.service" <<SERVICE
[Unit]
Description=Polymarket VPS Backend
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR/backend
Environment=POLY_VPS_HOST=$HOST
Environment=POLY_VPS_PORT=$PORT
Environment=POLY_VPS_USERS_PATH=$DATA_DIR/users.json
Environment=POLY_VPS_USERS_DIR=$DATA_DIR/users
ExecStart=$INSTALL_DIR/.venv/bin/uvicorn app:app --host \${POLY_VPS_HOST} --port \${POLY_VPS_PORT}
Restart=always
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ReadWritePaths=$DATA_DIR

[Install]
WantedBy=multi-user.target
SERVICE

systemctl daemon-reload
systemctl enable --now "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"

echo
echo "Installed. Service status:"
systemctl --no-pager --full status "$SERVICE_NAME" || true
echo
echo "Health check:"
curl -fsS "http://$HOST:$PORT/api/health" || true
echo
