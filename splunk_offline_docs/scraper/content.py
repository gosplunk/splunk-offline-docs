"""Fetch and extract DITA HTML topic content from help.splunk.com fragments."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from bs4 import BeautifulSoup

from .http_client import HelpClient

FRAGMENT_PREFIX = "/en/fragments/"


@dataclass
class TopicContent:
    path: str
    topic_id: str
    title: str
    breadcrumbs: List[dict]
    html: str
    resource_ids: List[str]
    mini_toc: List[dict]


def path_to_topic_id(path: str) -> str:
    return hashlib.sha256(path.encode()).hexdigest()[:16]


def _parse_version_options(soup: BeautifulSoup) -> List[Tuple[str, str]]:
    sel = soup.find("select", id="version-select")
    if not sel:
        return []
    opts = []
    for opt in sel.find_all("option"):
        val = opt.get("value", "")
        label = opt.get_text(strip=True)
        if val and label:
            opts.append((label, val))
    return opts


def pick_latest_10x_version(options: List[Tuple[str, str]]) -> Optional[str]:
    best = None
    best_tuple = (-1, -1)
    for label, val in options:
        m = re.match(r"^(\d+)\.(\d+)$", label.strip())
        if not m:
            continue
        major, minor = int(m.group(1)), int(m.group(2))
        if major != 10:
            continue
        if (major, minor) > best_tuple:
            best_tuple = (major, minor)
            best = val
    return best


def rewrite_path_to_version(path: str, version: str) -> str:
    """Replace or skip version segments; version is like '10.4'."""
    segs = path.split("/")
    for i, p in enumerate(segs):
        if re.match(r"^\d+\.\d+$", p):
            segs[i] = version
            return "/".join(segs)
    return path


def is_old_enterprise_version(path: str) -> bool:
    """True if path contains a non-10.x version segment."""
    for seg in path.split("/"):
        m = re.match(r"^(\d+)\.(\d+)$", seg)
        if m and int(m.group(1)) < 10:
            return True
    return False


def extract_meta_resource_ids(soup: BeautifulSoup) -> List[str]:
    ids = []
    for meta in soup.find_all("meta", attrs={"name": "resource-ids"}):
        content = meta.get("content", "")
        ids.extend([x.strip() for x in content.split(",") if x.strip()])
    for meta in soup.find_all("meta", attrs={"name": "cisco_topic_resource_id"}):
        c = meta.get("content", "").strip()
        if c:
            ids.append(c)
    return list(dict.fromkeys(ids))


def _extract_topic_from_soup(soup: BeautifulSoup, path: str) -> Tuple[str, str, List[dict]]:
    crumbs = []
    nav = soup.find("nav", class_="breadcrumbs")
    if nav:
        for a in nav.find_all("a"):
            href = a.get("href", "")
            crumbs.append(
                {"title": a.get_text(strip=True), "path": href.lstrip("/en/")}
            )

    container = soup.select_one(".dita-content-container")
    if not container:
        container = soup.select_one(".content-area")
    body_html = container.decode_contents() if container else ""

    h1 = soup.select_one("h1.topictitle1")
    title = (
        h1.get_text(strip=True)
        if h1
        else (crumbs[-1]["title"] if crumbs else path.split("/")[-1])
    )
    return title, body_html, crumbs


def fetch_topic(client: HelpClient, path: str) -> TopicContent:
    html = client.get(FRAGMENT_PREFIX + path)
    soup = BeautifulSoup(html, "lxml")
    resource_ids = extract_meta_resource_ids(soup)
    title, body_html, crumbs = _extract_topic_from_soup(soup, path)

    # Manual hubs and some branch pages return an empty fragment; use full page.
    if len(body_html.strip()) < 80:
        html = client.get(f"/en/{path}")
        soup = BeautifulSoup(html, "lxml")
        resource_ids = extract_meta_resource_ids(soup) or resource_ids
        full_title, full_body, full_crumbs = _extract_topic_from_soup(soup, path)
        if len(full_body.strip()) > len(body_html.strip()):
            title, body_html, crumbs = full_title, full_body, full_crumbs

    mini = []
    mt = soup.select_one(".mini-toc")
    if mt:
        for a in mt.find_all("a"):
            mini.append(
                {"title": a.get_text(strip=True), "anchor": a.get("href", "")}
            )

    return TopicContent(
        path=path,
        topic_id=path_to_topic_id(path),
        title=title,
        breadcrumbs=crumbs,
        html=body_html,
        resource_ids=resource_ids,
        mini_toc=mini,
    )


def resolve_enterprise_version(client: HelpClient, sample_path: str, cache: dict) -> Optional[str]:
    """Detect latest 10.x version string (e.g. '10.4') once per crawl."""
    if "enterprise_version" in cache:
        return cache["enterprise_version"]
    page = client.get(f"/en/{sample_path}")
    soup = BeautifulSoup(page, "lxml")
    opts = _parse_version_options(soup)
    best = pick_latest_10x_version(opts)
    if best:
        rel = best.lstrip("/en/").strip("/")
        for seg in rel.split("/"):
            if re.match(r"^\d+\.\d+$", seg):
                cache["enterprise_version"] = seg
                return seg
    return None


def normalize_enterprise_path(path: str, version: Optional[str]) -> Optional[str]:
    """Skip 9.x paths; keep explicit 10.x version segments from portal nav."""
    if is_old_enterprise_version(path):
        return None
    return path
