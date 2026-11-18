"""Network operations for application update checks."""

from __future__ import annotations

import platform
from typing import Any
from urllib.parse import urlparse

import httpx

from nightcrate.core.updates_state import LatestApp
from nightcrate.services import http_client
from nightcrate.services.update_notices import parse_notes

MANIFEST_URL = "https://github.com/fbaptiste/nightcrate/releases/latest/download/latest.json"
RELEASES_API_URL = "https://api.github.com/repos/fbaptiste/nightcrate/releases/latest"
REPOSITORY_URL = "https://github.com/fbaptiste/nightcrate"

_manifest_url = MANIFEST_URL
_releases_url = RELEASES_API_URL


class UpdateCheckError(RuntimeError):
    pass


def set_test_urls(manifest_url: str | None, releases_url: str | None) -> None:
    """Set compile-time-test endpoints, accepting insecure loopback only."""
    global _manifest_url, _releases_url
    for value in (manifest_url, releases_url):
        if value is None:
            continue
        parsed = urlparse(value)
        if parsed.scheme not in {"https", "http"} or (
            parsed.scheme == "http" and parsed.hostname != "127.0.0.1"
        ):
            raise ValueError("test update URLs must use HTTPS or HTTP on 127.0.0.1")
    _manifest_url = manifest_url or MANIFEST_URL
    _releases_url = releases_url or RELEASES_API_URL


def platform_key() -> str | None:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "darwin" and machine in {"arm64", "aarch64"}:
        return "darwin-aarch64"
    if system == "windows" and machine in {"amd64", "x86_64"}:
        return "windows-x86_64"
    if system == "linux" and machine in {"amd64", "x86_64"}:
        return "linux-x86_64"
    return None


async def _get_json(url: str, label: str) -> tuple[int, Any]:
    try:
        response = await http_client.get(
            url,
            label=label,
            follow_redirects=True,
            headers={"Accept": "application/vnd.github+json"},
        )
        if response.status_code == 404:
            return 404, None
        response.raise_for_status()
        return response.status_code, response.json()
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        raise UpdateCheckError("couldn't reach GitHub") from exc


async def fetch_latest_app() -> LatestApp | None:
    manifest_status, manifest = await _get_json(_manifest_url, "nightcrate_update_manifest")
    if manifest_status == 404:
        return None
    release_status, release = await _get_json(_releases_url, "nightcrate_latest_release")
    if release_status == 404:
        return None
    if not isinstance(manifest, dict) or not isinstance(release, dict):
        raise UpdateCheckError("GitHub returned invalid update information")
    version = manifest.get("version")
    platforms = manifest.get("platforms")
    release_url = release.get("html_url")
    if not isinstance(version, str) or not isinstance(platforms, dict):
        raise UpdateCheckError("GitHub returned invalid update information")
    tag = release.get("tag_name")
    release_version = tag[1:] if isinstance(tag, str) and tag.startswith("v") else tag
    if not isinstance(release_version, str):
        release_version = None
    if not isinstance(release_url, str):
        release_url = f"{REPOSITORY_URL}/releases/tag/v{version}"
    min_os = {
        key: entry["min_os"]
        for key, entry in platforms.items()
        if isinstance(key, str) and isinstance(entry, dict) and isinstance(entry.get("min_os"), str)
    }
    return LatestApp(
        version=version,
        release_version=release_version,
        published_at=release.get("published_at"),
        notes=parse_notes(str(release.get("body") or "")),
        release_url=release_url,
        platforms=list(platforms),
        min_os=min_os,
    )
