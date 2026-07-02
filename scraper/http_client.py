"""HTTP client for help.splunk.com with polite rate limiting."""
from __future__ import annotations

import time
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE = "https://help.splunk.com"
USER_AGENT = "Splunk4Offlinedocs/1.0 (+internal offline docs build)"


class HelpClient:
    def __init__(self, rate_limit: float = 1.0):
        self.rate_limit = rate_limit
        self._last = 0.0
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en"})
        retry = Retry(total=4, backoff_factor=0.6, status_forcelist=[429, 500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)

    def _throttle(self):
        elapsed = time.time() - self._last
        wait = self.rate_limit - elapsed
        if wait > 0:
            time.sleep(wait)
        self._last = time.time()

    def get(self, path: str) -> str:
        self._throttle()
        url = path if path.startswith("http") else f"{BASE}{path}"
        r = self.session.get(url, timeout=60)
        r.raise_for_status()
        return r.text

    def get_bytes(self, url: str) -> bytes:
        self._throttle()
        if url.startswith("/"):
            url = BASE + url
        r = self.session.get(url, timeout=60)
        r.raise_for_status()
        return r.content
