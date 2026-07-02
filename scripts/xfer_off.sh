#!/usr/bin/env bash
# Download the packaged app from the ephemeral build host
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=/dev/null
source "$ROOT/deploy/instance.env"

PORT="${BUILD_SSH_PORT:-22}"
DEST="${1:-.}"
REMOTE_TGZ="${OUTPUT_DIR:-/home/splunk/artifacts}/splunk_offline_docs.tgz"

if [[ -n "${BUILD_SSH_KEY_PATH:-}" ]]; then
  scp -P "$PORT" -i "$BUILD_SSH_KEY_PATH" \
    "${BUILD_SSH_USER}@${BUILD_SSH_HOST}:${REMOTE_TGZ}" "$DEST/"
elif [[ -n "${BUILD_SSH_PASSWORD:-}" ]]; then
  SSHPASS="$BUILD_SSH_PASSWORD" sshpass -e scp -P "$PORT" \
    "${BUILD_SSH_USER}@${BUILD_SSH_HOST}:${REMOTE_TGZ}" "$DEST/"
else
  scp -P "$PORT" "${BUILD_SSH_USER}@${BUILD_SSH_HOST}:${REMOTE_TGZ}" "$DEST/"
fi

echo "Downloaded to $DEST/$(basename "$REMOTE_TGZ")"
