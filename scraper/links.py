"""Rewrite internal documentation links for offline bundle."""
from __future__ import annotations

import re
from typing import Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

_VERSION_RE = re.compile(r"^\d+\.\d+(?:\.\d+)?$")
_MIN_SUFFIX_LEN = 12


def _version_from_path(path: str) -> Optional[str]:
    for seg in (path or "").strip("/").split("/"):
        if _VERSION_RE.match(seg):
            return seg
    return None


def _build_suffix_index(by_path: Dict[str, str]) -> Dict[str, str]:
    """Map path tail -> topic id (prefer longest indexed path per suffix)."""
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


def build_link_index(topics: Dict[str, dict]) -> dict:
    by_path: Dict[str, str] = {}
    by_resource: Dict[str, str] = {}
    by_title: Dict[str, str] = {}
    by_tail: Dict[str, str] = {}
    for tid, meta in topics.items():
        path = meta["path"].strip("/")
        by_path[path] = tid
        by_path[f"en/{path}"] = tid
        tail = path.split("/")[-1]
        if tail and tail not in by_tail:
            by_tail[tail] = tid
        title = (meta.get("title") or "").strip().lower()
        if title and title not in by_title:
            by_title[title] = tid
        for rid in meta.get("resource_ids", []):
            by_resource[rid] = tid
    return {
        "paths": by_path,
        "resourceIds": by_resource,
        "suffixes": _build_suffix_index(by_path),
        "titles": by_title,
        "tails": by_tail,
    }


def build_link_index_from_search(
    entries: List[dict],
    resource_ids: Optional[Dict[str, str]] = None,
) -> dict:
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
        "resourceIds": resource_ids or {},
        "suffixes": _build_suffix_index(by_path),
        "titles": by_title,
        "tails": by_tail,
    }


def _normalize_path(href: str) -> Optional[str]:
    if not href:
        return None
    path = href.split("#")[0].split("?")[0]
    if re.match(r"^https?://", path, re.I):
        parsed = urlparse(path)
        if "help.splunk.com" not in (parsed.netloc or "").lower():
            return None
        path = parsed.path
    if path.startswith("/en/"):
        return path[4:].strip("/")
    if path.startswith("en/"):
        return path[3:].strip("/")
    if path.startswith("/"):
        p = path[1:].strip("/")
        if p.startswith("en/"):
            return p[4:]
        return p
    return None


def _merge_class(a, class_name: str) -> list:
    existing = a.get("class", [])
    if isinstance(existing, str):
        existing = existing.split()
    elif not existing:
        existing = []
    if class_name not in existing:
        existing.append(class_name)
    return existing


def _strip_class(a, class_name: str) -> list:
    existing = a.get("class", [])
    if isinstance(existing, str):
        existing = [c for c in existing.split() if c != class_name]
    else:
        existing = [c for c in (existing or []) if c != class_name]
    return existing


def _path_candidates(path: str) -> list:
    out = {path.strip("/")}
    if path.endswith(".dita"):
        out.add(path[:-5].strip("/"))
    parts = path.strip("/").split("/")
    for i, part in enumerate(parts):
        if _VERSION_RE.match(part):
            out.add("/".join(parts[:i] + parts[i + 1 :]))
    return [p for p in out if p]


def _lookup_path(paths: dict, norm: str) -> Optional[str]:
    for candidate in _path_candidates(norm):
        if candidate in paths:
            return paths[candidate]
        if f"en/{candidate}" in paths:
            return paths[f"en/{candidate}"]
    return None


def _lookup_path_fuzzy(
    paths: dict,
    suffixes: dict,
    norm: str,
) -> Optional[str]:
    tid = _lookup_path(paths, norm)
    if tid:
        return tid

    link_ver = _version_from_path(norm)
    parts = norm.strip("/").split("/")
    best_tid: Optional[str] = None
    best_score = -1

    for i in range(1, len(parts)):
        suf = "/".join(parts[i:])
        if len(suf) < _MIN_SUFFIX_LEN:
            continue
        candidate = suffixes.get(suf)
        if not candidate:
            continue
        score = len(suf)
        if link_ver:
            for indexed_path, indexed_tid in paths.items():
                if indexed_tid == candidate and indexed_path.endswith(suf):
                    if _version_from_path(indexed_path) == link_ver:
                        score += 1000
                    break
        if score > best_score:
            best_score = score
            best_tid = candidate
    return best_tid


def _slugify_label(text: str) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def _parse_version_tuple(ver: str) -> tuple:
    parts = []
    for part in (ver or "").split("."):
        if part.isdigit():
            parts.append(int(part))
    return tuple(parts)


def _tail_from_anchor_token(anchor: str) -> Optional[str]:
    anchor = (anchor or "").strip().lstrip("#")
    if not anchor:
        return None
    if "--en__" in anchor:
        tail = anchor.rsplit("--en__", 1)[-1]
        return _slugify_label(tail.replace("_", " "))
    return None


def _build_tail_candidates(paths: dict) -> Dict[str, list]:
    out: Dict[str, list] = {}
    for path, tid in paths.items():
        if path.startswith("en/"):
            continue
        tail = path.split("/")[-1]
        if tail:
            out.setdefault(tail, []).append((path, tid))
    return out


def _lookup_by_tail_versioned(
    tail_candidates: dict,
    tail: str,
    context_path: str = "",
) -> Optional[str]:
    tail = (tail or "").strip().strip("/")
    if not tail:
        return None

    candidates = tail_candidates.get(tail, [])
    if not candidates:
        return None

    ctx_ver = _version_from_path(context_path)
    ctx_parts = (context_path or "").strip("/").split("/")
    ctx_product = ctx_parts[0] if ctx_parts else ""

    def score(path: str) -> tuple:
        ver = _version_from_path(path)
        ver_tuple = _parse_version_tuple(ver or "")
        product_match = 1 if ctx_product and path.startswith(ctx_product) else 0
        cim_boost = 0
        if ctx_product == "splunk-enterprise" and "common-information-model" in (context_path or ""):
            if "common-information-model" in path:
                cim_boost = 1
        ver_match = 1 if ctx_ver and ver == ctx_ver else 0
        return (ver_match, product_match, cim_boost, ver_tuple, len(path))

    path, tid = max(candidates, key=lambda item: score(item[0]))
    return tid


def _lookup_by_label(
    link_index: dict,
    label: str,
    context_path: str = "",
    tail_candidates: Optional[dict] = None,
) -> Optional[str]:
    label = (label or "").strip()
    if not label:
        return None
    paths = link_index.get("paths", {})
    if tail_candidates is None:
        tail_candidates = _build_tail_candidates(paths)
    slug = _slugify_label(label)
    if slug:
        tid = _lookup_by_tail_versioned(tail_candidates, slug, context_path)
        if tid:
            return tid
    lower = label.lower()
    titles = link_index.get("titles", {})
    if lower in titles:
        title_tid = titles[lower]
        for candidates in tail_candidates.values():
            for path, tid in candidates:
                if tid == title_tid:
                    tail = path.split("/")[-1]
                    versioned = _lookup_by_tail_versioned(
                        tail_candidates, tail, context_path,
                    )
                    return versioned or title_tid
        return title_tid
    return None


def _anchor_in_document(soup: BeautifulSoup, anchor_id: str) -> bool:
    if not anchor_id:
        return False
    anchor_id = anchor_id.lstrip("#")
    if soup.find(id=anchor_id):
        return True
    return bool(soup.find(attrs={"id": anchor_id}))


def _resolve_topic_id(
    paths: dict,
    suffixes: dict,
    rids: dict,
    href: str,
    anchor: str = "",
) -> tuple[Optional[str], Optional[str]]:
    """Return (topic_id, anchor_local_id)."""
    anchor_id = anchor.lstrip("#") if anchor else ""

    if "resourceId=" in href or "resource_id=" in href:
        parsed = urlparse(href)
        qs = parse_qs(parsed.query)
        rid = (qs.get("resourceId") or qs.get("resource_id") or [None])[0]
        if rid and rid in rids:
            return rids[rid], anchor_id or None

    norm = _normalize_path(href)
    if norm:
        tid = _lookup_path_fuzzy(paths, suffixes, norm)
        if tid:
            return tid, anchor_id or None
    return None, anchor_id or None


def rewrite_topic_html(
    html: str,
    link_index: dict,
    current_path: str,
    tail_candidates: Optional[dict] = None,
) -> str:
    soup = BeautifulSoup(html, "html.parser")
    paths = link_index.get("paths", {})
    suffixes = link_index.get("suffixes", {})
    rids = link_index.get("resourceIds", {})
    if tail_candidates is None:
        tail_candidates = _build_tail_candidates(paths)

    for a in soup.find_all("a"):
        href = a.get("href", "")
        stored_anchor = (a.get("data-anchor") or "").strip()
        offline_href = (a.get("data-offline-href") or "").strip()
        if offline_href and (not href or href == "#"):
            href = offline_href

        anchor = ""
        if "#" in href:
            href, anchor = href.split("#", 1)
            anchor = "#" + anchor
        elif stored_anchor:
            anchor = "#" + stored_anchor.lstrip("#")

        tid, anchor_id = _resolve_topic_id(paths, suffixes, rids, href, anchor)

        if not tid and stored_anchor:
            hint_tail = _tail_from_anchor_token(stored_anchor)
            if hint_tail:
                tid = _lookup_by_tail_versioned(tail_candidates, hint_tail, current_path)

        if tid:
            a["href"] = "#"
            a["data-topic"] = tid
            if anchor_id:
                a["data-anchor"] = anchor_id
            a["class"] = _merge_class(a, "offline-link")
            if a.has_attr("data-unresolved"):
                del a["data-unresolved"]
            a["class"] = _strip_class(a, "offline-unresolved")
            if a.has_attr("data-anchor-local"):
                del a["data-anchor-local"]
            continue

        anchor_id = (anchor_id or stored_anchor or "").lstrip("#")
        if anchor_id and _anchor_in_document(soup, anchor_id):
            a["href"] = "#"
            a["data-anchor-local"] = anchor_id
            if a.has_attr("data-unresolved"):
                del a["data-unresolved"]
            if a.has_attr("data-anchor"):
                del a["data-anchor"]
            a["class"] = _strip_class(a, "offline-unresolved")
            continue

        label_tid = _lookup_by_label(
            link_index, a.get_text(" ", strip=True), current_path, tail_candidates,
        )
        if label_tid:
            a["href"] = "#"
            a["data-topic"] = label_tid
            a["class"] = _merge_class(a, "offline-link")
            if a.has_attr("data-unresolved"):
                del a["data-unresolved"]
            a["class"] = _strip_class(a, "offline-unresolved")
            continue

        norm = _normalize_path(href)
        if norm is not None:
            a["href"] = "#"
            a["data-unresolved"] = "1"
            a["class"] = _merge_class(a, "offline-unresolved")
            if anchor_id:
                a["data-anchor"] = anchor_id
            continue

        if href.startswith("#"):
            a["data-anchor-local"] = href.lstrip("#")
            continue

        if re.match(r"^https?://", href, re.I):
            parsed = urlparse(href.split("#")[0])
            if "help.splunk.com" in (parsed.netloc or "").lower():
                tid2, anchor_id2 = _resolve_topic_id(
                    paths, suffixes, rids, href, anchor,
                )
                if tid2:
                    a["href"] = "#"
                    a["data-topic"] = tid2
                    if anchor_id2:
                        a["data-anchor"] = anchor_id2
                    a["class"] = _merge_class(a, "offline-link")
                    continue
            a["class"] = _merge_class(a, "offline-external")
            a["title"] = "Linking externally, won't work in airgapped environment"
            continue

    return str(soup)
