#!/usr/bin/env python3
"""Daily scheduled check for help.splunk.com documentation updates."""
from __future__ import annotations

import sys
from pathlib import Path

BIN_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BIN_DIR))

import offline_docs_service as svc  # noqa: E402


def main() -> int:
    settings = svc.load_settings()
    if not settings.get("daily_check_enabled", False):
        print("Daily check disabled in settings")
        return 0
    report = svc.run_check(save=True)
    if report.get("updates_available"):
        print("Updates available:")
        for product in report.get("products", []):
            if product.get("missing_count", 0) > 0 or product.get("new_versions"):
                print(
                    f"  - {product.get('title')}: "
                    f"{product.get('missing_count', 0)} missing, "
                    f"new versions={product.get('new_versions')}"
                )
        return 0
    print("No documentation updates detected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
