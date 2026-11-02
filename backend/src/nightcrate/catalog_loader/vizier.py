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
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import httpx

from nightcrate.services import http_client
from nightcrate.services.catalog_progress import ProgressCallback, ProgressUpdate

logger = logging.getLogger("nightcrate.catalog_loader.vizier")

VIZIER_PATH = "/viz-bin/asu-tsv"
# Mirror order: Strasbourg (the cited primary) → CfA Harvard → IDIA South
# Africa, each tried once over HTTPS. Checked 2026-11-01 during the CDS
# outage: these two mirrors returned rows identical to each other; Tokyo and
# Beijing serve plain HTTP only; Pune (vizier.iucaa.in) and Moscow time out;
# the old South Africa name vizieridia.saao.ac.za fails HTTPS (certificate).
VIZIER_HOSTS: tuple[str, ...] = (
    "vizier.cds.unistra.fr",
    "vizier.cfa.harvard.edu",
    "vizier.idia.ac.za",
)
VIZIER_BASE = f"https://{VIZIER_HOSTS[0]}{VIZIER_PATH}"
_HOST_NAMES = {
    VIZIER_HOSTS[0]: "CDS Strasbourg",
    VIZIER_HOSTS[1]: "the Harvard mirror",
    VIZIER_HOSTS[2]: "the South Africa mirror",
}
_HOST_SUBJECTS = {
    VIZIER_HOSTS[0]: "Strasbourg",
    VIZIER_HOSTS[1]: "Harvard",
    VIZIER_HOSTS[2]: "South Africa",
}

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
# A host that is down never completes the TCP handshake. Without a separate
# connect limit each attempt waits for the OS (about 75 s on macOS) before the
# next mirror is tried; working mirrors connect in well under a second.
_CONNECT_TIMEOUT_S = 10.0
_clock = time.monotonic


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
    # URL of the mirror that actually served the data.
    source_url: str


class NoVizierSource(RuntimeError):
    """No configured VizieR host returned a usable catalog."""


class _HttpFailure(RuntimeError):
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"HTTP {status_code}")


class _NoData(RuntimeError):
    pass


class _InvalidCatalog(RuntimeError):
    pass


def _emit(on_progress: ProgressCallback | None, progress: ProgressUpdate) -> None:
    if on_progress is not None:
        on_progress(progress)


def _catalog_name(spec: VizierFetchSpec) -> str:
    if "Sharpless" in spec.display_name:
        return "Sharpless"
    if "Barnard" in spec.display_name:
        return "Barnard"
    return spec.display_name


def _failure_reason(exc: BaseException) -> str:
    if isinstance(exc, httpx.TimeoutException):
        return "timed out"
    if isinstance(exc, httpx.ConnectError):
        return "couldn't connect"
    if isinstance(exc, httpx.TransportError):
        return "dropped the connection"
    if isinstance(exc, _HttpFailure):
        return f"returned an error (HTTP {exc.status_code})"
    if isinstance(exc, _NoData):
        return "returned no data"
    if isinstance(exc, _InvalidCatalog):
        return "returned something that isn't the catalog"
    return "failed"


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


def _verify_tsv_shape(path: Path, required_columns: tuple[str, ...] = ()) -> None:
    """Check that the downloaded file has VizieR's ``asu-tsv`` envelope.

    After the ``#`` metadata, VizieR writes a tab-separated header row, a
    units row, a separator row of hyphens with one field per column, then
    data rows. Anything else (an HTML or proxy error page served with
    HTTP 200, a truncated body) raises ``ValueError`` so the next mirror is
    tried instead of replacing a working catalog.
    """
    with path.open("r", encoding="utf-8", newline="") as fh:
        lines = (line.rstrip("\r\n") for line in fh)
        header = next(
            (line for line in lines if line.strip() and not line.strip().startswith("#")),
            None,
        )
        if header is None or "\t" not in header:
            raise ValueError(f"{path}: no tab-separated header row")
        columns = [name.strip() for name in header.split("\t")]
        missing = [name for name in required_columns if name not in columns]
        if missing:
            raise ValueError(f"{path}: header lacks requested columns {missing}")
        if next(lines, None) is None:
            raise ValueError(f"{path}: missing units row after header")
        separator = next(lines, None)
        fields = separator.split("\t") if separator is not None else []
        if len(fields) != len(columns) or not all(
            field.strip() and set(field.strip()) == {"-"} for field in fields
        ):
            raise ValueError(f"{path}: missing hyphen separator row after units")
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                break
            if len(line.split("\t")) == len(columns):
                return
        raise ValueError(f"{path}: no data row matching the header's {len(columns)} columns")


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
        "source_url": result.source_url,
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
    on_progress: ProgressCallback | None = None,
) -> VizierFetchResult:
    """Download the TSV for *spec* atomically into *catalogs_root*/vizier.

    Flow:
      1. GET the TSV to ``<vizier>/.download/<output_filename>`` from the
         first mirror in ``VIZIER_HOSTS`` that answers with a TSV-shaped body.
      2. Invalidate the entry in ``vizier/version.json`` so a crash mid-
         rename leaves an "install in progress" state (similar to OpenNGC's
         version.json commit marker).
      3. Atomic rename into place.
      4. Write the new version.json entry as the commit.

    If every mirror fails, the installed file and its version.json entry are
    left untouched.
    """
    vizier_dir = catalogs_root / "vizier"
    tmp_dir = vizier_dir / ".download"
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    tmp_path = tmp_dir / spec.output_filename
    final_path = vizier_dir / spec.output_filename

    # Columns added with ``-out.add`` must appear in the header, so a generic
    # tabular page cannot pass for this catalog.
    required_columns = tuple(
        name for name in spec.additional_params.get("-out.add", "").split(",") if name
    )

    async def _download(url: str, host: str, attempt_message: str) -> bytes:
        host_name = _HOST_NAMES[host]

        def _http_event(event: http_client.GetEvent) -> None:
            if event.kind == "attempt":
                _emit(on_progress, ProgressUpdate("trying_source", attempt_message))
            elif event.kind == "response" and event.status_code is not None:
                if event.status_code < 400:
                    _emit(
                        on_progress,
                        ProgressUpdate(
                            "downloading",
                            f"Downloading {_catalog_name(spec)} from {host_name}…",
                            bytes_total=event.content_length,
                        ),
                    )
            elif event.kind == "bytes" and event.status_code is not None:
                if event.status_code < 400:
                    _emit(
                        on_progress,
                        ProgressUpdate(
                            "downloading",
                            f"Downloading {_catalog_name(spec)} from {host_name}…",
                            bytes_received=event.bytes_received,
                            bytes_total=event.content_length,
                        ),
                    )

        response = await http_client.get(
            url,
            label=f"vizier:{spec.source_id}@{host}",
            follow_redirects=True,
            timeout=_DOWNLOAD_TIMEOUT_S,
            connect_timeout=_CONNECT_TIMEOUT_S,
            on_event=_http_event if on_progress is not None else None,
        )
        if response.status_code >= 400:
            raise _HttpFailure(response.status_code)
        content = response.content
        if not content:
            raise _NoData("empty body")
        if len(content) < _MIN_BODY_BYTES:
            raise _InvalidCatalog(f"body suspiciously short ({len(content)} bytes)")
        tmp_path.write_bytes(content)
        # An HTML or proxy error page served with HTTP 200 fails here, so the
        # next mirror still gets its turn.
        try:
            _verify_tsv_shape(tmp_path, required_columns)
        except ValueError as exc:
            raise _InvalidCatalog(str(exc)) from exc
        return content

    try:
        # One pass over the mirrors. ``http_client.get`` already retries a
        # transient failure once per host; the next mirror is the retry after
        # that, so an unreachable host costs about twice the connect timeout.
        failures: list[str] = []
        content: bytes | None = None
        source_url = ""
        attempt_message = f"Trying {_HOST_NAMES[VIZIER_HOSTS[0]]}…"
        for index, host in enumerate(VIZIER_HOSTS):
            url = _build_url(spec, host)
            _emit(
                on_progress,
                ProgressUpdate("trying_source", attempt_message),
            )
            host_started = _clock()
            try:
                content = await _download(url, host, attempt_message)
            except Exception as exc:  # noqa: BLE001 — rotate to next mirror
                host_duration_s = round(max(0.0, _clock() - host_started))
                error_name = type(exc).__name__
                if isinstance(exc, (_HttpFailure, _NoData)):
                    error_name = "RuntimeError"
                elif isinstance(exc, _InvalidCatalog):
                    error_name = "ValueError"
                reason = f"{error_name}: {exc}" if str(exc) else error_name
                failures.append(f"{host} ({reason})")
                logger.warning(
                    "[vizier] %s: %s failed (%s), trying next mirror",
                    spec.source_id,
                    host,
                    reason,
                )
                if index + 1 < len(VIZIER_HOSTS):
                    next_host = VIZIER_HOSTS[index + 1]
                    attempt_message = (
                        f"{_HOST_SUBJECTS[host]} {_failure_reason(exc)} "
                        f"after {host_duration_s} s. "
                        f"Trying {_HOST_NAMES[next_host]}…"
                    )
                    _emit(
                        on_progress,
                        ProgressUpdate(
                            "moving_source",
                            attempt_message,
                        ),
                    )
                continue
            source_url = url
            break
        if content is None:
            raise NoVizierSource(
                f"All VizieR mirrors failed for {spec.source_id}: {'; '.join(failures)}"
            )

        _emit(on_progress, ProgressUpdate("checking", "Checking downloaded files…"))

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

        _emit(on_progress, ProgressUpdate("saving", "Saving files to the local cache…"))
        tmp_path.replace(final_path)

        result = VizierFetchResult(
            source_id=spec.source_id,
            output_path=final_path,
            sha256=hashlib.sha256(content).hexdigest(),
            size_bytes=len(content),
            fetched_at=datetime.now(UTC).isoformat(timespec="seconds"),
            source_url=source_url,
        )
        _write_version_json(vizier_dir, spec, result)

        logger.info(
            "[vizier] %s: downloaded %d bytes from %s → %s",
            spec.source_id,
            result.size_bytes,
            source_url,
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
