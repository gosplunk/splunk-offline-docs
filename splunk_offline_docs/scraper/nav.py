"""Build navigation tree from help.splunk.com TOC fragments (portal order)."""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

from bs4 import BeautifulSoup

from .http_client import HelpClient

NAV_PREFIX = "/en/fragments/nav/"
VERSION_TITLE = re.compile(r"^\d+\.\d+$")


@dataclass
class NavNode:
    path: str
    title: str
    children: List["NavNode"] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "title": self.title,
            "children": [c.to_dict() for c in self.children],
        }


def _log(msg: str, log: Optional[Callable[[str], None]] = None) -> None:
    if log:
        log(msg)
    else:
        print(msg, flush=True)


SMALL_WORDS = {"a", "an", "and", "as", "at", "for", "in", "of", "on", "or", "the", "to", "with"}
ACRONYMS = {
    "api", "es", "http", "ite", "itsi", "kafka", "mcp", "odbc", "ot", "pci",
    "pod", "rest", "soar", "spl", "sql", "vm",
}


def _title_from_path(path: str) -> str:
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


def _prefer_path_title(title: str, path: str) -> str:
    path_title = _title_from_path(path)
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


def _clean_nav_title(title: str, path: str = "") -> str:
    title = (title or "").strip()
    if not title:
        return ""
    # Portal sometimes glues description onto the title in link text.
    m = re.match(r"^(.+?[a-z])(?=[A-Z][a-z].{12,})", title)
    if m:
        candidate = m.group(1).strip()
        if len(candidate.split()) >= 2 or len(candidate) >= 18:
            title = candidate
    title = title[:120]
    if path:
        title = _prefer_path_title(title, path)
    return title


def _title_from_link(a, path: str = "") -> str:
    link_path = (a.get("data-href") or path or "").strip()
    span = a.find("span", recursive=False)
    if span:
        return _clean_nav_title(span.get_text(strip=True), link_path)
    return _clean_nav_title(a.get_text(" ", strip=True), link_path)


def _is_excluded_version(title: str) -> bool:
    m = VERSION_TITLE.match(title.strip())
    if not m:
        return False
    major = int(title.split(".")[0])
    return major < 10


def _parse_toc_children(soup: BeautifulSoup, root_path: str) -> List[Tuple[str, str, bool]]:
    panel = soup.find(id="navigation-panel") or soup
    tree = panel.select_one("ul.toc-tree")
    if not tree:
        return []
    items: List[Tuple[str, str, bool]] = []
    for li in tree.find_all("li", recursive=False):
        a = li.select_one('a[data-testid="toc-link"]')
        if not a:
            continue
        path = (a.get("data-href") or "").strip()
        if not path.startswith(root_path):
            continue
        title = _title_from_link(a, path)
        if not title or _is_excluded_version(title):
            continue
        has_children = a.get("data-has-children") == "true"
        items.append((path, title, has_children))
    return items


def _fetch_nav_children(
    client: HelpClient,
    branch_path: str,
    root_path: str,
    log: Optional[Callable[[str], None]],
    fetched: Set[str],
    stats: Dict[str, int],
) -> List[NavNode]:
    if branch_path in fetched:
        return []
    fetched.add(branch_path)
    stats["branches"] = stats.get("branches", 0) + 1

    try:
        html = client.get(NAV_PREFIX + branch_path)
    except Exception as exc:
        _log(f"  nav: WARN branch {branch_path}: {exc}", log)
        return []

    items = _parse_toc_children(BeautifulSoup(html, "lxml"), root_path)
    nodes: List[NavNode] = []
    for path, title, has_children in items:
        children: List[NavNode] = []
        if has_children:
            children = _fetch_nav_children(
                client, path, root_path, log, fetched, stats
            )
        nodes.append(NavNode(path=path, title=title, children=children))
        stats["paths"] = stats.get("paths", 0) + 1

    if stats["branches"] % 50 == 0:
        _log(
            f"  nav: expanded {stats['branches']} branches, {stats.get('paths', 0)} paths",
            log,
        )
    return nodes


def discover_nav_tree(
    client: HelpClient,
    root_path: str,
    log: Optional[Callable[[str], None]] = None,
) -> NavNode:
    _log(f"  nav: loading tree from {root_path}", log)
    fetched: Set[str] = set()
    stats: Dict[str, int] = {"branches": 0, "paths": 0}
    children = _fetch_nav_children(
        client, root_path, root_path, log, fetched, stats
    )
    _log(
        f"  nav: done — {stats.get('paths', 0)} paths from {stats.get('branches', 0)} branches",
        log,
    )
    return NavNode(path=root_path, title="", children=children)


def load_cached_tree(cache_file: Path) -> Optional[NavNode]:
    if not cache_file.exists():
        return None
    data = json.loads(cache_file.read_text(encoding="utf-8"))

    def from_dict(d: dict) -> NavNode:
        return NavNode(
            path=d["path"],
            title=d.get("title", ""),
            children=[from_dict(c) for c in d.get("children", [])],
        )

    return from_dict(data)


def save_cached_tree(cache_file: Path, root: NavNode) -> None:
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(root.to_dict(), indent=2), encoding="utf-8")


def collect_paths(node: NavNode) -> Dict[str, str]:
    paths = {node.path: node.title}
    for child in node.children:
        paths.update(collect_paths(child))
    return paths


def build_product_nav(
    client: HelpClient,
    root_path: str,
    title: str,
    cache_file: Optional[Path] = None,
    log: Optional[Callable[[str], None]] = None,
) -> NavNode:
    root = None
    if cache_file and cache_file.exists():
        root = load_cached_tree(cache_file)
        if root:
            _log(f"  nav: loaded cached tree ({len(collect_paths(root))} paths)", log)

    if not root:
        root = discover_nav_tree(client, root_path, log=log)
        if cache_file:
            save_cached_tree(cache_file, root)

    root.title = title
    return root


def iter_topic_paths(node: NavNode):
    yield node.path
    for child in node.children:
        yield from iter_topic_paths(child)
