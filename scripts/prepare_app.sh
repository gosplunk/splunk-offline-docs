#!/usr/bin/env bash
# Bundle scraper + helper scripts into the Splunk app before packaging.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="$ROOT/splunk_offline_docs"

rsync -a --delete \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  "$ROOT/scraper/" "$APP/scraper/"

mkdir -p "$APP/scripts"
cp "$ROOT/scripts/rewrite_deployed_links.py" "$APP/scripts/rewrite_deployed_links.py"

chmod +x "$APP/bin/"*.py

echo "Prepared app with scraper and bin scripts"
