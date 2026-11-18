"""Helpers for the signed Tauri update feed assembled by release.yml."""

from __future__ import annotations

from typing import Any


def platform_entry(
    target: str,
    *,
    url: str,
    signature: str,
    tauri_config: dict[str, Any],
) -> dict[str, str]:
    """Build one feed entry, carrying the configured macOS minimum only there."""
    entry = {"url": url, "signature": signature}
    if target == "darwin-aarch64":
        minimum = tauri_config["bundle"]["macOS"]["minimumSystemVersion"]
        if not isinstance(minimum, str) or not minimum:
            raise ValueError("tauri.conf.json has no macOS minimumSystemVersion")
        entry["min_os"] = minimum
    return entry
