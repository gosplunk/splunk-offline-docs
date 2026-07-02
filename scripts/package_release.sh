#!/usr/bin/env bash
# Build customer-facing release tarball including pre-scraped documentation.
# Requires a machine that already has appserver/static/docs populated (build host or Splunk server).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="$ROOT/splunk_offline_docs"
DOCS="$APP/appserver/static/docs"
OUT="${OUTPUT_DIR:-$ROOT/artifacts}"
NAME="splunk_offline_docs_full.tgz"

bash "$ROOT/scripts/prepare_app.sh"

if [[ ! -f "$DOCS/manifest/nav.json" ]]; then
  echo "ERROR: Documentation bundle missing at $DOCS" >&2
  echo "Run scripts/build_bundle.sh on a connected host first, or copy docs into appserver/static/docs/." >&2
  exit 1
fi

mkdir -p "$OUT"
TOPIC_COUNT=$(find "$DOCS/topics" -name '*.html' 2>/dev/null | wc -l | tr -d ' ')
echo "Packaging app with $TOPIC_COUNT topic files..."
tar -czf "$OUT/$NAME" -C "$ROOT" splunk_offline_docs
ls -lh "$OUT/$NAME"
echo "Release artifact: $OUT/$NAME"
