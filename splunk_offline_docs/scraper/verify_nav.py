#!/usr/bin/env python3
"""Compare manifest nav order against help.splunk.com TOC fragments."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml
from bs4 import BeautifulSoup

from scraper.http_client import HelpClient
from scraper.nav import NAV_PREFIX, _parse_toc_children

ROOT = Path(__file__).resolve().parents[1]


def load_products(cfg_path: Path) -> dict:
    with open(cfg_path) as f:
        return yaml.safe_load(f)["products"]


def find_node(nodes: list, path: str) -> Optional[dict]:
    for node in nodes:
        if node.get("path") == path:
            return node
        hit = find_node(node.get("children") or [], path)
        if hit:
            return hit
    return None


def local_child_paths(
    product_children: list, parent_path: str, root_path: str
) -> List[str]:
    if parent_path == root_path:
        return [c["path"] for c in product_children]
    node = find_node(product_children, parent_path)
    if not node:
        return []
    return [c["path"] for c in node.get("children") or []]


def help_child_paths(client: HelpClient, parent_path: str, root_path: str) -> List[str]:
    html = client.get(NAV_PREFIX + parent_path)
    items = _parse_toc_children(BeautifulSoup(html, "html.parser"), root_path)
    return [path for path, _title, _has_kids in items]


def compare_lists(
    product_id: str,
    parent_path: str,
    help_paths: List[str],
    local_paths: List[str],
) -> List[str]:
    issues: List[str] = []
    if help_paths == local_paths:
        return issues
    issues.append(
        f"[{product_id}] order mismatch at {parent_path or '/'}: "
        f"help={len(help_paths)} local={len(local_paths)}"
    )
    for i, (hp, lp) in enumerate(zip(help_paths, local_paths)):
        if hp != lp:
            issues.append(f"  first diff @{i + 1}: help={hp}")
            issues.append(f"                 local={lp}")
            break
    help_set, local_set = set(help_paths), set(local_paths)
    missing = sorted(help_set - local_set)[:5]
    extra = sorted(local_set - help_set)[:5]
    if missing:
        issues.append(f"  missing locally ({len(help_set - local_set)}): {missing}")
    if extra:
        issues.append(f"  extra locally ({len(local_set - help_set)}): {extra}")
    return issues


def verify_product(
    client: HelpClient,
    product_id: str,
    root_path: str,
    local_children: list,
    max_depth: int,
    fetched: Dict[str, List[str]],
) -> Tuple[int, List[str]]:
    issues: List[str] = []
    branches = 0

    def walk(parent_path: str, depth: int) -> None:
        nonlocal branches
        if depth > max_depth:
            return
        if parent_path in fetched:
            help_paths = fetched[parent_path]
        else:
            try:
                help_paths = help_child_paths(client, parent_path, root_path)
            except Exception as exc:
                issues.append(f"[{product_id}] fetch failed {parent_path}: {exc}")
                return
            fetched[parent_path] = help_paths
        local_paths = local_child_paths(local_children, parent_path, root_path)
        issues.extend(compare_lists(product_id, parent_path, help_paths, local_paths))
        branches += 1
        for child_path in help_paths:
            walk(child_path, depth + 1)

    walk(root_path, 0)
    return branches, issues


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--nav", type=Path, default=ROOT / "bundle" / "manifest" / "nav.json")
    ap.add_argument("--products", default="enterprise,es8,soar,itsi")
    ap.add_argument("--depth", type=int, default=2, help="Branch depth to verify (0=root only)")
    ap.add_argument("--rate-limit", type=float, default=0.35)
    args = ap.parse_args()

    if not args.nav.exists():
        print(f"Missing {args.nav}", file=sys.stderr)
        return 2

    nav = json.loads(args.nav.read_text(encoding="utf-8"))
    products_cfg = load_products(ROOT / "scraper" / "products.yaml")
    selected = [p.strip() for p in args.products.split(",") if p.strip()]
    client = HelpClient(rate_limit=args.rate_limit)

    all_issues: List[str] = []
    total_branches = 0
    fetched: Dict[str, List[str]] = {}

    for pid in selected:
        if pid not in products_cfg:
            print(f"Unknown product {pid}", file=sys.stderr)
            continue
        product = next((p for p in nav if p.get("id") == pid), None)
        if not product:
            all_issues.append(f"[{pid}] missing from nav.json")
            continue
        cfg = products_cfg[pid]
        branches, issues = verify_product(
            client,
            pid,
            cfg["root_path"],
            product.get("children") or [],
            args.depth,
            fetched,
        )
        total_branches += branches
        all_issues.extend(issues)

    print(f"Verified {total_branches} branches (depth<={args.depth})")
    if all_issues:
        print(f"Found {len(all_issues)} issue(s):", file=sys.stderr)
        for line in all_issues:
            print(line, file=sys.stderr)
        return 1
    print("Nav order matches help.splunk.com")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
