#!/usr/bin/env bash
# Rebuild portal-order nav, fetch missing topics, sync into Splunk app
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"
export PYTHONUNBUFFERED=1

python3 scraper/rebuild_nav.py --output "$ROOT/bundle" --refresh
python3 scraper/patch_nav_manifest.py "$ROOT/bundle/manifest/nav.json"
python3 scraper/fetch_missing.py --output "$ROOT/bundle"
python3 scraper/repair_bundle.py --output "$ROOT/bundle"

mkdir -p splunk_offline_docs/appserver/static/docs
rsync -a bundle/manifest/ splunk_offline_docs/appserver/static/docs/manifest/
rsync -a bundle/topics/ splunk_offline_docs/appserver/static/docs/topics/
bash scripts/package.sh
