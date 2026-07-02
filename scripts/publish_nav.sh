#!/usr/bin/env bash
# Rebuild manifest/nav.json from cached portal-order trees and sync into the app
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"

python3 scraper/rebuild_nav.py --output "$ROOT/bundle" --from-cache

mkdir -p splunk_offline_docs/appserver/static/docs/manifest
rsync -a bundle/manifest/nav.json splunk_offline_docs/appserver/static/docs/manifest/

echo "Published nav.json to splunk_offline_docs/appserver/static/docs/manifest/"
