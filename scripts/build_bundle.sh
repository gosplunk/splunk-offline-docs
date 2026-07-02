#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

pip3 install --user -q -r scraper/requirements.txt
export PYTHONPATH="$ROOT"
export PYTHONUNBUFFERED=1

python3 scraper/crawl.py \
  --output "$ROOT/bundle" \
  --products es8,soar,itsi,enterprise \
  --rate-limit 0.35 \
  --resume

mkdir -p splunk_offline_docs/appserver/static/docs
rsync -a bundle/manifest/ splunk_offline_docs/appserver/static/docs/manifest/
rsync -a bundle/topics/ splunk_offline_docs/appserver/static/docs/topics/

bash scripts/package.sh
echo "Build complete: ${OUTPUT_DIR:-$ROOT/artifacts}/splunk_offline_docs.tgz"
