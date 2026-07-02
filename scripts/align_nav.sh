#!/usr/bin/env bash
# Two-pass nav alignment: verify → rebuild if needed → patch → publish → verify
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"
export PYTHONUNBUFFERED=1

NAV="$ROOT/bundle/manifest/nav.json"
DEPTH="${1:-2}"
PRODUCTS="${PRODUCTS:-enterprise,es8,soar,itsi}"

verify() {
  local pass="$1"
  local depth="$2"
  echo "=== Pass $pass verify (depth=$depth) ==="
  python3 scraper/verify_nav.py --nav "$NAV" --products "$PRODUCTS" --depth "$depth"
}

publish() {
  bash "$ROOT/scripts/publish_nav.sh"
  if [[ -d "${SPLUNK_HOME:-/opt/splunk}/etc/apps/splunk_offline_docs" ]]; then
    rsync -a "$NAV" "${SPLUNK_HOME:-/opt/splunk}/etc/apps/splunk_offline_docs/appserver/static/docs/manifest/nav.json"
    echo "Synced nav.json to Splunk app"
  fi
}

if ! verify 1 "$DEPTH"; then
  echo "Pass 1: republishing from cache + patch..."
  python3 scraper/rebuild_nav.py --output "$ROOT/bundle" --from-cache --products "$PRODUCTS"
  publish
  if ! verify 1 "$DEPTH"; then
    echo "Pass 1: rebuilding nav from help.splunk.com (slow)..."
    python3 scraper/rebuild_nav.py --output "$ROOT/bundle" --refresh --products "$PRODUCTS"
    publish
    verify 1 "$DEPTH"
  fi
fi

DEEPER=$((DEPTH + 1))
if ! verify 2 "$DEEPER"; then
  echo "Pass 2: refreshing nav from help.splunk.com..."
  python3 scraper/rebuild_nav.py --output "$ROOT/bundle" --refresh --products "$PRODUCTS"
  publish
  verify 2 "$DEEPER"
fi

echo "=== Nav alignment complete ==="
