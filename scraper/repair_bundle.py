#!/usr/bin/env python3
"""Re-fetch empty topic HTML and rebuild manifest files."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from scraper.content import fetch_topic
from scraper.crawl import plain_text, save_checkpoint
from scraper.http_client import HelpClient
from scraper.links import build_link_index, rewrite_topic_html

ROOT = Path(__file__).resolve().parents[1]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="bundle")
    ap.add_argument("--rate-limit", type=float, default=0.35)
    ap.add_argument("--min-bytes", type=int, default=80)
    args = ap.parse_args()

    out = Path(args.output)
    topics_dir = out / "topics"
    manifest = out / "manifest"
    checkpoint_path = out / "checkpoint.json"
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    topics_meta = checkpoint.get("topics", {})

    client = HelpClient(rate_limit=args.rate_limit)
    repaired = 0
    for tid, meta in topics_meta.items():
        fp = topics_dir / f"{tid}.html"
        if fp.exists() and fp.stat().st_size >= args.min_bytes:
            continue
        path = meta["path"]
        try:
            topic = fetch_topic(client, path)
            meta["title"] = topic.title
            meta["breadcrumbs"] = topic.breadcrumbs
            meta["mini_toc"] = topic.mini_toc
            meta["resource_ids"] = topic.resource_ids
            fp.write_text(topic.html, encoding="utf-8")
            repaired += 1
            if repaired % 25 == 0:
                print(f"repaired {repaired} topics...", flush=True)
                save_checkpoint(checkpoint_path, checkpoint)
        except Exception as exc:
            print(f"WARN failed {path}: {exc}", file=sys.stderr, flush=True)

    save_checkpoint(checkpoint_path, checkpoint)
    print(f"Repaired {repaired} empty topics", flush=True)

    link_index = build_link_index(topics_meta)
    for tid, meta in topics_meta.items():
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
        for tid, m in topics_meta.items()
        if (fp := topics_dir / f"{tid}.html").exists()
    ]

    (manifest / "link-index.json").write_text(
        json.dumps(link_index, indent=2), encoding="utf-8"
    )
    (manifest / "search-index.json").write_text(
        json.dumps(search_index, indent=2), encoding="utf-8"
    )
    meta_path = manifest / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["repaired_at"] = datetime.now(timezone.utc).isoformat()
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    report = {
        "topics": len(topics_meta),
        "repaired": repaired,
        "built_at": datetime.now(timezone.utc).isoformat(),
    }
    (out / "scrape-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("Done:", report, flush=True)


if __name__ == "__main__":
    main()
