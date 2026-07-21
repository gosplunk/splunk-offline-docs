#!/usr/bin/env python3
"""Rebuild manifest/nav.json from help.splunk.com portal TOC order."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from scraper.crawl import load_products, save_checkpoint
from scraper.http_client import HelpClient
from scraper.nav import build_product_nav, load_cached_tree
from scraper.patch_nav_manifest import patch_nav_file
from scraper.versions import apply_latest_version_filter

ROOT = Path(__file__).resolve().parents[1]


def assemble_from_cache(out: Path, products_cfg: dict, selected: list[str]) -> list[dict]:
    """Build nav.json from cached *-tree.json files (portal order, no network)."""
    nav_trees = []
    for pid in selected:
        if pid not in products_cfg:
            continue
        cfg = products_cfg[pid]
        cache_file = out / "nav-cache" / f"{pid}-tree.json"
        root = load_cached_tree(cache_file)
        if not root:
            raise SystemExit(f"Missing nav cache: {cache_file}")
        tree_dict = root.to_dict() | {"id": pid, "product": pid, "title": cfg["title"]}
        tree_dict, allowed = apply_latest_version_filter(tree_dict, cfg)
        if allowed:
            ordered = sorted(
                allowed, key=lambda v: tuple(int(p) for p in v.split(".")), reverse=True
            )
            print(f"[{pid}] latest {len(allowed)} version(s): {', '.join(ordered)}", flush=True)
        nav_trees.append(tree_dict)
    return nav_trees


def load_existing_nav(manifest: Path) -> dict[str, dict]:
    nav_path = manifest / "nav.json"
    if not nav_path.is_file():
        return {}
    try:
        trees = json.loads(nav_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(trees, list):
        return {}
    out: dict[str, dict] = {}
    for tree in trees:
        if isinstance(tree, dict):
            pid = tree.get("id") or tree.get("product")
            if pid:
                out[str(pid)] = tree
    return out


def merge_nav_trees(products_cfg: dict, existing: dict[str, dict], updated: list[dict]) -> list[dict]:
    """Keep unselected products from existing nav when rebuilding a subset."""
    merged = dict(existing)
    for tree in updated:
        pid = tree.get("id") or tree.get("product")
        if pid:
            merged[str(pid)] = tree
    ordered: list[dict] = []
    for pid in products_cfg:
        if pid in merged:
            ordered.append(merged.pop(pid))
    ordered.extend(merged.values())
    return ordered


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="bundle")
    ap.add_argument("--products", default="enterprise,es8,soar,itsi")
    ap.add_argument("--rate-limit", type=float, default=0.35)
    ap.add_argument("--refresh", action="store_true", help="Ignore nav cache")
    ap.add_argument(
        "--from-cache",
        action="store_true",
        help="Assemble nav.json from nav-cache/*-tree.json without fetching",
    )
    args = ap.parse_args()

    out = Path(args.output)
    manifest = out / "manifest"
    manifest.mkdir(parents=True, exist_ok=True)
    products_cfg = load_products(ROOT / "scraper" / "products.yaml")
    selected = [p.strip() for p in args.products.split(",") if p.strip()]

    if args.from_cache:
        nav_trees = assemble_from_cache(out, products_cfg, selected)
    else:
        client = HelpClient(rate_limit=args.rate_limit)
        nav_trees = []
        for pid in selected:
            if pid not in products_cfg:
                print(f"Unknown product {pid}", file=sys.stderr)
                continue
            cfg = products_cfg[pid]
            cache_file = out / "nav-cache" / f"{pid}-tree.json"
            if args.refresh and cache_file.exists():
                cache_file.unlink()
            old_flat = out / "nav-cache" / f"{pid}.json"
            if args.refresh and old_flat.exists():
                old_flat.unlink()

            print(f"[{pid}] building ordered nav...", flush=True)
            root = build_product_nav(
                client,
                cfg["root_path"],
                cfg["title"],
                cache_file=cache_file,
                log=lambda m: print(f"[{pid}] {m}", flush=True),
            )
            tree_dict = root.to_dict() | {
                "id": pid,
                "product": pid,
                "title": cfg["title"],
            }
            tree_dict, allowed = apply_latest_version_filter(tree_dict, cfg)
            if allowed:
                ordered = sorted(allowed, key=lambda v: tuple(int(p) for p in v.split(".")), reverse=True)
                print(f"[{pid}] latest {len(allowed)} version(s): {', '.join(ordered)}", flush=True)
            nav_trees.append(tree_dict)

    if len(selected) < len(products_cfg):
        existing = load_existing_nav(manifest)
        if existing:
            nav_trees = merge_nav_trees(products_cfg, existing, nav_trees)
            print(
                f"Merged nav ({len(nav_trees)} products; rebuilt {', '.join(selected)})",
                flush=True,
            )

    (manifest / "nav.json").write_text(json.dumps(nav_trees, indent=2), encoding="utf-8")
    patch_nav_file(manifest / "nav.json", out / "topics")
    meta_path = manifest / "meta.json"
    meta = {}
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["nav_rebuilt_at"] = datetime.now(timezone.utc).isoformat()
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"Wrote nav.json ({len(nav_trees)} products)", flush=True)


if __name__ == "__main__":
    main()
