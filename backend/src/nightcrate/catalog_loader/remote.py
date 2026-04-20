"""GitHub-backed fetcher for the OpenNGC catalog.

Two entry points:

- :func:`fetch_latest_release` — queries the GitHub REST API for the
  latest OpenNGC release tag. Does not touch the filesystem.
- :func:`download_openngc` — downloads ``NGC.csv`` and ``addendum.csv``
  from a given release tag into ``<catalogs_root>/openngc/`` atomically:
  bytes land in a ``.download/`` temp dir, sha256 is computed, and only
  after both files are on disk are they renamed into place. A
  ``version.json`` is written last so partial states never get mistaken
  for a complete install.

Both functions wrap every HTTP call in a local retry loop on top of the
shared ``services/http_client.get()`` (which already retries once per
attempt on transient failures). Default is 3 outer attempts → up to 6
underlying HTTP requests per URL in the worst case.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from nightcrate.catalog_loader._common import retry_with_backoff
from nightcrate.catalog_loader.registry import (
    OPENNGC_CITATION,
    OPENNGC_LICENSE,
    OPENNGC_SOURCE_URL,
)
from nightcrate.services import http_client

logger = logging.getLogger("nightcrate.catalog_loader.remote")

GITHUB_RELEASES_URL = "https://api.github.com/repos/mattiaverga/OpenNGC/releases/latest"
RAW_BASE = "https://raw.githubusercontent.com/mattiaverga/OpenNGC"
DOWNLOAD_FILES: tuple[str, ...] = ("NGC.csv", "addendum.csv")


@dataclass(frozen=True, slots=True)
class RemoteReleaseInfo:
    tag_name: str
    published_at: str | None
    release_url: str


@dataclass(frozen=True, slots=True)
class DownloadedFile:
    name: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class DownloadReport:
    tag: str
    files: list[DownloadedFile]
    version_json_path: Path


async def fetch_latest_release() -> RemoteReleaseInfo:
    """Query the GitHub API for the latest tagged OpenNGC release."""

    async def _call():
        response = await http_client.get(
            GITHUB_RELEASES_URL,
            label="openngc_latest_release",
            follow_redirects=True,
            headers={"Accept": "application/vnd.github+json"},
        )
        if response.status_code >= 400:
            raise RuntimeError(f"GitHub API returned {response.status_code} for latest release")
        data = response.json()
        tag = data.get("tag_name")
        if not tag:
            raise RuntimeError("GitHub API response missing tag_name")
        return RemoteReleaseInfo(
            tag_name=str(tag),
            published_at=data.get("published_at"),
            release_url=data.get("html_url") or f"{OPENNGC_SOURCE_URL}/releases/tag/{tag}",
        )

    return await retry_with_backoff(_call, logger=logger, label="fetch_latest_release")


async def _download_file(url: str, dest: Path, *, label: str) -> DownloadedFile:
    async def _call():
        response = await http_client.get(url, label=label, follow_redirects=True, timeout=60.0)
        if response.status_code >= 400:
            raise RuntimeError(f"download {label} failed with status {response.status_code}")
        content = response.content
        if not content:
            raise RuntimeError(f"download {label} returned empty body")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
        digest = hashlib.sha256(content).hexdigest()
        return DownloadedFile(name=dest.name, size_bytes=len(content), sha256=digest)

    return await retry_with_backoff(_call, logger=logger, label=f"download:{label}")


def _write_version_json(
    catalogs_root: Path,
    release: RemoteReleaseInfo,
    downloaded: list[DownloadedFile],
) -> Path:
    openngc_dir = catalogs_root / "openngc"
    openngc_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "source_id": "openngc",
        "version": release.tag_name,
        "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source_url": OPENNGC_SOURCE_URL,
        "release_url": release.release_url,
        "license": OPENNGC_LICENSE,
        "citation": OPENNGC_CITATION,
        "files": {f.name: {"sha256": f.sha256, "size_bytes": f.size_bytes} for f in downloaded},
    }
    path = openngc_dir / "version.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


async def download_openngc(
    release: RemoteReleaseInfo,
    catalogs_root: Path,
) -> DownloadReport:
    """Download both OpenNGC files for *release* into *catalogs_root*.

    Atomicity model: ``version.json`` is the commit marker. The flow is:

    1. Download all files into ``<catalogs_root>/openngc/.download/``
       (in parallel). If any download fails, the tmp dir is cleaned up
       and the prior install is left intact.
    2. Delete the existing ``version.json`` — from this point until step
       4 completes the install is "in progress" and the registry will
       report "Not loaded".
    3. Rename the downloaded CSVs over the canonical paths. Each rename
       is atomic per-file; if a crash happens between renames, the
       install still shows "Not loaded" because there's no version.json
       yet, which prompts the user to re-fetch.
    4. Write the new ``version.json`` last as the commit.

    Partial failure never produces a stale version-vs-data mismatch: if
    version.json is present, it correctly describes the CSVs on disk.
    """
    openngc_dir = catalogs_root / "openngc"
    tmp_dir = openngc_dir / ".download"
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Download both files in parallel. They write to distinct tmp paths
        # and don't share state, so gather is safe. Halves wall-clock time
        # on the NGC.csv + addendum.csv pair (~4 MB + ~20 KB).
        tasks = [
            _download_file(
                f"{RAW_BASE}/{release.tag_name}/database_files/{filename}",
                tmp_dir / filename,
                label=f"openngc/{release.tag_name}/{filename}",
            )
            for filename in DOWNLOAD_FILES
        ]
        downloaded = list(await asyncio.gather(*tasks))

        # Invalidate the commit marker BEFORE the CSV renames. If we crash
        # anywhere between here and the _write_version_json call below, the
        # registry will read no version.json → report "Not loaded" → user
        # re-fetches. Better than a stale-version / new-data mismatch.
        version_json_path = openngc_dir / "version.json"
        version_json_path.unlink(missing_ok=True)

        # Per-file atomic rename into place.
        for f in downloaded:
            src = tmp_dir / f.name
            dest = openngc_dir / f.name
            src.replace(dest)

        version_path = _write_version_json(catalogs_root, release, downloaded)
        logger.info(
            "[catalog_loader.remote] downloaded OpenNGC %s (%d files, %d bytes total)",
            release.tag_name,
            len(downloaded),
            sum(f.size_bytes for f in downloaded),
        )
        return DownloadReport(
            tag=release.tag_name, files=downloaded, version_json_path=version_path
        )
    finally:
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)
