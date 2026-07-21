#!/usr/bin/env python3
"""Clean nav titles and product order in an existing manifest/nav.json."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from scraper.content import path_to_topic_id

PRODUCT_ORDER = ["enterprise", "es8", "soar", "itsi"]
PRODUCT_TITLES = {
    "enterprise": "Splunk Enterprise",
    "es8": "Enterprise Security",
    "soar": "SOAR (On-premises)",
    "itsi": "IT Service Intelligence",
}

GLUED = re.compile(r"^(.+?[a-z])(?=[A-Z][a-z].{12,})")


def clean_title(title: str) -> str:
    title = (title or "").strip()
    if not title:
        return ""
    m = GLUED.match(title)
    if m:
        title = m.group(1).strip()
    return title[:120]


VERSION_TITLE = re.compile(r"^\d+\.\d+(\.\d+)?$")
SMALL_WORDS = {"a", "an", "and", "as", "at", "for", "in", "of", "on", "or", "the", "to", "with"}
ACRONYMS = {
    "api", "es", "http", "ite", "itsi", "kafka", "mcp", "odbc", "ot", "pci",
    "pod", "rest", "soar", "spl", "sql", "vm",
}


def title_from_path(path: str) -> str:
    slug = (path or "").rstrip("/").split("/")[-1]
    if not slug or VERSION_TITLE.match(slug):
        return ""
    parts = slug.split("-")
    words: list[str] = []
    for i, part in enumerate(parts):
        low = part.lower()
        if low in ACRONYMS:
            words.append(low.upper())
        elif i > 0 and low in SMALL_WORDS:
            words.append(low)
        else:
            words.append(low.capitalize())
    return " ".join(words)


def best_title(title: str, path: str) -> str:
    title = clean_title(title)
    path_title = title_from_path(path)
    if not path_title:
        return title
    if len(title) < 8:
        return path_title
    trimmed = title.rstrip()
    if trimmed.endswith("(") or trimmed.endswith("..."):
        return path_title
    tl, pl = title.lower(), path_title.lower()
    if pl.startswith(tl) and len(title) < len(path_title):
        return path_title
    if len(title) < len(path_title) * 0.65:
        return path_title
    return title


def annotate_topic_ids(nodes: list, topics_dir: Path | None) -> None:
    if not topics_dir or not topics_dir.is_dir():
        return
    for node in nodes:
        path = (node.get("path") or "").strip()
        if path:
            tid = path_to_topic_id(path)
            if (topics_dir / f"{tid}.html").is_file():
                node["topic_id"] = tid
        annotate_topic_ids(node.get("children") or [], topics_dir)


def walk(nodes: list) -> None:
    for node in nodes:
        node["title"] = best_title(node.get("title", ""), node.get("path", ""))
        walk(node.get("children") or [])


def patch_nav_file(nav_path: Path, topics_dir: Path | None = None) -> None:
    nav = json.loads(nav_path.read_text(encoding="utf-8"))
    nav.sort(
        key=lambda p: (
            PRODUCT_ORDER.index(p["id"])
            if p.get("id") in PRODUCT_ORDER
            else 99
        )
    )
    for product in nav:
        pid = product.get("id", "")
        if pid in PRODUCT_TITLES:
            product["title"] = PRODUCT_TITLES[pid]
        walk(product.get("children") or [])
        annotate_topic_ids(product.get("children") or [], topics_dir)

    nav_path.write_text(json.dumps(nav, indent=2), encoding="utf-8")
    print(f"Patched {nav_path}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("nav_json", type=Path)
    ap.add_argument(
        "--topics-dir",
        type=Path,
        default=None,
        help="If set, add topic_id to nodes whose HTML exists under this directory",
    )
    args = ap.parse_args()
    patch_nav_file(args.nav_json, args.topics_dir)


if __name__ == "__main__":
    main()
