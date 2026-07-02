#!/usr/bin/env python3
"""Run incremental documentation sync from help.splunk.com into the Splunk app."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow running as Splunk scripted input / standalone
BIN_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BIN_DIR))

import offline_docs_service as svc  # noqa: E402


def run_step(label: str, cmd: list[str], env: dict) -> None:
    print(f"==> {label}", flush=True)
    proc = subprocess.run(cmd, env=env, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"{label} failed with exit code {proc.returncode}")


def publish_bundle() -> None:
    """Docs are updated in place; no separate publish copy step."""
    print(f"Bundle in place at {svc.docs_dir()}", flush=True)


def finish_job(success: bool, error: str = "") -> None:
    job = svc.read_json(svc.state_path("update_job.json"), {})
    job["status"] = "success" if success else "error"
    job["finished_at"] = datetime.now(timezone.utc).isoformat()
    if error:
        job["error"] = error
    meta_path = svc.docs_dir() / "manifest" / "meta.json"
    meta = svc.read_json(meta_path, {})
    meta["last_sync_at"] = job["finished_at"]
    meta["last_sync_mode"] = job.get("mode", "incremental")
    svc.write_json(meta_path, meta)
    svc.write_json(svc.state_path("update_job.json"), job)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["incremental", "full"], default="incremental")
    ap.add_argument("--products", default=svc.DEFAULT_PRODUCTS)
    args = ap.parse_args()

    try:
        svc.ensure_bundle_seeded()
        root = svc.project_root()
        py = svc.python_bin()
        out = str(svc.bundle_dir())
        env = dict(**{k: v for k, v in __import__("os").environ.items()})
        env["PYTHONPATH"] = str(root)
        env["PYTHONUNBUFFERED"] = "1"

        refresh_flag = ["--refresh"] if args.mode == "full" else []
        run_step(
            "Rebuild navigation",
            [py, str(root / "scraper" / "rebuild_nav.py"), "--output", out,
             "--products", args.products, *refresh_flag],
            env,
        )
        run_step(
            "Patch nav manifest",
            [py, str(root / "scraper" / "patch_nav_manifest.py"),
             str(Path(out) / "manifest" / "nav.json")],
            env,
        )
        run_step(
            "Fetch missing topics",
            [py, str(root / "scraper" / "fetch_missing.py"), "--output", out,
             "--products", args.products],
            env,
        )
        run_step(
            "Repair bundle",
            [py, str(root / "scraper" / "repair_bundle.py"), "--output", out],
            env,
        )
        rewrite = svc.app_root() / "scripts" / "rewrite_deployed_links.py"
        if not rewrite.is_file():
            rewrite = svc.project_root() / "scripts" / "rewrite_deployed_links.py"
        if rewrite.is_file():
            run_step(
                "Rewrite internal links",
                [py, str(rewrite), "--app-dir", str(Path(out))],
                env,
            )
        publish_bundle()
        finish_job(True)
        print("Update completed successfully", flush=True)
        return 0
    except Exception as exc:
        finish_job(False, str(exc))
        print(f"Update failed: {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
