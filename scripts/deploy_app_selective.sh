#!/usr/bin/env bash
# Deploy app code to Splunk server without overwriting appserver/static/docs.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TGZ="${1:-$ROOT/artifacts/splunk_offline_docs.tgz}"
APP="${SPLUNK_APP_PATH:-/opt/splunk/etc/apps/splunk_offline_docs}"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
tar -xzf "$TGZ" -C "$TMP"
SRC="$TMP/splunk_offline_docs"

for dir in bin scraper default; do
  rm -rf "$APP/$dir"
  cp -a "$SRC/$dir" "$APP/$dir"
done
rm -rf "$APP/lib"

mkdir -p "$APP/appserver/static"
rsync -a --delete --exclude 'docs/' "$SRC/appserver/static/" "$APP/appserver/static/"

chown -R splunk:splunk "$APP"
echo "Deployed to $APP (docs bundle preserved)"
