#!/usr/bin/env python3
"""Rewrite topic HTML links in an installed Splunk app (offline bundle)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scraper.links import (  # noqa: E402
    _build_tail_candidates,
    build_link_index_from_search,
    rewrite_topic_html,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--app-dir",
        default="/opt/splunk/etc/apps/splunk_offline_docs/appserver/static/docs",
    )
    args = ap.parse_args()

    docs = Path(args.app_dir)
    topics = docs / "topics"
    manifest = docs / "manifest"
    search_path = manifest / "search-index.json"
    link_index_path = manifest / "link-index.json"
    if not search_path.is_file():
        print(f"Missing {search_path}", file=sys.stderr)
        return 1

    search = json.loads(search_path.read_text(encoding="utf-8"))
    old_rids = {}
    if link_index_path.is_file():
        old_rids = json.loads(link_index_path.read_text(encoding="utf-8")).get(
            "resourceIds", {},
        )

    link_index = build_link_index_from_search(search, old_rids)
    tail_candidates = _build_tail_candidates(link_index["paths"])
    link_index_path.write_text(
        json.dumps(link_index, indent=2),
        encoding="utf-8",
    )
    path_by_id = {entry["id"]: entry.get("path", "") for entry in search}
    print(
        f"Rebuilt link-index: {len(link_index['paths'])} paths, "
        f"{len(link_index['suffixes'])} suffixes, "
        f"{len(link_index['resourceIds'])} resource ids",
    )

    changed = 0
    for fp in sorted(topics.glob("*.html")):
        topic_id = fp.stem
        current_path = path_by_id.get(topic_id, "")
        html = fp.read_text(encoding="utf-8")
        new_html = rewrite_topic_html(
            html, link_index, current_path, tail_candidates,
        )
        if new_html != html:
            fp.write_text(new_html, encoding="utf-8")
            changed += 1

    print(f"Rewrote links in {changed} topic files under {topics}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
