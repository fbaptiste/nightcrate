"""VizieR TSV fetcher.

Parallels ``catalog_loader/remote.py`` (the OpenNGC GitHub fetcher), but
targets VizieR's ``asu-tsv`` endpoint. Each logical source has a
:class:`VizierFetchSpec` with the catalog id, output filename, optional
column filter and query constraints. Downloads land atomically in
``APP_DIR/catalogs/vizier/`` with an accompanying ``version.json`` as the
commit marker (same pattern as v0.14.0 — if the download is interrupted
mid-rename, version.json is absent and the install reports as "Not
loaded" so the user re-fetches).
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from nightcrate.catalog_loader._common import retry_with_backoff
from nightcrate.services import http_client

logger = logging.getLogger("nightcrate.catalog_loader.vizier")

VIZIER_PATH = "/viz-bin/asu-tsv"
# Mirror order: primary (Strasbourg) → India → South Africa. Used as a
# fallback when the primary host fails after `retry_with_backoff` gives up.
VIZIER_HOSTS: tuple[str, ...] = (
    "vizier.cds.unistra.fr",
    "vizier.iucaa.in",
    "vizieridia.saao.ac.za",
)
VIZIER_BASE = f"https://{VIZIER_HOSTS[0]}{VIZIER_PATH}"

# Smallest plausible TSV body. Anything shorter is a truncated / error
# response masquerading as HTTP 200.
_MIN_BODY_BYTES = 1024

CDS_CITATION = (
    "This research has made use of the VizieR catalogue access tool, "
    "CDS, Strasbourg, France (DOI: 10.26093/cds/vizier)."
)

# Tuple constant for narrow except clauses — sidesteps the py314 ruff-format
# bug documented in CLAUDE.md "Gotchas" where `except (A, B):` gets its
# parens stripped into the Python 2 `except A, B:` form.
_VERSION_JSON_ERRS: tuple[type[BaseException], ...] = (json.JSONDecodeError, OSError)
# VizieR downloads can take a while over a slow CDS connection (Barnard
# VII/220A can stretch past a minute). Give them a generous timeout.
_DOWNLOAD_TIMEOUT_S = 180.0


@dataclass(frozen=True, slots=True)
class VizierFetchSpec:
    source_id: str  # e.g. 'vizier_sharpless'
    catalog_id: str  # e.g. 'VII/20/catalog'
    output_filename: str  # e.g. 'sharpless_VII_20.tsv'
    display_name: str
    citation: str
    # Optional ``-out=`` column projection (comma-separated column names).
    column_filter: str | None = None
    # Optional additional constraint params (e.g. {'modbest': '=!null'}).
    additional_params: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class VizierFetchResult:
    source_id: str
    output_path: Path
    sha256: str
    size_bytes: int
    fetched_at: str


def _build_url(spec: VizierFetchSpec, host: str = VIZIER_HOSTS[0]) -> str:
    """Compose the ``asu-tsv`` URL for *spec* at the given VizieR *host*.

    VizieR accepts repeated query parameters — a single ``-source=`` plus
    any number of ``-out=`` / constraint params. We build the URL by hand
    (rather than via ``httpx``'s ``params`` kwarg) because the repeated
    ``=`` style for constraints (``-modbest==!null``) doesn't round-trip
    cleanly through URL-encoding libraries.
    """
    parts = [f"-source={spec.catalog_id}"]
    if spec.column_filter:
        parts.append(f"-out={spec.column_filter}")
    else:
        parts.append("-out.all")
    parts.append("-out.max=unlimited")
    for key, value in spec.additional_params.items():
        parts.append(f"{key}={value}")
    return f"https://{host}{VIZIER_PATH}?{'&'.join(parts)}"


def _verify_tsv_shape(path: Path) -> None:
    """Smoke-check that the downloaded file looks like a VizieR TSV.

    We don't parse fully here; the parser does that. This just confirms we
    have a header row after the metadata so we fail fast on obvious wire
    problems (HTML error pages, truncated responses).
    """
    with path.open("r", encoding="utf-8", newline="") as fh:
        saw_header = False
        for line in fh:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            # The first non-comment, non-empty line is the header row.
            if "\t" not in line:
                raise ValueError(f"{path}: expected tab-separated header, got {line[:80]!r}")
            saw_header = True
            break
        if not saw_header:
            raise ValueError(f"{path}: no tab-separated header found")


def _write_version_json(
    vizier_dir: Path,
    spec: VizierFetchSpec,
    result: VizierFetchResult,
) -> Path:
    """Merge per-source metadata into ``vizier/version.json``.

    Unlike OpenNGC (which has a single fetch per version.json), VizieR
    version.json holds one ``files`` entry per source so each fetch
    records its own sha256 + fetch date.
    """
    path = vizier_dir / "version.json"
    payload: dict = {"category": "vizier", "files": {}}
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload.setdefault("files", {})
        except _VERSION_JSON_ERRS:
            payload = {"category": "vizier", "files": {}}

    payload["files"][spec.output_filename] = {
        "source_id": spec.source_id,
        "catalog_id": spec.catalog_id,
        "source_url": _build_url(spec),
        "fetch_date": result.fetched_at,
        "sha256": result.sha256,
        "size_bytes": result.size_bytes,
        "citation": spec.citation,
        "license": "CDS public — see attribution panel",
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


async def fetch_vizier_catalog(
    spec: VizierFetchSpec,
    catalogs_root: Path,
) -> VizierFetchResult:
    """Download the TSV for *spec* atomically into *catalogs_root*/vizier.

    Flow:
      1. GET the TSV to ``<vizier>/.download/<output_filename>``.
      2. Smoke-check the shape.
      3. Invalidate the entry in ``vizier/version.json`` so a crash mid-
         rename leaves an "install in progress" state (similar to OpenNGC's
         version.json commit marker).
      4. Atomic rename into place.
      5. Write the new version.json entry as the commit.
    """
    vizier_dir = catalogs_root / "vizier"
    tmp_dir = vizier_dir / ".download"
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    tmp_path = tmp_dir / spec.output_filename
    final_path = vizier_dir / spec.output_filename

    def _make_download_for_host(host: str):
        async def _download() -> bytes:
            response = await http_client.get(
                _build_url(spec, host),
                label=f"vizier:{spec.source_id}@{host}",
                follow_redirects=True,
                timeout=_DOWNLOAD_TIMEOUT_S,
            )
            if response.status_code >= 400:
                raise RuntimeError(
                    f"VizieR {host} returned {response.status_code} for {spec.source_id}"
                )
            content = response.content
            if not content:
                raise RuntimeError(f"VizieR {host} returned empty body for {spec.source_id}")
            if len(content) < _MIN_BODY_BYTES:
                raise RuntimeError(
                    f"VizieR {host} body suspiciously short "
                    f"({len(content)} bytes) for {spec.source_id}"
                )
            tmp_path.write_bytes(content)
            return content

        return _download

    try:
        # Try each VizieR host in order. ``retry_with_backoff`` handles the
        # per-host transient failures (3 attempts with jittered backoff); we
        # fall through to the next host only after that exhausts.
        last_exc: BaseException | None = None
        content: bytes | None = None
        for host in VIZIER_HOSTS:
            try:
                content = await retry_with_backoff(
                    _make_download_for_host(host),
                    label=f"fetch:{spec.source_id}",
                    logger=logger,
                )
                break
            except Exception as exc:  # noqa: BLE001 — rotate to next mirror
                last_exc = exc
                logger.warning(
                    "[vizier] %s: all retries exhausted on %s, trying next mirror",
                    spec.source_id,
                    host,
                )
        if content is None:
            raise RuntimeError(f"All VizieR mirrors failed for {spec.source_id}: {last_exc}")
        _verify_tsv_shape(tmp_path)

        # Invalidate this source's entry in version.json BEFORE renaming — a
        # crash between here and the post-rename write leaves the file
        # untracked so the registry reports "Not loaded" and the user re-fetches.
        version_json = vizier_dir / "version.json"
        if version_json.exists():
            try:
                payload = json.loads(version_json.read_text(encoding="utf-8"))
                payload.get("files", {}).pop(spec.output_filename, None)
                version_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            except _VERSION_JSON_ERRS:
                # Corrupt version.json — drop it entirely and rebuild below.
                version_json.unlink(missing_ok=True)

        tmp_path.replace(final_path)

        result = VizierFetchResult(
            source_id=spec.source_id,
            output_path=final_path,
            sha256=hashlib.sha256(content).hexdigest(),
            size_bytes=len(content),
            fetched_at=datetime.now(UTC).isoformat(timespec="seconds"),
        )
        _write_version_json(vizier_dir, spec, result)

        logger.info(
            "[vizier] %s: downloaded %d bytes → %s",
            spec.source_id,
            result.size_bytes,
            final_path,
        )
        return result
    finally:
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)


def read_installed_version(catalogs_root: Path) -> dict[str, dict]:
    """Return the ``files`` map from ``vizier/version.json`` or empty."""
    path = catalogs_root / "vizier" / "version.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except _VERSION_JSON_ERRS:
        return {}
    return payload.get("files", {})
