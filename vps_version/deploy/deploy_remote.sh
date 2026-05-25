#!/usr/bin/env bash
set -euo pipefail

if [ "${1:-}" = "" ]; then
  echo "Usage: $0 user@host [ssh-port]" >&2
  echo "Example: $0 root@1.2.3.4" >&2
  echo "Example: $0 ubuntu@1.2.3.4 22" >&2
  exit 2
fi

TARGET="$1"
SSH_PORT="${2:-22}"
APP_HOME="$(cd "$(dirname "$0")/.." && pwd)"
ARCHIVE="/tmp/polymarket-vps-$(date +%s).tgz"
REMOTE_ARCHIVE="/tmp/polymarket-vps.tgz"
REMOTE_DIR="/tmp/polymarket-vps-deploy"

tar \
  --exclude ".venv" \
  --exclude "__pycache__" \
  --exclude "*.pyc" \
  --exclude "backend/data/*" \
  -czf "$ARCHIVE" -C "$APP_HOME" .

scp -P "$SSH_PORT" "$ARCHIVE" "$TARGET:$REMOTE_ARCHIVE"
ssh -p "$SSH_PORT" "$TARGET" "rm -rf '$REMOTE_DIR' && mkdir -p '$REMOTE_DIR' && tar -xzf '$REMOTE_ARCHIVE' -C '$REMOTE_DIR' && bash '$REMOTE_DIR/deploy/install_vps.sh'"
rm -f "$ARCHIVE"
