"""VizieR TSV fetcher.

Parallels ``catalog_loader/remote.py`` (the OpenNGC GitHub fetcher), but
targets VizieR's ``asu-tsv`` endpoint. Each logical source has a
:class:`VizierFetchSpec` with the catalog id, output filename, optional
column filter and query constraints. A logical catalog stages and validates
all of its tables before publication; ``version.json`` is the commit point,
and a per-catalog marker keeps interrupted publications unavailable.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import shutil
import stat
import tempfile
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import httpx

from nightcrate.services import http_client
from nightcrate.services.catalog_progress import ProgressCallback, ProgressUpdate

logger = logging.getLogger("nightcrate.catalog_loader.vizier")

VIZIER_PATH = "/viz-bin/asu-tsv"
# Mirror order: Strasbourg (the cited primary) → CfA Harvard → IDIA South
# Africa → Tokyo → Beijing → India. Checked 2026-11-03 during the CDS outage:
# Tokyo and Beijing answer only over plain HTTP and serve every NightCrate
# table except V/163; their Sharpless tables match IDIA byte for byte. India
# timed out over both schemes on 2026-11-01 and 2026-11-03; HTTP is retained
# because it can reach or redirect an HTTP-only service instead of failing at
# TLS setup. Each available mirror is tried once in this order.
VIZIER_HOSTS: tuple[str, ...] = (
    "vizier.cds.unistra.fr",
    "vizier.cfa.harvard.edu",
    "vizier.idia.ac.za",
    "vizier.nao.ac.jp",
    "vizier.china-vo.org",
    "vizier.iucaa.in",
)
_HOST_SCHEMES = {
    VIZIER_HOSTS[0]: "https",
    VIZIER_HOSTS[1]: "https",
    VIZIER_HOSTS[2]: "https",
    VIZIER_HOSTS[3]: "http",
    VIZIER_HOSTS[4]: "http",
    VIZIER_HOSTS[5]: "http",
}
VIZIER_BASE = f"{_HOST_SCHEMES[VIZIER_HOSTS[0]]}://{VIZIER_HOSTS[0]}{VIZIER_PATH}"
_HOST_NAMES = {
    VIZIER_HOSTS[0]: "CDS Strasbourg",
    VIZIER_HOSTS[1]: "the Harvard mirror",
    VIZIER_HOSTS[2]: "the South Africa mirror",
    VIZIER_HOSTS[3]: "the Tokyo mirror",
    VIZIER_HOSTS[4]: "the Beijing mirror",
    VIZIER_HOSTS[5]: "the India mirror",
}
_HOST_SUBJECTS = {
    VIZIER_HOSTS[0]: "Strasbourg",
    VIZIER_HOSTS[1]: "Harvard",
    VIZIER_HOSTS[2]: "South Africa",
    VIZIER_HOSTS[3]: "Tokyo",
    VIZIER_HOSTS[4]: "Beijing",
    VIZIER_HOSTS[5]: "India",
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
MIRROR_DOWN_S = 3600.0
_mirror_down_until: dict[str, float] = {}
_last_probe_at: float | None = None


def reset_mirror_health() -> None:
    """Forget recent mirror failures, primarily to isolate tests."""
    global _last_probe_at

    _mirror_down_until.clear()
    _last_probe_at = None


def record_fresh_probe_for_tests() -> None:
    """Record all mirrors up so unrelated tests do not make probe requests."""
    global _last_probe_at

    _mirror_down_until.clear()
    _last_probe_at = _clock()


def _mirror_order() -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return available hosts in table order and the hosts currently down."""
    now = _clock()
    marked = tuple(host for host in VIZIER_HOSTS if _mirror_down_until.get(host, 0.0) > now)
    unmarked = tuple(host for host in VIZIER_HOSTS if host not in marked)
    return unmarked, marked


def _joined_phrases(phrases: Sequence[str]) -> str:
    if len(phrases) == 1:
        return phrases[0]
    if len(phrases) == 2:
        return f"{phrases[0]} and {phrases[1]}"
    return f"{', '.join(phrases[:-1])} and {phrases[-1]}"


def _joined_host_subjects(hosts: Sequence[str]) -> str:
    return _joined_phrases([_HOST_SUBJECTS[host] for host in hosts])


def _down_phrase(hosts: Sequence[str]) -> str:
    verb = "is" if len(hosts) == 1 else "are"
    return f"{_joined_host_subjects(hosts)} {verb} down"


def _grouped_failure_summary(outcomes: Sequence[tuple[str, str]]) -> str:
    grouped: dict[str, list[str]] = {}
    for host, reason in outcomes:
        grouped.setdefault(reason, []).append(host)

    phrases: list[str] = []
    for reason, hosts in grouped.items():
        subjects = _joined_host_subjects(hosts)
        if reason == "is down":
            phrases.append(_down_phrase(hosts))
        elif reason == "doesn't have this table" and len(hosts) > 1:
            phrases.append(f"{subjects} don't have this table")
        else:
            phrases.append(f"{subjects} {reason}")
    return _joined_phrases(phrases)


def _mark_mirror_failed(host: str, source_id: str, reason: str) -> None:
    _mirror_down_until[host] = _clock() + MIRROR_DOWN_S
    logger.warning(
        "[vizier] %s: %s marked failed for %.0f s (%s), trying next mirror",
        source_id,
        host,
        MIRROR_DOWN_S,
        reason,
    )


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
    # Columns which must be present in the downloaded table. When omitted,
    # preserve the legacy behaviour of deriving them from ``-out.add``.
    required_columns: tuple[str, ...] = ()


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

    def __init__(
        self,
        message: str,
        *,
        summary: str,
        table_display_name: str | None = None,
        part_index: int = 1,
        part_count: int = 1,
    ) -> None:
        super().__init__(message)
        self.summary = summary
        self.table_display_name = table_display_name
        self.part_index = part_index
        self.part_count = part_count


class _HttpFailure(RuntimeError):
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"HTTP {status_code}")


class _NoData(RuntimeError):
    pass


class _InvalidCatalog(RuntimeError):
    pass


class _TableNotFound(_InvalidCatalog):
    pass


def _emit(on_progress: ProgressCallback | None, progress: ProgressUpdate) -> None:
    if on_progress is not None:
        on_progress(progress)


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
    if isinstance(exc, _TableNotFound):
        return "doesn't have this table"
    if isinstance(exc, _InvalidCatalog):
        return "returned something that isn't the catalog"
    return "failed"


def _technical_failure(exc: BaseException) -> str:
    error_name = type(exc).__name__
    if isinstance(exc, (_HttpFailure, _NoData)):
        error_name = "RuntimeError"
    elif isinstance(exc, _InvalidCatalog):
        error_name = "ValueError"
    return f"{error_name}: {exc}" if str(exc) else error_name


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
    return f"{_HOST_SCHEMES[host]}://{host}{VIZIER_PATH}?{'&'.join(parts)}"


def _probe_url(host: str) -> str:
    return f"{_HOST_SCHEMES[host]}://{host}{VIZIER_PATH}?-source=VII/20/catalog&-out=Sh2,Diam&-out.max=1"


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


async def _probe_mirrors(
    probe_dir: Path,
    on_progress: ProgressCallback | None,
) -> bool:
    """Check every mirror concurrently and record which ones answered."""
    global _last_probe_at

    _emit(
        on_progress,
        ProgressUpdate("trying_source", "Checking which VizieR mirrors are up…"),
    )

    async def _probe_one(index: int, host: str) -> tuple[str, str | None]:
        path = probe_dir / f".probe-{index}.tsv"
        try:
            response = await http_client.get(
                _probe_url(host),
                label=f"vizier:probe@{host}",
                attempts=1,
                timeout=10.0,
                connect_timeout=10.0,
                follow_redirects=True,
            )
            if response.status_code != 200:
                raise _HttpFailure(response.status_code)
            if not response.content:
                raise _NoData("empty body")
            path.write_bytes(response.content)
            try:
                _verify_tsv_shape(path, ("Sh2", "Diam"))
            except ValueError as exc:
                raise _InvalidCatalog(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 — one failed probe must not cancel its peers
            return host, _technical_failure(exc)
        finally:
            path.unlink(missing_ok=True)
        return host, None

    results = await asyncio.gather(
        *(_probe_one(index, host) for index, host in enumerate(VIZIER_HOSTS))
    )
    up_hosts = {host for host, reason in results if reason is None}
    if not up_hosts:
        _mirror_down_until.clear()
        _last_probe_at = None
        for host, reason in results:
            logger.warning("[vizier] probe: %s is down (%s)", host, reason)
        return False

    checked_at = _clock()
    _mirror_down_until.clear()
    for host, reason in results:
        if reason is None:
            continue
        _mirror_down_until[host] = checked_at + MIRROR_DOWN_S
        logger.warning("[vizier] probe: %s is down (%s)", host, reason)
    _last_probe_at = checked_at
    return True


async def _ensure_mirrors_probed(
    probe_dir: Path,
    on_progress: ProgressCallback | None,
) -> bool:
    available, _down = _mirror_order()
    now = _clock()
    if _last_probe_at is None or now - _last_probe_at >= MIRROR_DOWN_S or not available:
        return await _probe_mirrors(probe_dir, on_progress)
    return True


def _version_entry(spec: VizierFetchSpec, result: VizierFetchResult) -> dict[str, object]:
    return {
        "source_id": spec.source_id,
        "catalog_id": spec.catalog_id,
        "source_url": result.source_url,
        "fetch_date": result.fetched_at,
        "sha256": result.sha256,
        "size_bytes": result.size_bytes,
        "citation": spec.citation,
        "license": "CDS public — see attribution panel",
    }


def _atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    """Durably replace a JSON file without exposing a partial write."""
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o644
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}-", delete=False
        ) as stream:
            temporary = Path(stream.name)
            json.dump(payload, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _required_columns(spec: VizierFetchSpec) -> tuple[str, ...]:
    if spec.required_columns:
        return spec.required_columns
    return tuple(name for name in spec.additional_params.get("-out.add", "").split(",") if name)


async def fetch_vizier_tables(
    specs: Sequence[VizierFetchSpec],
    catalogs_root: Path,
    on_progress: ProgressCallback | None = None,
    *,
    catalog_id: str | None = None,
) -> list[VizierFetchResult]:
    """Stage, validate, then publish every table as one catalog commit."""
    if not specs:
        return []
    if catalog_id is not None:
        from nightcrate.catalog_loader.registry import optional_catalog

        catalog = optional_catalog(catalog_id)
        if catalog is None:
            raise ValueError(f"Unknown optional catalog: {catalog_id}")
        catalog_name = catalog.display_name
    else:
        catalog_name = specs[0].display_name
    marker_catalog_id = catalog_id or specs[0].source_id
    vizier_dir = catalogs_root / "vizier"
    tmp_dir = vizier_dir / ".download"
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    async def _download(
        spec: VizierFetchSpec,
        tmp_path: Path,
        url: str,
        host: str,
        attempt_message: str,
        part_suffix: str,
    ) -> bytes:
        host_name = _HOST_NAMES[host]
        progress_name = f"{catalog_name}{part_suffix}"

        def _http_event(event: http_client.GetEvent) -> None:
            if event.kind == "attempt":
                _emit(on_progress, ProgressUpdate("trying_source", attempt_message))
            elif event.kind == "response" and event.status_code is not None:
                if event.status_code < 400:
                    _emit(
                        on_progress,
                        ProgressUpdate(
                            "downloading",
                            f"Downloading {progress_name} from {host_name}…",
                            bytes_total=event.content_length,
                        ),
                    )
            elif event.kind == "bytes" and event.status_code is not None:
                if event.status_code < 400:
                    _emit(
                        on_progress,
                        ProgressUpdate(
                            "downloading",
                            f"Downloading {progress_name} from {host_name}…",
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
        if b"Error=Table or Catalog not found" in content:
            raise _TableNotFound("table or catalog not found")
        if len(content) < _MIN_BODY_BYTES:
            raise _InvalidCatalog(f"body suspiciously short ({len(content)} bytes)")
        tmp_path.write_bytes(content)
        # An HTML or proxy error page served with HTTP 200 fails here, so the
        # next mirror still gets its turn.
        try:
            _verify_tsv_shape(tmp_path, _required_columns(spec))
        except ValueError as exc:
            raise _InvalidCatalog(str(exc)) from exc
        return content

    try:
        results: list[VizierFetchResult] = []
        total_parts = len(specs)
        for part_index, spec in enumerate(specs, start=1):
            tmp_path = tmp_dir / spec.output_filename
            part_suffix = f" (part {part_index} of {total_parts})" if total_parts > 1 else ""
            if not await _ensure_mirrors_probed(tmp_dir, on_progress):
                raise NoVizierSource(
                    f"No VizieR mirrors answered the availability probe for {spec.source_id}",
                    summary="no VizieR mirror answered; check your internet connection",
                    table_display_name=spec.display_name,
                    part_index=part_index,
                    part_count=total_parts,
                )
            technical_failures: dict[str, str] = {}
            failure_reasons: dict[str, str] = {}
            content: bytes | None = None
            source_url = ""
            hosts, down_hosts = _mirror_order()
            attempt_message = f"Trying {_HOST_NAMES[hosts[0]]}…"
            if down_hosts:
                attempt_message = f"{_down_phrase(down_hosts)}. {attempt_message}"
            for index, host in enumerate(hosts):
                url = _build_url(spec, host)
                _emit(on_progress, ProgressUpdate("trying_source", attempt_message))
                host_started = _clock()
                try:
                    content = await _download(
                        spec, tmp_path, url, host, attempt_message, part_suffix
                    )
                except Exception as exc:  # noqa: BLE001 — rotate to next mirror
                    host_duration_s = round(max(0.0, _clock() - host_started))
                    reason = _technical_failure(exc)
                    technical_failures[host] = reason
                    failure_reasons[host] = _failure_reason(exc)
                    if isinstance(exc, httpx.TransportError) or (
                        isinstance(exc, _HttpFailure) and exc.status_code >= 500
                    ):
                        _mark_mirror_failed(host, spec.source_id, reason)
                    else:
                        logger.warning(
                            "[vizier] %s: %s failed (%s), trying next mirror",
                            spec.source_id,
                            host,
                            reason,
                        )
                    if index + 1 < len(hosts):
                        next_host = hosts[index + 1]
                        if isinstance(exc, _TableNotFound):
                            attempt_message = (
                                f"{_HOST_SUBJECTS[host]} {_failure_reason(exc)}. "
                                f"Trying {_HOST_NAMES[next_host]}…"
                            )
                        else:
                            attempt_message = (
                                f"{_HOST_SUBJECTS[host]} {_failure_reason(exc)} "
                                f"after {host_duration_s} s. "
                                f"Trying {_HOST_NAMES[next_host]}…"
                            )
                        _emit(
                            on_progress,
                            ProgressUpdate("moving_source", attempt_message),
                        )
                    continue
                _mirror_down_until.pop(host, None)
                source_url = url
                break
            if content is None:
                outcomes = [
                    (host, "is down" if host in down_hosts else failure_reasons[host])
                    for host in VIZIER_HOSTS
                    if host in down_hosts or host in failure_reasons
                ]
                technical = "; ".join(
                    f"{host} ({'marked down' if host in down_hosts else technical_failures[host]})"
                    for host in VIZIER_HOSTS
                    if host in down_hosts or host in technical_failures
                )
                raise NoVizierSource(
                    f"All VizieR mirrors failed for {spec.source_id}: {technical}",
                    summary=_grouped_failure_summary(outcomes),
                    table_display_name=spec.display_name,
                    part_index=part_index,
                    part_count=total_parts,
                )
            results.append(
                VizierFetchResult(
                    source_id=spec.source_id,
                    output_path=vizier_dir / spec.output_filename,
                    sha256=hashlib.sha256(content).hexdigest(),
                    size_bytes=len(content),
                    fetched_at=datetime.now(UTC).isoformat(timespec="seconds"),
                    source_url=source_url,
                )
            )

        _emit(on_progress, ProgressUpdate("checking", "Checking downloaded files…"))
        _emit(on_progress, ProgressUpdate("saving", "Saving files to the local cache…"))
        marker_path = vizier_dir / "publishing" / f"{marker_catalog_id}.json"
        _atomic_write_json(
            marker_path,
            {
                "version": 1,
                "catalog_id": marker_catalog_id,
                "files": [spec.output_filename for spec in specs],
            },
        )

        for spec in specs:
            os.replace(tmp_dir / spec.output_filename, vizier_dir / spec.output_filename)

        version_path = vizier_dir / "version.json"
        payload: dict[str, object] = {"category": "vizier", "files": {}}
        if version_path.exists():
            try:
                loaded = json.loads(version_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict) and isinstance(loaded.get("files"), dict):
                    payload = loaded
            except _VERSION_JSON_ERRS:
                pass
        files = payload.setdefault("files", {})
        if not isinstance(files, dict):
            files = {}
            payload["files"] = files
        for spec, result in zip(specs, results, strict=True):
            files[spec.output_filename] = _version_entry(spec, result)
        _atomic_write_json(version_path, payload)
        marker_path.unlink()

        for result in results:
            logger.info(
                "[vizier] %s: downloaded %d bytes from %s → %s",
                result.source_id,
                result.size_bytes,
                result.source_url,
                result.output_path,
            )
        return results
    finally:
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)


async def fetch_vizier_catalog(
    spec: VizierFetchSpec,
    catalogs_root: Path,
    on_progress: ProgressCallback | None = None,
) -> VizierFetchResult:
    """Backward-compatible one-table wrapper around :func:`fetch_vizier_tables`."""
    return (await fetch_vizier_tables((spec,), catalogs_root, on_progress))[0]


def remove_vizier_files(
    catalog_id: str,
    filenames: set[str],
    catalogs_root: Path,
    *,
    keep_files: set[str] | None = None,
) -> None:
    """Remove one optional catalog's unshared files and commit metadata."""
    keep = keep_files or set()
    removed = filenames - keep
    vizier_dir = catalogs_root / "vizier"
    (vizier_dir / "publishing" / f"{catalog_id}.json").unlink(missing_ok=True)
    for filename in removed:
        (vizier_dir / filename).unlink(missing_ok=True)

    version_path = vizier_dir / "version.json"
    if not version_path.exists():
        return
    try:
        payload = json.loads(version_path.read_text(encoding="utf-8"))
    except _VERSION_JSON_ERRS:
        return
    files = payload.get("files")
    if not isinstance(files, dict):
        return
    for filename in removed:
        files.pop(filename, None)
    _atomic_write_json(version_path, payload)


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
