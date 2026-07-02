#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"
export PYTHONUNBUFFERED=1
python3 scraper/repair_bundle.py --output "$ROOT/bundle" --rate-limit 0.35
mkdir -p splunk_offline_docs/appserver/static/docs
rsync -a bundle/manifest/ splunk_offline_docs/appserver/static/docs/manifest/
rsync -a bundle/topics/ splunk_offline_docs/appserver/static/docs/topics/
bash scripts/package.sh
