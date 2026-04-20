"""GitHub fetcher for the 50 MGC catalog.

50 MGC is distributed from https://github.com/davidohlson/50MGC as a
FITS binary table at ``data/catalog.fits`` (the ``catalog_short.fits``
variant in the same dir omits the distance columns we augment on).
Fetching from GitHub rather than VizieR is more reliable — CDS's VizieR
endpoint has been intermittently flaky — and GitHub's raw-content URLs
are CDN-backed. The default branch is ``master`` (not ``main``).

Uses the same atomic download pattern as ``catalog_loader/remote.py``:
write into ``<dest_dir>/.download/``, compute sha256, invalidate the
sentinel, atomic rename, then write the sentinel as the commit marker.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from nightcrate.catalog_loader._common import retry_with_backoff
from nightcrate.services import http_client

logger = logging.getLogger("nightcrate.catalog_loader.mgc50_fetch")

MGC50_RAW_URL = "https://raw.githubusercontent.com/davidohlson/50MGC/master/data/catalog.fits"
MGC50_OUTPUT_FILENAME = "catalog.fits"
MGC50_REPO_URL = "https://github.com/davidohlson/50MGC"
MGC50_CITATION = (
    "Ohlson, D. et al. 2024, AJ, 167, 31 — The 50 Mpc Galaxy Catalog. "
    "Retrieved from the author's GitHub mirror."
)
_DOWNLOAD_TIMEOUT_S = 120.0
_MIN_BODY_BYTES = 1024  # sanity check — catalog.fits is ~4.4 MB

_VERSION_JSON_ERRS: tuple[type[BaseException], ...] = (
    json.JSONDecodeError,
    OSError,
    ValueError,
)


@dataclass(frozen=True, slots=True)
class Mgc50FetchResult:
    output_path: Path
    sha256: str
    size_bytes: int
    fetched_at: str


def _write_version_json(dest_dir: Path, result: Mgc50FetchResult) -> Path:
    """Persist the fetch metadata as ``<dest_dir>/version.json``."""
    payload = {
        "source_id": "github_50mgc",
        "fetched_at": result.fetched_at,
        "source_url": MGC50_RAW_URL,
        "repository_url": MGC50_REPO_URL,
        "sha256": result.sha256,
        "size_bytes": result.size_bytes,
        "citation": MGC50_CITATION,
        "license": "See upstream repository",
    }
    path = dest_dir / "version.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def read_installed_fetch(catalogs_root: Path) -> dict:
    """Return the parsed ``github/50mgc/version.json`` or an empty dict."""
    path = catalogs_root / "github" / "50mgc" / "version.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except _VERSION_JSON_ERRS:
        return {}


async def fetch_50mgc_from_github(catalogs_root: Path) -> Mgc50FetchResult:
    """Download ``catalog.fits`` atomically into ``<catalogs_root>/github/50mgc/``.

    Flow:
      1. GET the raw file into a ``.download/`` tmp dir.
      2. Verify size > ``_MIN_BODY_BYTES`` (guards against truncated
         responses and HTML error pages).
      3. Invalidate ``version.json`` so any crash before step 5 leaves
         the install visibly "in progress".
      4. Atomic rename into place.
      5. Write ``version.json`` as the commit marker.
    """
    dest_dir = catalogs_root / "github" / "50mgc"
    tmp_dir = dest_dir / ".download"
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    tmp_path = tmp_dir / MGC50_OUTPUT_FILENAME
    final_path = dest_dir / MGC50_OUTPUT_FILENAME

    async def _download():
        response = await http_client.get(
            MGC50_RAW_URL,
            label="50mgc_github",
            follow_redirects=True,
            timeout=_DOWNLOAD_TIMEOUT_S,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"GitHub returned {response.status_code} for 50 MGC")
        content = response.content
        if not content or len(content) < _MIN_BODY_BYTES:
            raise RuntimeError(
                f"50 MGC download body too small ({len(content) if content else 0} bytes)"
            )
        tmp_path.write_bytes(content)
        return content

    try:
        content = await retry_with_backoff(_download, label="fetch:50mgc", logger=logger)

        version_json = dest_dir / "version.json"
        version_json.unlink(missing_ok=True)

        tmp_path.replace(final_path)

        result = Mgc50FetchResult(
            output_path=final_path,
            sha256=hashlib.sha256(content).hexdigest(),
            size_bytes=len(content),
            fetched_at=datetime.now(UTC).isoformat(timespec="seconds"),
        )
        _write_version_json(dest_dir, result)
        logger.info(
            "[50mgc_github] downloaded %d bytes → %s",
            result.size_bytes,
            final_path,
        )
        return result
    finally:
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)
