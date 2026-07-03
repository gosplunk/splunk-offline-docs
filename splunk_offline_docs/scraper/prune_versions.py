#!/usr/bin/env python3
"""Remove documentation topics outside the configured latest-N version window."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from scraper.versions import (
    filter_nav_node,
    latest_version_allowlist,
    path_matches_version_allowlist,
    version_sort_key,
    versions_in_paths,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_KEEP = {"soar": 2, "itsi": 2}
_MIN_SUFFIX_LEN = 12


def _build_suffix_index(by_path: Dict[str, str]) -> Dict[str, str]:
    suffix_map: Dict[str, str] = {}
    best_len: Dict[str, int] = {}
    for path, tid in by_path.items():
        if path.startswith("en/"):
            continue
        parts = path.split("/")
        for i in range(1, len(parts)):
            suf = "/".join(parts[i:])
            if len(suf) < _MIN_SUFFIX_LEN:
                continue
            if suf not in suffix_map or len(path) > best_len[suf]:
                suffix_map[suf] = tid
                best_len[suf] = len(path)
    return suffix_map


def build_link_index_from_search(entries: List[dict]) -> dict:
    by_path: Dict[str, str] = {}
    by_title: Dict[str, str] = {}
    by_tail: Dict[str, str] = {}
    for entry in entries:
        tid = entry["id"]
        path = entry["path"].strip("/")
        by_path[path] = tid
        by_path[f"en/{path}"] = tid
        tail = path.split("/")[-1]
        if tail and tail not in by_tail:
            by_tail[tail] = tid
        title = (entry.get("title") or "").strip().lower()
        if title and title not in by_title:
            by_title[title] = tid
    return {
        "paths": by_path,
        "resourceIds": {},
        "suffixes": _build_suffix_index(by_path),
        "titles": by_title,
        "tails": by_tail,
    }


def load_version_keep(products_path: Path, pid: str) -> int:
    """Parse version_filter from products.yaml without requiring PyYAML."""
    if products_path.is_file():
        current = None
        for raw in products_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.endswith(":") and not raw.startswith(" "):
                current = line[:-1]
                continue
            if current == pid and line.startswith("version_filter:"):
                value = line.split(":", 1)[1].strip().strip('"').strip("'")
                if value.startswith("latest_"):
                    try:
                        return int(value.split("_", 1)[1])
                    except ValueError:
                        return 0
                return 0
    return DEFAULT_KEEP.get(pid, 0)


def rebuild_manifest(out: Path, entries: list, nav_trees: list) -> None:
    manifest = out / "manifest"
    link_index = build_link_index_from_search(entries)

    (manifest / "nav.json").write_text(json.dumps(nav_trees, indent=2), encoding="utf-8")
    (manifest / "link-index.json").write_text(
        json.dumps(link_index, indent=2), encoding="utf-8"
    )
    (manifest / "search-index.json").write_text(
        json.dumps(entries, indent=2), encoding="utf-8"
    )

    meta_path = manifest / "meta.json"
    meta = {}
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["topic_count"] = len(entries)
    meta["pruned_at"] = datetime.now(timezone.utc).isoformat()
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True, help="Bundle directory (contains manifest/ and topics/)")
    ap.add_argument("--products", default="soar,itsi")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    out = Path(args.output)
    manifest = out / "manifest"
    search_path = manifest / "search-index.json"
    nav_path = manifest / "nav.json"
    if not search_path.is_file() or not nav_path.is_file():
        print("Missing manifest/search-index.json or nav.json", file=sys.stderr)
        return 1

    products_path = out.parents[2] / "scraper" / "products.yaml"
    if not products_path.is_file():
        products_path = ROOT / "scraper" / "products.yaml"
    selected = [p.strip() for p in args.products.split(",") if p.strip()]
    entries = json.loads(search_path.read_text(encoding="utf-8"))
    nav_trees = json.loads(nav_path.read_text(encoding="utf-8"))

    removed = 0
    kept_entries = []

    allowlists = {}
    for pid in selected:
        keep_n = load_version_keep(products_path, pid)
        if not keep_n:
            print(f"[{pid}] no version_filter configured — skipping", flush=True)
            continue
        paths = [e["path"] for e in entries if e.get("product") == pid]
        allowed = latest_version_allowlist(paths, keep_n)
        allowlists[pid] = allowed
        ordered = versions_in_paths(paths)
        print(
            f"[{pid}] keeping {sorted(allowed, key=version_sort_key, reverse=True)} "
            f"(latest {keep_n} of {len(ordered)} versions)",
            flush=True,
        )

    for entry in entries:
        pid = entry.get("product")
        allowed = allowlists.get(pid)
        if allowed is not None and not path_matches_version_allowlist(entry.get("path", ""), allowed):
            removed += 1
            if not args.dry_run:
                fp = out / "topics" / f"{entry['id']}.html"
                if fp.is_file():
                    fp.unlink()
            continue
        kept_entries.append(entry)

    if not args.dry_run:
        for i, tree in enumerate(nav_trees):
            pid = tree.get("id") or tree.get("product")
            if pid in allowlists:
                nav_trees[i] = filter_nav_node(tree, allowlists[pid])
        rebuild_manifest(out, kept_entries, nav_trees)

    print(
        f"{'Would remove' if args.dry_run else 'Removed'} {removed} topics; "
        f"{len(kept_entries)} remain",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
