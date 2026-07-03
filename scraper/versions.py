"""Version detection and filtering for product documentation paths."""
from __future__ import annotations

import re
from typing import Iterable, List, Optional, Set

VERSION_SEGMENT_RE = re.compile(r"^\d+\.\d+(?:\.\d+)?$")


def version_sort_key(version: str) -> tuple:
    return tuple(int(p) if p.isdigit() else p for p in version.split("."))


def is_version_segment(segment: str) -> bool:
    return bool(VERSION_SEGMENT_RE.match(segment or ""))


def path_version_segments(path: str) -> List[str]:
    return [seg for seg in (path or "").split("/") if is_version_segment(seg)]


def versions_in_paths(paths: Iterable[str]) -> List[str]:
    found: Set[str] = set()
    for path in paths:
        found.update(path_version_segments(path))
    return sorted(found, key=version_sort_key, reverse=True)


def latest_version_allowlist(paths: Iterable[str], keep: int = 2) -> Set[str]:
    if keep < 1:
        return set()
    return set(versions_in_paths(paths)[:keep])


def path_matches_version_allowlist(path: str, allowed: Set[str]) -> bool:
    """Keep unversioned paths; versioned paths must only use allowed versions."""
    segs = path_version_segments(path)
    if not segs:
        return True
    return all(seg in allowed for seg in segs)


def version_filter_keep(cfg: dict) -> Optional[int]:
    raw = (cfg or {}).get("version_filter")
    if not raw or raw == "none":
        return None
    if raw == "latest_2":
        return 2
    if raw == "latest_1":
        return 1
    if raw.startswith("latest_"):
        try:
            return int(raw.split("_", 1)[1])
        except ValueError:
            return None
    return None


def is_version_branch(nodes: List[dict]) -> bool:
    if not nodes:
        return False
    for node in nodes:
        title = (node.get("title") or "").strip()
        if not is_version_segment(title) and not path_version_segments(node.get("path") or ""):
            return False
    return True


def node_version(node: dict) -> Optional[str]:
    title = (node.get("title") or "").strip()
    if is_version_segment(title):
        return title
    segs = path_version_segments(node.get("path") or "")
    return segs[0] if segs else None


def filter_nav_node(node: dict, allowed: Set[str]) -> dict:
    children = node.get("children") or []
    filtered: List[dict] = []

    if is_version_branch(children):
        for child in children:
            ver = node_version(child)
            if ver and ver in allowed:
                filtered.append(filter_nav_node(child, allowed))
        out = dict(node)
        out["children"] = filtered
        return out

    for child in children:
        filtered.append(filter_nav_node(child, allowed))

    out = dict(node)
    out["children"] = filtered
    return out
