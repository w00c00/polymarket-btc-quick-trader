#!/usr/bin/env bash
set -euo pipefail

if [ "${1:-}" = "" ]; then
  echo "Usage: $0 user@host [ssh-port]" >&2
  exit 2
fi

TARGET="$1"
SSH_PORT="${2:-22}"
ssh -N -L 8787:127.0.0.1:8787 -p "$SSH_PORT" "$TARGET"
