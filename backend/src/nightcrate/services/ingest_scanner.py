"""Directory scanning + per-file FITS parsing for the ingest pipeline (v0.40.0).

Two layers:

  * :func:`scan_directory` — fast filesystem walk on the main process; classifies
    every file by path (extension/name) into a :class:`ScanEntry`.
  * :func:`parse_image_file` — the CPU-bound worker (header read + content hash)
    dispatched to a ``ProcessPoolExecutor`` for header-bearing files. It is a
    module-level function returning a plain picklable dict (no DB, no resolver).

The ingest API (``api/ingest.py``) drives both and owns all DB writes.
"""

from __future__ import annotations

import logging
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from nightcrate.services.ingest_classify import (
    CATEGORY_SUB,
    classify_extension,
    is_sidecar,
)

logger = logging.getLogger("nightcrate.ingest")

_LOG_PREFIX = "[ingest-scan]"


@dataclass
class ScanEntry:
    """One file found during the directory walk."""

    path: str
    name: str
    category: str  # CATEGORY_* from ingest_classify
    size_bytes: int
    mtime: str  # ISO 8601 UTC


@dataclass
class ScanReport:
    """Files found plus places the scan could not or deliberately did not list."""

    entries: list[ScanEntry]
    root_error: str | None = None
    unlisted_dirs: list[tuple[str, str]] = field(default_factory=list)
    unreadable_files: list[tuple[str, str]] = field(default_factory=list)
    skipped_dirs: list[str] = field(default_factory=list)

    def __iter__(self):
        return iter(self.entries)


def scan_directory(root: str) -> ScanReport:
    """Recursively walk *root*, skipping hidden files/dirs, classifying each file.

    `.pxiproject` directories are recorded as a single entry (a project asset),
    not descended into.

    *root* may also address a folder **inside an archive** — either the archive
    itself (``/data/night.zip``) or a directory within it
    (``/data/night.zip::lights/ha``). Entries then carry the same ``::`` virtual
    path the rest of the app uses, and :func:`parse_image_file` reads them
    straight out of the archive.
    """
    if _archive_root(root) is not None:
        return _scan_archive(root)

    base = Path(root).expanduser()
    report = ScanReport(entries=[])
    try:
        base.stat()
        children = sorted(base.iterdir(), key=lambda path: path.name)
    except OSError as exc:
        report.root_error = f"{type(exc).__name__}: {exc}"
        return report

    stack = [(base, children)]
    while stack:
        _current, children = stack.pop()
        for path in children:
            try:
                is_dir = path.is_dir()
            except OSError:
                is_dir = False
            is_hidden = path.name.startswith(".")
            is_pxiproject = is_dir and path.name.lower().endswith(".pxiproject")
            if is_hidden and not is_dir:
                continue
            if is_dir and (is_hidden or is_pxiproject):
                report.skipped_dirs.append(str(path))
            if is_hidden and not is_pxiproject:
                continue
            if is_pxiproject:
                pass
            elif is_dir:
                try:
                    stack.append((path, sorted(path.iterdir(), key=lambda child: child.name)))
                except OSError as exc:
                    report.unlisted_dirs.append((str(path), f"{type(exc).__name__}: {exc}"))
                continue
            if is_sidecar(path.name):
                continue
            category = classify_extension(path.name, is_dir=is_dir)
            try:
                stat = path.stat()
            except OSError as exc:
                if category == CATEGORY_SUB:
                    report.unreadable_files.append((str(path), f"{type(exc).__name__}: {exc}"))
                continue
            report.entries.append(
                ScanEntry(
                    path=str(path),
                    name=path.name,
                    category=category,
                    size_bytes=stat.st_size if not is_dir else 0,
                    mtime=_iso_mtime(stat.st_mtime),
                )
            )
    return report


def _archive_root(root: str) -> tuple[Path, str] | None:
    """Split *root* into (archive, subdir) when it addresses an archive, else None."""
    from nightcrate.services.archive_io import is_archive

    left, sep, right = root.partition("::")
    archive = Path(left).expanduser()
    if not is_archive(archive) or not archive.is_file():
        return None
    return archive, right.strip("/") if sep else ""


def _scan_archive(root: str) -> ScanReport:
    """Walk a directory inside an archive, yielding ``archive::entry`` paths.

    Archives carry no per-entry mtime in the TOC listing we use, so every entry
    inherits the archive file's own mtime. For a frame that is only a fallback —
    a header's DATE-OBS wins. For a log or other non-header file it is the
    timestamp stored on ``file_location`` and shown in the catalog's Others tab,
    so it reads as the archive's date rather than the file's own.

    ``.pxiproject`` bundles are recorded as one asset and not descended into,
    matching the filesystem scanner. Nested archives are catalogued as plain files.
    """
    from nightcrate.services.archive_io import list_contents

    parsed = _archive_root(root)
    if parsed is None:
        return ScanReport(entries=[], root_error="The archive couldn't be opened.")
    archive, start = parsed
    report = ScanReport(entries=[])
    try:
        mtime = _iso_mtime(archive.stat().st_mtime)
    except OSError as exc:
        report.root_error = f"{type(exc).__name__}: {exc}"
        return report

    stack = [start]
    while stack:
        subdir = stack.pop()
        try:
            children = list_contents(archive, subdir)
        except (OSError, ValueError) as exc:
            logger.warning("%s cannot list %s::%s — %s", _LOG_PREFIX, archive, subdir, exc)
            message = f"{type(exc).__name__}: {exc}"
            virtual_dir = f"{archive}::{subdir}" if subdir else str(archive)
            if subdir == start:
                report.root_error = message
            else:
                report.unlisted_dirs.append((virtual_dir, message))
            continue
        for child in children:
            name = child["name"]
            if name.startswith("."):
                if child["type"] == "dir":
                    entry_path = f"{subdir}/{name}" if subdir else name
                    report.skipped_dirs.append(f"{archive}::{entry_path}")
                continue
            entry_path = f"{subdir}/{name}" if subdir else name
            if child["type"] == "dir":
                # A .pxiproject is a directory, but it is one asset — the same
                # rule applied on the filesystem. Descending into it would
                # catalog its internals as loose files.
                if name.lower().endswith(".pxiproject"):
                    report.skipped_dirs.append(f"{archive}::{entry_path}")
                    report.entries.append(
                        ScanEntry(
                            path=f"{archive}::{entry_path}",
                            name=name,
                            category=classify_extension(name, is_dir=True),
                            size_bytes=0,
                            mtime=mtime,
                        )
                    )
                    continue
                stack.append(entry_path)
                continue
            if is_sidecar(name):
                continue
            report.entries.append(
                ScanEntry(
                    path=f"{archive}::{entry_path}",
                    name=name,
                    category=classify_extension(name, is_dir=False),
                    size_bytes=child.get("size") or 0,
                    mtime=mtime,
                )
            )
    return report


def _iso_mtime(epoch: float) -> str:
    from datetime import UTC, datetime

    return datetime.fromtimestamp(epoch, tz=UTC).isoformat()


def parse_image_file(path_str: str) -> dict:
    """Worker: read header + content hash for one FITS/XISF file.

    Module-level + picklable so it runs under ProcessPoolExecutor (spawn). Returns
    a dict; on failure returns ``{"path", "error"}`` so the caller can record an
    ingestion error without aborting the run.
    """
    # Imports are inside the worker so the spawned process resolves them cleanly.
    from nightcrate.catalog_loader.hash import file_sha256
    from nightcrate.services.fits_header_map import extract_metadata
    from nightcrate.services.path_resolver import file_type

    if "::" in path_str:
        return _parse_archive_entry(path_str)

    path = Path(path_str)
    try:
        ftype = file_type(path)
        if ftype == "xisf":
            from nightcrate.services.xisf_io import read_header
        else:
            from nightcrate.services.fits_io import read_header

        cards = read_header(path)
        raw_header = {c["key"]: c["value"] for c in cards if c.get("key")}
        meta = extract_metadata(raw_header)
        content_hash = file_sha256(path)
        if ftype == "xisf":
            from nightcrate.services import xisf_io

            for index in range(len(xisf_io.list_extensions(path))):
                xisf_io.verify_image(path, index)
        stat = path.stat()
        return {
            "path": path_str,
            "content_hash": content_hash,
            "size_bytes": stat.st_size,
            "mtime": _iso_mtime(stat.st_mtime),
            "meta": meta,
            "raw_header": raw_header,
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001 - any parse failure is a recorded error, not fatal
        from nightcrate.services.xisf_io import (
            XISFChecksumError,
            XISFError,
            XISFUnavailableError,
        )

        message = str(exc) if isinstance(exc, XISFError) else f"{type(exc).__name__}: {exc}"
        reason = (
            "damaged"
            if isinstance(exc, XISFChecksumError)
            else "unsupported"
            if isinstance(exc, XISFUnavailableError)
            else "unreadable"
        )
        return {"path": path_str, "error": message, "reason": reason}


def _parse_archive_entry(path_str: str) -> dict:
    """Worker branch for ``archive::entry`` paths — same contract as the plain one.

    The entry is extracted **once** and hashed from those bytes; the header gets
    its own fresh ``BytesIO`` because astropy closes any file object handed to it,
    so a single buffer cannot serve both consumers.
    """
    import hashlib
    import io

    from nightcrate.services.archive_io import extract_entry
    from nightcrate.services.fits_header_map import extract_metadata
    from nightcrate.services.path_resolver import file_type

    archive_str, entry = path_str.rsplit("::", 1)
    archive = Path(archive_str)
    try:
        raw = extract_entry(archive, entry).getvalue()
        ftype = file_type(Path(entry))
        if ftype == "xisf":
            from nightcrate.services.xisf_io import read_header
        else:
            from nightcrate.services.fits_io import read_header

        cards = read_header(io.BytesIO(raw))
        raw_header = {c["key"]: c["value"] for c in cards if c.get("key")}
        if ftype == "xisf":
            from nightcrate.services import xisf_io

            for index in range(len(xisf_io.list_extensions(io.BytesIO(raw)))):
                xisf_io.verify_image(io.BytesIO(raw), index)
        return {
            "path": path_str,
            "content_hash": hashlib.sha256(raw).hexdigest(),
            "size_bytes": len(raw),
            "mtime": _iso_mtime(archive.stat().st_mtime),
            "meta": extract_metadata(raw_header),
            "raw_header": raw_header,
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001 - a bad entry is a recorded error, not fatal
        from nightcrate.services.xisf_io import (
            XISFChecksumError,
            XISFError,
            XISFUnavailableError,
        )

        message = str(exc) if isinstance(exc, XISFError) else f"{type(exc).__name__}: {exc}"
        reason = (
            "damaged"
            if isinstance(exc, XISFChecksumError)
            else "unsupported"
            if isinstance(exc, XISFUnavailableError)
            else "unreadable"
        )
        return {"path": path_str, "error": message, "reason": reason}


# ── ProcessPool ──────────────────────────────────────────────────────────────


def make_pool(n_workers: int) -> ProcessPoolExecutor:
    """Create a fresh spawn-context pool for a single ingest run.

    **Deliberately NOT a persistent module-global pool.** A long-lived pool leaves
    spawn worker processes alive after the run; under ``uvicorn --reload`` those
    orphaned children prevent a clean restart and wedge the dev server. The caller
    owns this pool and must shut it down (``with`` block) when the run finishes —
    the ~1 s spawn cost is negligible against a folder scan.
    """
    import multiprocessing as mp

    ctx = mp.get_context("spawn")
    pool = ProcessPoolExecutor(max_workers=max(1, n_workers), mp_context=ctx)
    logger.info("%s created ProcessPool with %d workers", _LOG_PREFIX, max(1, n_workers))
    return pool


def header_bearing(entries: list[ScanEntry]) -> list[ScanEntry]:
    """The subset of scan entries that should be header-parsed (FITS/XISF)."""
    return [e for e in entries if e.category == CATEGORY_SUB]
