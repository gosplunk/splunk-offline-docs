#!/usr/bin/env python3
"""Crawl help.splunk.com and emit offline documentation bundle."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Set

import yaml
from bs4 import BeautifulSoup

from scraper.content import (
    fetch_topic,
    normalize_enterprise_path,
    resolve_enterprise_version,
)
from scraper.http_client import HelpClient
from scraper.links import build_link_index, rewrite_topic_html
from scraper.nav import NavNode, build_product_nav, iter_topic_paths

ROOT = Path(__file__).resolve().parents[1]


def load_products(cfg_path: Path) -> dict:
    with open(cfg_path) as f:
        return yaml.safe_load(f)["products"]


def should_exclude(path: str, excludes: List[str]) -> bool:
    p = path.lower()
    return any(x.lower() in p for x in excludes)


def plain_text(html: str) -> str:
    return BeautifulSoup(html, "lxml").get_text(" ", strip=True)


def save_checkpoint(path: Path, checkpoint: dict) -> None:
    path.write_text(json.dumps(checkpoint, indent=2), encoding="utf-8")


def crawl_product(
    client: HelpClient,
    pid: str,
    cfg: dict,
    out: Path,
    checkpoint: dict,
) -> dict:
    root_path = cfg["root_path"]
    title = cfg["title"]
    excludes = cfg.get("exclude_path_contains", [])
    version_cache: dict = checkpoint.setdefault("version_cache", {})

    cache_file = out / "nav-cache" / f"{pid}-tree.json"

    def log(msg: str) -> None:
        print(f"[{pid}] {msg}", flush=True)

    log(f"building nav for {root_path}...")
    nav_root = build_product_nav(
        client, root_path, title, cache_file=cache_file, log=log
    )

    paths: Set[str] = set()
    enterprise_version = None
    if cfg.get("version_filter") == "10.x_latest" and pid == "enterprise":
        sample = next(
            (p for p in iter_topic_paths(nav_root) if p != root_path),
            root_path,
        )
        enterprise_version = resolve_enterprise_version(
            client, sample, version_cache
        )
        log(f"enterprise version: {enterprise_version or 'unknown'}")

    for p in iter_topic_paths(nav_root):
        if should_exclude(p, excludes):
            continue
        if pid == "enterprise":
            p = normalize_enterprise_path(p, enterprise_version)
            if not p:
                continue
        paths.add(p)

    log(f"fetching {len(paths)} topics...")
    topics_dir = out / "topics"
    topics_dir.mkdir(parents=True, exist_ok=True)
    topics_meta: Dict[str, dict] = checkpoint.setdefault("topics", {})
    done = set(checkpoint.get("fetched_paths", []))

    for i, path in enumerate(sorted(paths)):
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
            checkpoint["fetched_paths"] = list(done)
            if (i + 1) % 25 == 0:
                log(f"fetched {i + 1}/{len(paths)} topics")
                save_checkpoint(out / "checkpoint.json", checkpoint)
        except Exception as e:
            print(f"[{pid}] WARN failed {path}: {e}", file=sys.stderr, flush=True)

    log(f"finished — {len([p for p in paths if p in done])} topics")
    return nav_root.to_dict() | {"id": pid, "product": pid, "title": title}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="bundle")
    ap.add_argument("--products", default="enterprise,es8,soar,itsi")
    ap.add_argument("--rate-limit", type=float, default=0.75)
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()

    out = Path(args.output)
    manifest = out / "manifest"
    manifest.mkdir(parents=True, exist_ok=True)

    checkpoint_path = out / "checkpoint.json"
    checkpoint: dict = {}
    if args.resume and checkpoint_path.exists():
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))

    products_cfg = load_products(ROOT / "scraper" / "products.yaml")
    selected = [p.strip() for p in args.products.split(",") if p.strip()]

    client = HelpClient(rate_limit=args.rate_limit)
    nav_trees = []
    for pid in selected:
        if pid not in products_cfg:
            print(f"Unknown product {pid}", file=sys.stderr)
            continue
        tree = crawl_product(client, pid, products_cfg[pid], out, checkpoint)
        nav_trees.append(tree)
        save_checkpoint(checkpoint_path, checkpoint)

    topics = checkpoint.get("topics", {})
    print(f"Rewriting links for {len(topics)} topics...", flush=True)
    link_index = build_link_index(topics)

    topics_dir = out / "topics"
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

    (manifest / "nav.json").write_text(
        json.dumps(nav_trees, indent=2), encoding="utf-8"
    )
    (manifest / "link-index.json").write_text(
        json.dumps(link_index, indent=2), encoding="utf-8"
    )
    (manifest / "search-index.json").write_text(
        json.dumps(search_index, indent=2), encoding="utf-8"
    )
    (manifest / "meta.json").write_text(
        json.dumps(
            {
                "products": selected,
                "topic_count": len(topics),
                "source": "https://help.splunk.com",
                "built_at": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    report = {
        "topics": len(topics),
        "products": selected,
        "built_at": datetime.now(timezone.utc).isoformat(),
    }
    (out / "scrape-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("Done:", report, flush=True)


if __name__ == "__main__":
    main()
