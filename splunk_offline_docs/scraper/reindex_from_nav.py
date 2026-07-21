#!/usr/bin/env python3
"""Rebuild checkpoint + search/link indexes from nav.json and on-disk topic HTML."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from scraper.content import path_to_topic_id
from scraper.crawl import plain_text, save_checkpoint
from scraper.fetch_missing import rebuild_manifest
from scraper.links import build_link_index, rewrite_topic_html

ROOT = Path(__file__).resolve().parents[1]


def collect_nav_paths(tree: dict) -> dict[str, str]:
    """Map topic path -> nav title for all nodes under a product tree."""
    paths: dict[str, str] = {}

    def walk(node: dict) -> None:
        path = (node.get("path") or "").strip()
        title = (node.get("title") or "").strip()
        if path:
            paths[path] = title
        for child in node.get("children") or []:
            walk(child)

    walk(tree)
    return paths


def title_from_html(html: str, fallback: str) -> str:
    if fallback and len(fallback) >= 3:
        return fallback
    import re

    m = re.search(r"<title[^>]*>([^<]+)</title>", html, re.I)
    if m:
        return m.group(1).strip()
    m = re.search(r"<h1[^>]*>([^<]+)</h1>", html, re.I)
    if m:
        return m.group(1).strip()
    return fallback or "Untitled"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="bundle")
    ap.add_argument("--merge", action="store_true", help="Keep existing checkpoint entries")
    args = ap.parse_args()

    out = Path(args.output)
    manifest = out / "manifest"
    nav_path = manifest / "nav.json"
    if not nav_path.is_file():
        raise SystemExit(f"Missing {nav_path}")

    nav_trees = json.loads(nav_path.read_text(encoding="utf-8"))
    topics_dir = out / "topics"
    checkpoint_path = out / "checkpoint.json"
    checkpoint: dict = {"topics": {}, "fetched_paths": []}
    if args.merge and checkpoint_path.is_file():
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    topics_meta = checkpoint.setdefault("topics", {})
    fetched_paths = set(checkpoint.get("fetched_paths") or [])

    added = 0
    for tree in nav_trees:
        pid = tree.get("id") or tree.get("product")
        if not pid:
            continue
        root_path = (tree.get("path") or "").strip()
        for path, nav_title in collect_nav_paths(tree).items():
            if root_path and path == root_path:
                continue
            tid = path_to_topic_id(path)
            fp = topics_dir / f"{tid}.html"
            if not fp.is_file():
                continue
            html = fp.read_text(encoding="utf-8")
            entry = topics_meta.get(tid, {})
            topics_meta[tid] = {
                "path": path,
                "title": title_from_html(html, nav_title or entry.get("title", "")),
                "product": pid,
                "resource_ids": entry.get("resource_ids", []),
                "breadcrumbs": entry.get("breadcrumbs", []),
                "mini_toc": entry.get("mini_toc", []),
            }
            fetched_paths.add(path)
            added += 1

    checkpoint["topics"] = topics_meta
    checkpoint["fetched_paths"] = sorted(fetched_paths)
    save_checkpoint(checkpoint_path, checkpoint)

    link_index = build_link_index(topics_meta)
    for tid, meta in topics_meta.items():
        fp = topics_dir / f"{tid}.html"
        if not fp.is_file():
            continue
        raw = fp.read_text(encoding="utf-8")
        fp.write_text(rewrite_topic_html(raw, link_index, meta["path"]), encoding="utf-8")

    rebuild_manifest(out, checkpoint, nav_trees)

    meta_path = manifest / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["reindexed_at"] = datetime.now(timezone.utc).isoformat()
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print(
        f"Reindexed {len(topics_meta)} topics ({added} from nav/html scan)",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
