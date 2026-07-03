#!/usr/bin/env python3
"""Fetch topics referenced in nav.json that are not yet in the bundle."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from scraper.content import fetch_topic, normalize_enterprise_path, resolve_enterprise_version
from scraper.crawl import load_products, plain_text, save_checkpoint, should_exclude
from scraper.http_client import HelpClient
from scraper.links import build_link_index, rewrite_topic_html
from scraper.nav import NavNode, iter_topic_paths
from scraper.versions import (
    latest_version_allowlist,
    path_matches_version_allowlist,
    version_filter_keep,
)

ROOT = Path(__file__).resolve().parents[1]


def tree_from_dict(d: dict) -> NavNode:
    return NavNode(
        path=d["path"],
        title=d.get("title", ""),
        children=[tree_from_dict(c) for c in d.get("children", [])],
    )


def rebuild_manifest(out: Path, checkpoint: dict, nav_trees: list) -> None:
    manifest = out / "manifest"
    topics = checkpoint.get("topics", {})
    topics_dir = out / "topics"
    link_index = build_link_index(topics)

    for tid, meta in topics.items():
        fp = topics_dir / f"{tid}.html"
        if not fp.exists():
            continue
        raw = fp.read_text(encoding="utf-8")
        fp.write_text(rewrite_topic_html(raw, link_index, meta["path"]), encoding="utf-8")

    search_index = [
        {
            "id": tid,
            "title": m["title"],
            "path": m["path"],
            "product": m["product"],
            "text": plain_text(fp.read_text(encoding="utf-8"))[:8000],
        }
        for tid, m in topics.items()
        if (fp := topics_dir / f"{tid}.html").exists()
    ]

    (manifest / "nav.json").write_text(json.dumps(nav_trees, indent=2), encoding="utf-8")
    (manifest / "link-index.json").write_text(
        json.dumps(link_index, indent=2), encoding="utf-8"
    )
    (manifest / "search-index.json").write_text(
        json.dumps(search_index, indent=2), encoding="utf-8"
    )
    meta_path = manifest / "meta.json"
    meta = {}
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["topic_count"] = len(topics)
    meta["updated_at"] = datetime.now(timezone.utc).isoformat()
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="bundle")
    ap.add_argument("--rate-limit", type=float, default=0.35)
    args = ap.parse_args()

    out = Path(args.output)
    manifest = out / "manifest"
    nav_trees = json.loads((manifest / "nav.json").read_text(encoding="utf-8"))
    checkpoint_path = out / "checkpoint.json"
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    products_cfg = load_products(ROOT / "scraper" / "products.yaml")
    topics_meta = checkpoint.setdefault("topics", {})
    done = set(checkpoint.get("fetched_paths", []))
    version_cache = checkpoint.setdefault("version_cache", {})

    client = HelpClient(rate_limit=args.rate_limit)
    topics_dir = out / "topics"
    topics_dir.mkdir(parents=True, exist_ok=True)
    fetched = 0

    for tree_dict in nav_trees:
        pid = tree_dict.get("id") or tree_dict.get("product")
        if pid not in products_cfg:
            continue
        cfg = products_cfg[pid]
        root = tree_from_dict(tree_dict)
        all_paths = list(iter_topic_paths(root))
        version_allowlist = None
        keep_n = version_filter_keep(cfg)
        if keep_n:
            version_allowlist = latest_version_allowlist(all_paths, keep_n)

        enterprise_version = None
        if pid == "enterprise":
            sample = next(
                (p for p in iter_topic_paths(root) if p != cfg["root_path"]),
                cfg["root_path"],
            )
            enterprise_version = resolve_enterprise_version(
                client, sample, version_cache
            )

        for path in all_paths:
            if path == cfg["root_path"]:
                continue
            if should_exclude(path, cfg.get("exclude_path_contains", [])):
                continue
            if pid == "enterprise":
                path = normalize_enterprise_path(path, enterprise_version) or path
            if version_allowlist is not None and not path_matches_version_allowlist(
                path, version_allowlist
            ):
                continue
            if path in done:
                continue
            try:
                topic = fetch_topic(client, path)
                topics_meta[topic.topic_id] = {
                    "path": path,
                    "title": topic.title,
                    "product": pid,
                    "resource_ids": topic.resource_ids,
                    "breadcrumbs": topic.breadcrumbs,
                    "mini_toc": topic.mini_toc,
                }
                (topics_dir / f"{topic.topic_id}.html").write_text(
                    topic.html, encoding="utf-8"
                )
                done.add(path)
                fetched += 1
                if fetched % 25 == 0:
                    print(f"fetched {fetched} new topics...", flush=True)
                    checkpoint["fetched_paths"] = list(done)
                    save_checkpoint(checkpoint_path, checkpoint)
            except Exception as exc:
                print(f"WARN {path}: {exc}", file=sys.stderr, flush=True)

    checkpoint["fetched_paths"] = list(done)
    save_checkpoint(checkpoint_path, checkpoint)
    rebuild_manifest(out, checkpoint, nav_trees)
    print(f"Done — fetched {fetched} new topics ({len(topics_meta)} total)", flush=True)


if __name__ == "__main__":
    main()
