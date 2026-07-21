#!/usr/bin/env python3
"""Shared service logic for Splunk Offline Docs configuration and updates."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

APP_NAME = "splunk_offline_docs"
DEFAULT_PRODUCTS = "enterprise,es8,soar,itsi"
VERSION_TITLE = re.compile(r"^\d+\.\d+$")
VERSION_IN_PATH = re.compile(r"(?<![0-9])(\d+\.\d+(?:\.\d+)?)(?![0-9])")


def app_root() -> Path:
    env = os.environ.get("SPLUNK_OFFLINE_DOCS_APP")
    if env:
        return Path(env)
    # bin/ -> app root
    return Path(__file__).resolve().parents[1]


def splunk_home() -> Path:
    return Path(os.environ.get("SPLUNK_HOME", "/opt/splunk"))


def local_dir() -> Path:
    path = app_root() / "local"
    try:
        path.mkdir(parents=True, exist_ok=True)
        os.chmod(path, 0o755)
    except OSError:
        pass
    return path


def bundle_dir() -> Path:
    """Working bundle path — same as published docs (no duplicate local/bundle copy)."""
    return docs_dir()


def docs_dir() -> Path:
    path = app_root() / "appserver" / "static" / "docs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def state_path(name: str) -> Path:
    return local_dir() / name


def read_json(path: Path, default: Any = None) -> Any:
    try:
        if not path.is_file():
            return default
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, PermissionError):
        return default


def write_json(path: Path, data: Any) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except (OSError, PermissionError) as exc:
        raise RuntimeError(f"Cannot write {path}: {exc}") from exc


def load_settings() -> dict:
    defaults = {
        "products": DEFAULT_PRODUCTS,
        "rate_limit": 0.35,
        "python": "/usr/bin/python3",
        "scraper_root": "",
        "daily_check_enabled": False,
    }
    conf_path = app_root() / "default" / "offline_docs.conf"
    if conf_path.is_file():
        for line in conf_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = [p.strip() for p in line.split("=", 1)]
            if key == "products":
                defaults["products"] = value
            elif key == "rate_limit":
                defaults["rate_limit"] = float(value)
            elif key == "python":
                defaults["python"] = value
            elif key == "scraper_root":
                defaults["scraper_root"] = value
            elif key == "daily_check_enabled":
                defaults["daily_check_enabled"] = value.lower() in ("1", "true", "yes")
    local_settings = read_json(state_path("settings.json"), {})
    defaults.update({k: v for k, v in local_settings.items() if v is not None})
    return defaults


def scraper_root() -> Path:
    settings = load_settings()
    app = app_root()
    # Prefer scraper bundled inside the installed app over dev clones on the host.
    candidates = [
        settings.get("scraper_root"),
        str(app),
        os.environ.get("SPLUNK_OFFLINE_DOCS_ROOT"),
        str(app.parents[1]),
    ]
    for raw in candidates:
        if not raw:
            continue
        path = Path(raw)
        if (path / "scraper" / "products.yaml").is_file():
            return path
        if path.name == "scraper" and (path / "products.yaml").is_file():
            return path.parent
    raise FileNotFoundError(
        "Scraper source not found. Set scraper_root in local/settings.json "
        "or bundle scraper/ inside the app."
    )


def project_root() -> Path:
    app = app_root()
    if (app / "scraper" / "products.yaml").is_file():
        return app
    root = scraper_root()
    if (root / "scraper" / "products.yaml").is_file():
        return root
    return root.parent


def docs_bundle_ready() -> tuple[bool, str]:
    """Return whether the offline docs bundle is present enough to browse."""
    docs = docs_dir()
    nav = docs / "manifest" / "nav.json"
    link_index = docs / "manifest" / "link-index.json"
    topics = docs / "topics"
    topic_files = list(topics.glob("*.html")) if topics.is_dir() else []
    if nav.is_file() and link_index.is_file() and len(topic_files) >= 100:
        return True, ""
    missing = []
    if not nav.is_file():
        missing.append("manifest/nav.json")
    if not link_index.is_file():
        missing.append("manifest/link-index.json")
    if len(topic_files) < 100:
        missing.append(f"topics/ ({len(topic_files)} html files)")
    hint = (
        "Install splunk_offline_docs_full.tgz (documentation included). "
        "The app-only splunk_offline_docs.tgz (~3 MB) does not ship docs."
    )
    return False, f"Docs bundle incomplete: missing {', '.join(missing)}. {hint}"


def python_bin() -> str:
    """Return system Python for scraper subprocesses (not Splunk's embedded interpreter)."""
    configured = (load_settings().get("python") or "").strip()
    if configured and Path(configured).is_file():
        return configured
    for candidate in ("/usr/bin/python3", "/usr/local/bin/python3"):
        if Path(candidate).is_file():
            return candidate
    found = shutil.which("python3")
    if found and "splunk" not in found.replace("\\", "/").lower():
        return found
    return "/usr/bin/python3"


def scraper_env() -> dict:
    env = os.environ.copy()
    root = project_root()
    app = app_root()
    paths = [str(root), str(app)]
    vendor = app / "lib" / "python"
    if vendor.is_dir():
        paths.append(str(vendor))
    env["PYTHONPATH"] = os.pathsep.join(paths)
    env["SPLUNK_OFFLINE_DOCS_APP"] = str(app)
    env["PYTHONUNBUFFERED"] = "1"
    return env


def ensure_bundle_seeded() -> None:
    """Ensure docs tree exists and remove legacy duplicate local/bundle workspace."""
    docs_dir()
    legacy = local_dir() / "bundle"
    if legacy.is_dir():
        shutil.rmtree(legacy, ignore_errors=True)


def bundle_stats() -> dict:
    docs = docs_dir()
    topics = list((docs / "topics").glob("*.html")) if (docs / "topics").is_dir() else []
    meta = read_json(docs / "manifest" / "meta.json", {})
    app_conf = app_root() / "default" / "app.conf"
    version = "unknown"
    if app_conf.is_file():
        for line in app_conf.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("version"):
                version = line.split("=", 1)[1].strip()
                break
    return {
        "app_version": version,
        "topic_count": len(topics),
        "meta": meta,
        "docs_path": str(docs),
        "scrape": scrape_stats(docs, meta),
    }


def _dir_size(path: Path) -> int:
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    if not path.is_dir():
        return 0
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += (Path(root) / name).stat().st_size
            except OSError:
                continue
    return total


def _fmt_bytes(num: int) -> str:
    if num < 1024:
        return f"{num} B"
    units = ["KB", "MB", "GB", "TB"]
    value = float(num)
    for unit in units:
        value /= 1024.0
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}"
    return f"{value:.1f} TB"


def _version_sort_key(version: str) -> tuple:
    parts: List[Any] = []
    for piece in version.split("."):
        try:
            parts.append(int(piece))
        except ValueError:
            parts.append(piece)
    return tuple(parts)


def versions_in_paths(paths: List[str]) -> List[str]:
    found: set[str] = set()
    for path in paths:
        for seg in path.split("/"):
            if VERSION_TITLE.match(seg):
                found.add(seg)
        for match in VERSION_IN_PATH.finditer(path):
            found.add(match.group(1))
    return sorted(found, key=_version_sort_key, reverse=True)


def _topic_counts_by_product(docs: Path) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    index_path = docs / "manifest" / "search-index.json"
    if not index_path.is_file():
        return counts
    try:
        entries = json.loads(index_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return counts
    if not isinstance(entries, list):
        return counts
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        pid = entry.get("product") or "unknown"
        counts[pid] = counts.get(pid, 0) + 1
    return counts


def _collect_nav_paths(node: dict) -> List[str]:
    paths: List[str] = []

    def walk(item: dict) -> None:
        path = item.get("path")
        if path:
            paths.append(path)
        for child in item.get("children") or []:
            if isinstance(child, dict):
                walk(child)

    walk(node)
    return paths


def _product_version_hint(product_id: str) -> Optional[str]:
    if product_id == "es8":
        return "8.x"
    return None


def scrape_stats(docs: Path, meta: Optional[dict] = None) -> dict:
    meta = meta or read_json(docs / "manifest" / "meta.json", {})
    manifest = docs / "manifest"
    topic_counts = _topic_counts_by_product(docs)

    disk = {
        "total_bytes": _dir_size(docs),
        "topics_bytes": _dir_size(docs / "topics"),
        "manifest_bytes": _dir_size(manifest),
        "nav_cache_bytes": _dir_size(docs / "nav-cache"),
    }
    disk["total_human"] = _fmt_bytes(disk["total_bytes"])
    disk["topics_human"] = _fmt_bytes(disk["topics_bytes"])
    disk["manifest_human"] = _fmt_bytes(disk["manifest_bytes"])
    disk["nav_cache_human"] = _fmt_bytes(disk["nav_cache_bytes"])

    manifest_files = {
        "nav_json_bytes": (manifest / "nav.json").stat().st_size if (manifest / "nav.json").is_file() else 0,
        "link_index_bytes": (manifest / "link-index.json").stat().st_size if (manifest / "link-index.json").is_file() else 0,
        "search_index_bytes": (manifest / "search-index.json").stat().st_size if (manifest / "search-index.json").is_file() else 0,
    }
    manifest_files["nav_json_human"] = _fmt_bytes(manifest_files["nav_json_bytes"])
    manifest_files["link_index_human"] = _fmt_bytes(manifest_files["link_index_bytes"])
    manifest_files["search_index_human"] = _fmt_bytes(manifest_files["search_index_bytes"])

    products: List[dict] = []
    nav = read_json(manifest / "nav.json", [])
    if isinstance(nav, list):
        for node in nav:
            if not isinstance(node, dict):
                continue
            pid = node.get("id") or ""
            paths = _collect_nav_paths(node)
            versions = versions_in_paths(paths)
            hint = _product_version_hint(pid)
            if not versions and hint:
                versions = [hint]
            products.append({
                "id": pid,
                "title": node.get("title") or pid,
                "versions": versions,
                "version_count": len(versions),
                "latest_version": versions[0] if versions else hint,
                "nav_branches": len(node.get("children") or []),
                "nav_paths": len(paths),
                "topic_count": topic_counts.get(pid, 0),
            })

    timestamps = {
        "source": meta.get("source"),
        "built_at": meta.get("built_at"),
        "updated_at": meta.get("updated_at"),
        "repaired_at": meta.get("repaired_at"),
        "nav_rebuilt_at": meta.get("nav_rebuilt_at"),
        "last_sync_at": meta.get("last_sync_at") or meta.get("updated_at") or meta.get("built_at"),
    }

    return {
        "disk": disk,
        "manifest_files": manifest_files,
        "products": products,
        "timestamps": timestamps,
        "topic_count_indexed": sum(topic_counts.values()),
        "topic_count_files": len(list((docs / "topics").glob("*.html"))) if (docs / "topics").is_dir() else 0,
    }


def get_job() -> dict:
    return read_json(state_path("update_job.json"), {"status": "idle"})


def is_job_running() -> bool:
    job = get_job()
    if job.get("status") != "running":
        return False
    pid = job.get("pid")
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        job["status"] = "error"
        job["error"] = "Update process exited unexpectedly"
        job["finished_at"] = datetime.now(timezone.utc).isoformat()
        write_json(state_path("update_job.json"), job)
        return False


def tail_log(path: Path, lines: int = 40) -> List[str]:
    if not path.is_file():
        return []
    try:
        content = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return content[-lines:]
    except OSError:
        return []


def get_status() -> dict:
    check = read_json(state_path("check_report.json"), {})
    job = get_job()
    if is_job_running():
        job["status"] = "running"
    settings = load_settings()
    try:
        scraper_path = str(scraper_root())
    except Exception as exc:
        scraper_path = str(exc)
    bundle_ok, bundle_hint = docs_bundle_ready()
    return {
        "bundle": {
            **bundle_stats(),
            "ready": bundle_ok,
            "ready_hint": bundle_hint,
        },
        "check": check,
        "job": {
            **job,
            "log_tail": tail_log(state_path("update_job.log")),
        },
        "settings": {
            "products": settings.get("products", DEFAULT_PRODUCTS),
            "daily_check_enabled": settings.get("daily_check_enabled", False),
            "scraper_root": scraper_path,
            "python": python_bin(),
        },
    }


def run_check(save: bool = True) -> dict:
    ensure_bundle_seeded()
    settings = load_settings()
    nav_path = docs_dir() / "manifest" / "nav.json"
    if not nav_path.is_file():
        nav_path = bundle_dir() / "manifest" / "nav.json"
    products_yaml = scraper_root() / "products.yaml"
    if not products_yaml.is_file():
        products_yaml = scraper_root() / "scraper" / "products.yaml"

    cmd = [
        python_bin(),
        str(project_root() / "scraper" / "check_updates.py"),
        "--nav", str(nav_path),
        "--products", settings.get("products", DEFAULT_PRODUCTS),
        "--products-yaml", str(products_yaml),
        "--rate-limit", str(settings.get("rate_limit", 0.35)),
        "--output", str(state_path("check_report.json")),
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=scraper_env(),
        timeout=600,
        check=False,
    )
    report = read_json(state_path("check_report.json"), {})
    if not report or not report.get("products"):
        err = proc.stderr.strip() or proc.stdout.strip()
        if not report:
            report = {
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "updates_available": False,
                "products": [],
            }
        if proc.returncode != 0 and err:
            report["error"] = err
        elif proc.returncode != 0:
            report["error"] = f"check_updates.py exited with code {proc.returncode}"
        if save:
            write_json(state_path("check_report.json"), report)
    report["exit_code"] = proc.returncode
    return report


def start_update(mode: str = "incremental") -> dict:
    if is_job_running():
        return {"ok": False, "error": "An update is already running", "job": get_job()}

    bundle_ok, bundle_hint = docs_bundle_ready()
    if mode == "incremental" and not bundle_ok:
        return {"ok": False, "error": bundle_hint, "job": get_job()}

    log_path = state_path("update_job.log")
    log_path.write_text("", encoding="utf-8")
    settings = load_settings()
    job = {
        "status": "running",
        "mode": mode,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "products": settings.get("products", DEFAULT_PRODUCTS),
    }
    write_json(state_path("update_job.json"), job)

    script = app_root() / "bin" / "offline_docs_run_sync.py"
    env = scraper_env()
    with open(log_path, "a", encoding="utf-8") as logf:
        proc = subprocess.Popen(
            [
                python_bin(),
                str(script),
                "--mode", mode,
                "--products", settings.get("products", DEFAULT_PRODUCTS),
            ],
            stdout=logf,
            stderr=subprocess.STDOUT,
            env=env,
            cwd=str(app_root()),
        )
    job["pid"] = proc.pid
    write_json(state_path("update_job.json"), job)
    return {"ok": True, "job": job}


def coerce_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("0", "false", "no", "off", "disabled"):
        return False
    if text in ("1", "true", "yes", "on", "enabled"):
        return True
    return False


def save_settings(updates: dict) -> dict:
    current = load_settings()
    allowed = {"products", "rate_limit", "python", "scraper_root", "daily_check_enabled"}
    local = read_json(state_path("settings.json"), {})
    for key, value in updates.items():
        if key not in allowed or value is None:
            continue
        if key == "daily_check_enabled":
            current[key] = coerce_bool(value)
        else:
            current[key] = value
    for key in allowed:
        if key in current:
            local[key] = current[key]
    write_json(state_path("settings.json"), local)
    return current
