"""Archive I/O — unified interface for zip, tar (gz/bz2/zst), and 7z archives."""

from __future__ import annotations

import io
import os
import tarfile
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

import py7zr

# Compound suffixes checked longest-first so .tar.gz matches before .gz
_ARCHIVE_SUFFIXES: list[str] = [
    ".tar.gz",
    ".tar.bz2",
    ".tar.zst",
    ".tar.xz",
    ".tgz",
    ".tar",
    ".zip",
    ".7z",
]

# Map compound suffix to tarfile open mode
_TAR_MODES: dict[str, str] = {
    ".tar": "r:",
    ".tar.gz": "r:gz",
    ".tgz": "r:gz",
    ".tar.bz2": "r:bz2",
    ".tar.zst": "r:zst",
    ".tar.xz": "r:xz",
}


def _get_suffix(path: Path) -> str:
    """Return the archive suffix (compound-aware), lowercased, or empty string."""
    name_lower = path.name.lower()
    for suffix in _ARCHIVE_SUFFIXES:
        if name_lower.endswith(suffix):
            return suffix
    return ""


def _validate_path(entry_path: str, label: str = "entry") -> None:
    """Reject path traversal attempts."""
    p = PurePosixPath(entry_path)
    if p.is_absolute():
        msg = f"Path traversal rejected: {label} must not be absolute"
        raise ValueError(msg)
    if ".." in p.parts:
        msg = f"Path traversal rejected: {label} must not contain '..'"
        raise ValueError(msg)


def is_archive(path: Path) -> bool:
    """Detect whether a path is an archive by extension."""
    return _get_suffix(path) != ""


def list_contents(archive_path: Path, subdir: str = "") -> list[dict]:
    """List entries at a directory level within an archive (TOC only).

    Returns a list of dicts with keys: name, is_dir, size (None for dirs).
    """
    if subdir:
        _validate_path(subdir, "subdir")

    suffix = _get_suffix(archive_path)
    if suffix == ".zip":
        return _list_zip(archive_path, subdir)
    if suffix in _TAR_MODES:
        return _list_tar(archive_path, suffix, subdir)
    if suffix == ".7z":
        return _list_7z(archive_path, subdir)

    msg = f"Unsupported archive format: {archive_path.name}"
    raise ValueError(msg)


def extract_entry(archive_path: Path, entry_path: str) -> io.BytesIO:
    """Extract a single file from an archive into memory.

    Returns a BytesIO positioned at the start.
    Raises FileNotFoundError if entry_path is not in the archive.
    Raises ValueError for path traversal attempts.
    """
    _validate_path(entry_path, "entry")

    suffix = _get_suffix(archive_path)
    if suffix == ".zip":
        return _extract_zip(archive_path, entry_path)
    if suffix in _TAR_MODES:
        return _extract_tar(archive_path, suffix, entry_path)
    if suffix == ".7z":
        return _extract_7z(archive_path, entry_path)

    msg = f"Unsupported archive format: {archive_path.name}"
    raise ValueError(msg)


# ---------------------------------------------------------------------------
# Internal — directory synthesis from flat entry paths
# ---------------------------------------------------------------------------


def _build_level_entries(
    all_paths: list[tuple[str, int | None]],
    subdir: str,
) -> list[dict]:
    """Given (full_path, size_or_None) pairs, return entries at the requested level.

    Directories are synthesized from paths — archives don't always have explicit
    directory entries.
    """
    prefix = f"{subdir}/" if subdir else ""
    dirs: set[str] = set()
    files: dict[str, int | None] = {}

    for full_path, size in all_paths:
        # Skip entries not under the requested prefix
        if not full_path.startswith(prefix):
            continue

        remainder = full_path[len(prefix) :]
        if not remainder:
            continue

        parts = remainder.split("/")
        if len(parts) == 1:
            # Direct child file
            files[parts[0]] = size
        else:
            # There is a deeper level — synthesize a directory entry
            dirs.add(parts[0])

    entries: list[dict] = []
    for d in sorted(dirs):
        entries.append({"name": d, "is_dir": True, "size": None})
    for name in sorted(files):
        entries.append({"name": name, "is_dir": False, "size": files[name]})
    return entries


# ---------------------------------------------------------------------------
# ZIP
# ---------------------------------------------------------------------------


def _list_zip(archive_path: Path, subdir: str) -> list[dict]:
    with zipfile.ZipFile(archive_path, "r") as zf:
        all_paths: list[tuple[str, int | None]] = []
        for info in zf.infolist():
            # Skip explicit directory entries — we synthesize them
            if info.filename.endswith("/"):
                continue
            all_paths.append((info.filename, info.file_size))
        return _build_level_entries(all_paths, subdir)


def _extract_zip(archive_path: Path, entry_path: str) -> io.BytesIO:
    with zipfile.ZipFile(archive_path, "r") as zf:
        try:
            data = zf.read(entry_path)
        except KeyError:
            msg = f"Entry not found in archive: {entry_path}"
            raise FileNotFoundError(msg)
        return io.BytesIO(data)


# ---------------------------------------------------------------------------
# TAR (all variants)
# ---------------------------------------------------------------------------


def _list_tar(archive_path: Path, suffix: str, subdir: str) -> list[dict]:
    mode = _TAR_MODES[suffix]
    with tarfile.open(archive_path, mode) as tf:
        all_paths: list[tuple[str, int | None]] = []
        for member in tf.getmembers():
            if member.isdir():
                continue
            all_paths.append((member.name, member.size))
        return _build_level_entries(all_paths, subdir)


def _extract_tar(archive_path: Path, suffix: str, entry_path: str) -> io.BytesIO:
    mode = _TAR_MODES[suffix]
    with tarfile.open(archive_path, mode) as tf:
        try:
            member = tf.getmember(entry_path)
        except KeyError:
            msg = f"Entry not found in archive: {entry_path}"
            raise FileNotFoundError(msg)
        f = tf.extractfile(member)
        if f is None:
            msg = f"Entry not found in archive: {entry_path}"
            raise FileNotFoundError(msg)
        buf = io.BytesIO(f.read())
        return buf


# ---------------------------------------------------------------------------
# 7z
# ---------------------------------------------------------------------------


def _list_7z(archive_path: Path, subdir: str) -> list[dict]:
    with py7zr.SevenZipFile(archive_path, "r") as szf:
        all_paths: list[tuple[str, int | None]] = []
        for entry in szf.list():
            if entry.is_directory:
                continue
            all_paths.append((entry.filename, entry.uncompressed))
        return _build_level_entries(all_paths, subdir)


def _extract_7z(archive_path: Path, entry_path: str) -> io.BytesIO:
    with py7zr.SevenZipFile(archive_path, "r") as szf:
        names = szf.getnames()
        if entry_path not in names:
            msg = f"Entry not found in archive: {entry_path}"
            raise FileNotFoundError(msg)
        with tempfile.TemporaryDirectory() as td:
            szf.extract(path=td, targets=[entry_path])
            extracted = Path(td) / entry_path
            # py7zr may create files with restrictive permissions
            os.chmod(extracted, 0o644)
            return io.BytesIO(extracted.read_bytes())
