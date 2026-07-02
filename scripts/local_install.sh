#!/usr/bin/env bash
# Install splunk_offline_docs into SPLUNK_HOME on the build host (smoke test)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SPLUNK_HOME="${SPLUNK_HOME:-/opt/splunk}"
APP_DIR="$SPLUNK_HOME/etc/apps/splunk_offline_docs"

sudo rm -rf "$APP_DIR"
sudo cp -a "$ROOT/splunk_offline_docs" "$APP_DIR"
sudo chown -R splunk:splunk "$APP_DIR"

# Allow iframe/html panels in Simple XML dashboards (system default is false on Splunk 9.x).
# Merge into the first [settings] stanza so splunkweb picks them up reliably.
LOCAL_WEB="$SPLUNK_HOME/etc/system/local/web.conf"
if ! sudo grep -q '^dashboard_html_allow_embeddable_content' "$LOCAL_WEB" 2>/dev/null; then
  sudo python3 - "$LOCAL_WEB" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text() if path.exists() else ""
lines = [
    "dashboard_html_allow_embeddable_content = true",
    "dashboard_html_allow_iframes = true",
    "dashboard_html_allow_inline_styles = true",
]
if "[settings]" in text:
    parts = text.split("[settings]", 1)
    head, rest = parts[0], parts[1]
    block, tail = (rest.split("\n[", 1) + [""])[:2]
    block_lines = block.splitlines()
    insert_at = 0
    for i, line in enumerate(block_lines):
        if line.strip() and not line.strip().startswith("#"):
            insert_at = i
            break
    for line in reversed(lines):
        if line.split("=")[0].strip() not in block:
            block_lines.insert(insert_at, line)
    text = head + "[settings]" + "\n".join(block_lines) + ("\n[" + tail if tail else "")
else:
    text = text.rstrip() + "\n\n[settings]\n" + "\n".join(lines) + "\n"
path.write_text(text)
PY
  sudo chown splunk:splunk "$LOCAL_WEB"
fi

echo "Installed to $APP_DIR — restart Splunk or reload apps"
