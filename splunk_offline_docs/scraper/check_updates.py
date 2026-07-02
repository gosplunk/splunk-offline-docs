#!/usr/bin/env python3
"""Check help.splunk.com for documentation updates vs the local bundle."""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import yaml
from bs4 import BeautifulSoup

from scraper.http_client import HelpClient
from scraper.nav import NAV_PREFIX, VERSION_TITLE, _parse_toc_children

ROOT = Path(__file__).resolve().parents[1]
VERSION_IN_PATH = re.compile(r"(?<![0-9])(\d+\.\d+(?:\.\d+)?)(?![0-9])")


def load_products(cfg_path: Path) -> dict:
    with open(cfg_path, encoding="utf-8") as f:
        return yaml.safe_load(f)["products"]


def help_child_paths(client: HelpClient, parent_path: str, root_path: str) -> List[str]:
    html = client.get(NAV_PREFIX + parent_path)
    items = _parse_toc_children(BeautifulSoup(html, "lxml"), root_path)
    return [path for path, _title, _has_kids in items]


def versions_in_paths(paths: List[str]) -> set[str]:
    found: set[str] = set()
    for path in paths:
        for seg in path.split("/"):
            if VERSION_TITLE.match(seg):
                found.add(seg)
        for match in VERSION_IN_PATH.finditer(path):
            found.add(match.group(1))
    return found


def check_product(
    client: HelpClient,
    product_id: str,
    cfg: dict,
    local_product: Optional[dict],
) -> dict:
    root_path = cfg["root_path"]
    title = cfg.get("title", product_id)
    result = {
        "id": product_id,
        "title": title,
        "root_path": root_path,
        "missing_count": 0,
        "missing_sample": [],
        "extra_count": 0,
        "new_versions": [],
        "nav_drift": False,
        "error": None,
    }

    if not local_product:
        result["error"] = "missing from local nav.json"
        result["missing_count"] = -1
        return result

    try:
        help_roots = help_child_paths(client, root_path, root_path)
    except Exception as exc:
        result["error"] = str(exc)
        return result

    local_roots = [c.get("path", "") for c in local_product.get("children") or []]
    help_set, local_set = set(help_roots), set(local_roots)
    missing = sorted(help_set - local_set)
    extra = sorted(local_set - help_set)

    help_versions = versions_in_paths(help_roots)
    local_versions = versions_in_paths(local_roots)
    new_versions = sorted(help_versions - local_versions)

    result["missing_count"] = len(missing)
    result["missing_sample"] = missing[:12]
    result["extra_count"] = len(extra)
    result["new_versions"] = new_versions
    result["nav_drift"] = help_roots != local_roots
    return result


def run_check(
    nav_path: Path,
    products_cfg: dict,
    selected: List[str],
    rate_limit: float = 0.35,
) -> dict:
    if not nav_path.is_file():
        raise FileNotFoundError(f"Missing nav manifest: {nav_path}")

    nav = json.loads(nav_path.read_text(encoding="utf-8"))
    client = HelpClient(rate_limit=rate_limit)
    products: List[dict] = []
    updates_available = False

    for pid in selected:
        if pid not in products_cfg:
            continue
        local_product = next((p for p in nav if p.get("id") == pid), None)
        report = check_product(client, pid, products_cfg[pid], local_product)
        if report.get("error") == "missing from local nav.json":
            updates_available = True
        elif report.get("error"):
            pass
        elif (
            report.get("missing_count", 0) > 0
            or report.get("new_versions")
            or report.get("nav_drift")
        ):
            updates_available = True
        products.append(report)

    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "updates_available": updates_available,
        "products": products,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Check for help.splunk.com doc updates")
    ap.add_argument("--nav", type=Path, required=True)
    ap.add_argument("--products", default="enterprise,es8,soar,itsi")
    ap.add_argument("--products-yaml", type=Path, default=ROOT / "scraper" / "products.yaml")
    ap.add_argument("--rate-limit", type=float, default=0.35)
    ap.add_argument("--output", type=Path, help="Write JSON report to this path")
    args = ap.parse_args()

    products_cfg = load_products(args.products_yaml)
    selected = [p.strip() for p in args.products.split(",") if p.strip()]
    report = run_check(args.nav, products_cfg, selected, args.rate_limit)

    payload = json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload)
    return 1 if report["updates_available"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
