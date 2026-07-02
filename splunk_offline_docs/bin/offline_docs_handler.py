#!/usr/bin/env python3
"""Splunk REST handler for Offline Docs configuration and updates."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, unquote

BIN_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BIN_DIR))

import offline_docs_service as svc  # noqa: E402

try:
    from splunk.persistconn.application import PersistentServerConnectionApplication
except ImportError:
    PersistentServerConnectionApplication = object  # type: ignore


def parse_in_string(in_string) -> dict:
    """Parse Splunk persistent REST request string without splunk.rest."""
    if not in_string:
        return {}
    if isinstance(in_string, bytes):
        in_string = in_string.decode("utf-8", errors="replace")
    parsed = parse_qs(in_string, keep_blank_values=True)
    result = {}
    for key, values in parsed.items():
        result[key] = values[-1] if len(values) == 1 else values
    if "path" in result and isinstance(result["path"], str):
        result["path"] = unquote(result["path"])
    return result


def _json_response(payload: dict, status: int = 200) -> dict:
    return {
        "payload": json.dumps(payload),
        "status": status,
        "headers": {"Content-Type": "application/json"},
    }


def _parse_body(in_dict: dict) -> dict:
    body = in_dict.get("payload") or ""
    if not body:
        return {}
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return {}


def _member_from_path(path: str) -> str:
    path = (path or "").rstrip("/")
    if not path:
        return "status"
    return path.split("/")[-1]


class OfflineDocsHandler(PersistentServerConnectionApplication):
    def __init__(self, command_line=None, command_arg=None):
        PersistentServerConnectionApplication.__init__(self)

    def handle(self, in_string):
        try:
            in_dict = parse_in_string(in_string)
            method = (in_dict.get("method") or "GET").upper()
            member = _member_from_path(in_dict.get("path", ""))
            query = in_dict.get("query", {}) or {}
            body = _parse_body(in_dict)

            if member in ("status", "offline_docs"):
                return _json_response(svc.get_status())

            if member == "check":
                if method == "GET":
                    return _json_response(svc.read_json(
                        svc.state_path("check_report.json"), {},
                    ) or {"message": "No check has been run yet"})
                report = svc.run_check(save=True)
                return _json_response(report)

            if member == "update":
                if method != "POST":
                    return _json_response({"error": "POST required"}, 405)
                mode = body.get("mode") or query.get("mode") or "incremental"
                result = svc.start_update(mode=mode)
                code = 200 if result.get("ok") else 409
                return _json_response(result, code)

            if member == "settings":
                if method == "GET":
                    return _json_response(svc.load_settings())
                if method != "POST":
                    return _json_response({"error": "POST required"}, 405)
                saved = svc.save_settings(body)
                return _json_response({"ok": True, "settings": saved})

            return _json_response({"error": f"Unknown endpoint: {member}"}, 404)
        except Exception as exc:
            return _json_response({"error": str(exc)}, 500)


if __name__ == "__main__":
    print(json.dumps(svc.get_status(), indent=2))
