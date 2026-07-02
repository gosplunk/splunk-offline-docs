#!/usr/bin/env bash
# Repackage and install splunk_offline_docs into SPLUNK_HOME (bump forces static cache refresh)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SPLUNK_HOME="${SPLUNK_HOME:-/opt/splunk}"
APP_DIR="$SPLUNK_HOME/etc/apps/splunk_offline_docs"

cd "$ROOT"
bash scripts/package.sh
tar -xzf artifacts/splunk_offline_docs.tgz -C "$SPLUNK_HOME/etc/apps/"
echo "Installed to $APP_DIR (version $(grep ^version= "$APP_DIR/default/app.conf" | cut -d= -f2 | tr -d ' '))"
echo "Restart Splunk or reload the app, then hard-refresh the browser (Ctrl+Shift+R)."
