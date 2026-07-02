#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
bash "$ROOT/scripts/prepare_app.sh"
OUT="${OUTPUT_DIR:-$ROOT/artifacts}"
mkdir -p "$OUT"
tar -czf "$OUT/splunk_offline_docs.tgz" -C "$ROOT" splunk_offline_docs
ls -lh "$OUT/splunk_offline_docs.tgz"
