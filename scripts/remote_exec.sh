#!/usr/bin/env bash
# Run a command on the ephemeral build host defined in deploy/instance.env
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=/dev/null
source "$ROOT/deploy/instance.env"

PORT="${BUILD_SSH_PORT:-22}"
HOST="${BUILD_SSH_HOST}"
USER="${BUILD_SSH_USER}"
REMOTE_CMD="${*:-echo connected}"

if [[ -n "${BUILD_SSH_KEY_PATH:-}" ]]; then
  ssh -p "$PORT" -i "$BUILD_SSH_KEY_PATH" -o StrictHostKeyChecking=accept-new \
    "${USER}@${HOST}" "$REMOTE_CMD"
elif [[ -n "${BUILD_SSH_PASSWORD:-}" ]]; then
  SSHPASS="$BUILD_SSH_PASSWORD" sshpass -e ssh -p "$PORT" \
    -o StrictHostKeyChecking=accept-new "${USER}@${HOST}" "$REMOTE_CMD"
else
  ssh -p "$PORT" -o StrictHostKeyChecking=accept-new "${USER}@${HOST}" "$REMOTE_CMD"
fi
