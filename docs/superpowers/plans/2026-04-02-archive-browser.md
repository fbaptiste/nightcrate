# Archive Browser Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Treat archive files (zip, tar, tar.gz, tar.bz2, tar.zst, 7z) as transparent folders in the file browser, with in-memory extraction and full image viewer support.

**Architecture:** New `archive_io` service handles format dispatch (zip/tar/7z). I/O services widened from `Path` to `Path | BinaryIO`. File browse API gains archive detection and a `browse-archive` endpoint. Frontend `FileBrowser` gains an archive browse mode alongside the existing directory and project modes.

**Tech Stack:** Python stdlib (`zipfile`, `tarfile`), `py7zr` (LGPL-2.1+), existing I/O services (astropy, defusedxml, Pillow, tifffile)

**Design spec:** `docs/superpowers/specs/2026-04-02-archive-browser-design.md`

---

## File Structure

### New Files
| File | Responsibility |
|------|---------------|
| `backend/src/nightcrate/services/archive_io.py` | Archive format dispatch, TOC listing, in-memory extraction |
| `backend/tests/test_archive_io.py` | Unit tests for archive_io service |
| `backend/tests/test_archive_api.py` | API endpoint tests for archive browsing |

### Modified Files
| File | Changes |
|------|---------|
| `backend/src/nightcrate/services/fits_io.py` | Widen `Path` → `Path \| BinaryIO` |
| `backend/src/nightcrate/services/xisf_io.py` | Widen `Path` → `Path \| BinaryIO` |
| `backend/src/nightcrate/services/standard_io.py` | Widen `Path` → `Path \| BinaryIO` |
| `backend/src/nightcrate/api/files.py` | Add `archives` to browse response, new `browse-archive` endpoint |
| `backend/src/nightcrate/api/images.py` | Archive branch in `_resolve_path()`, new `_file_type_from_ext()` |
| `frontend/src/api/files.ts` | New `browseArchive()` function and `ArchiveBrowseResult` type |
| `frontend/src/components/fits/FileBrowser.tsx` | Archive browse mode, state, breadcrumb, navigation |

---

## Task 1: Install py7zr dependency

**Files:**
- Modify: `backend/pyproject.toml`

- [ ] **Step 1: Add py7zr**

```bash
cd backend && uv add py7zr
```

- [ ] **Step 2: Verify import works**

```bash
uv run python -c "import py7zr; print(py7zr.__version__)"
```

Expected: prints version number, no errors.

- [ ] **Step 3: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock
git commit -m "Add py7zr dependency for 7z archive support"
```

---

## Task 2: Archive I/O service — list contents

**Files:**
- Create: `backend/src/nightcrate/services/archive_io.py`
- Create: `backend/tests/test_archive_io.py`

- [ ] **Step 1: Write failing tests for archive detection and listing**

```python
# backend/tests/test_archive_io.py
"""Tests for archive I/O service."""

import zipfile
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits

from nightcrate.services import archive_io


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def tmp_fits_bytes() -> bytes:
    """Create a minimal FITS file in memory and return its bytes."""
    data = np.zeros((20, 30), dtype=np.uint16)
    data[10, 15] = 10000
    hdu = fits.PrimaryHDU(data)
    hdu.header["OBJECT"] = "TestStar"
    hdu.header["FILTER"] = "L"
    buf = BytesIO()
    hdu.writeto(buf)
    return buf.getvalue()


@pytest.fixture
def tmp_zip_archive(tmp_path: Path, tmp_fits_bytes: bytes) -> Path:
    """Create a zip archive with nested dirs and a FITS file."""
    archive_path = tmp_path / "test_archive.zip"
    with zipfile.ZipFile(archive_path, "w") as zf:
        zf.writestr("lights/target/image_001.fits", tmp_fits_bytes)
        zf.writestr("lights/target/image_002.fits", tmp_fits_bytes)
        zf.writestr("lights/flats/flat_001.fits", tmp_fits_bytes)
        zf.writestr("darks/dark_001.fits", tmp_fits_bytes)
        zf.writestr("notes.txt", "session notes")
    return archive_path


# ── Detection ─────────────────────────────────────────────────────────


class TestIsArchive:
    def test_zip(self, tmp_path: Path):
        assert archive_io.is_archive(tmp_path / "data.zip") is True

    def test_tar_gz(self, tmp_path: Path):
        assert archive_io.is_archive(tmp_path / "data.tar.gz") is True

    def test_tgz(self, tmp_path: Path):
        assert archive_io.is_archive(tmp_path / "data.tgz") is True

    def test_tar_bz2(self, tmp_path: Path):
        assert archive_io.is_archive(tmp_path / "data.tar.bz2") is True

    def test_tar_zst(self, tmp_path: Path):
        assert archive_io.is_archive(tmp_path / "data.tar.zst") is True

    def test_7z(self, tmp_path: Path):
        assert archive_io.is_archive(tmp_path / "data.7z") is True

    def test_plain_tar(self, tmp_path: Path):
        assert archive_io.is_archive(tmp_path / "data.tar") is True

    def test_not_archive(self, tmp_path: Path):
        assert archive_io.is_archive(tmp_path / "image.fits") is False
        assert archive_io.is_archive(tmp_path / "photo.png") is False

    def test_case_insensitive(self, tmp_path: Path):
        assert archive_io.is_archive(tmp_path / "data.ZIP") is True
        assert archive_io.is_archive(tmp_path / "data.TAR.GZ") is True


# ── Listing ───────────────────────────────────────────────────────────


class TestListContents:
    def test_root_level(self, tmp_zip_archive: Path):
        entries = archive_io.list_contents(tmp_zip_archive)
        names = {e["name"] for e in entries}
        assert names == {"lights", "darks", "notes.txt"}

    def test_root_types(self, tmp_zip_archive: Path):
        entries = archive_io.list_contents(tmp_zip_archive)
        by_name = {e["name"]: e for e in entries}
        assert by_name["lights"]["type"] == "dir"
        assert by_name["darks"]["type"] == "dir"
        assert by_name["notes.txt"]["type"] == "file"

    def test_subdir_listing(self, tmp_zip_archive: Path):
        entries = archive_io.list_contents(tmp_zip_archive, subdir="lights")
        names = {e["name"] for e in entries}
        assert names == {"target", "flats"}

    def test_nested_subdir(self, tmp_zip_archive: Path):
        entries = archive_io.list_contents(
            tmp_zip_archive, subdir="lights/target"
        )
        names = {e["name"] for e in entries}
        assert names == {"image_001.fits", "image_002.fits"}
        for e in entries:
            assert e["type"] == "file"
            assert e["size"] is not None
            assert e["size"] > 0

    def test_empty_subdir(self, tmp_zip_archive: Path):
        entries = archive_io.list_contents(
            tmp_zip_archive, subdir="nonexistent"
        )
        assert entries == []

    def test_file_has_size(self, tmp_zip_archive: Path):
        entries = archive_io.list_contents(tmp_zip_archive, subdir="darks")
        dark = entries[0]
        assert dark["name"] == "dark_001.fits"
        assert dark["size"] > 0

    def test_dir_has_no_size(self, tmp_zip_archive: Path):
        entries = archive_io.list_contents(tmp_zip_archive)
        dirs = [e for e in entries if e["type"] == "dir"]
        for d in dirs:
            assert d["size"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && uv run pytest tests/test_archive_io.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'nightcrate.services.archive_io'`

- [ ] **Step 3: Write the archive_io service with detection and zip listing**

```python
# backend/src/nightcrate/services/archive_io.py
"""Archive I/O service — transparent browsing and extraction of archive files.

Supports: zip, tar (gz/bz2/zst), 7z.
Archives are treated as virtual folders. Contents are listed from the
table of contents and extracted in-memory as BytesIO buffers.
"""

from __future__ import annotations

import tarfile
import zipfile
from io import BytesIO
from pathlib import Path, PurePosixPath

import py7zr


# ── Archive detection ─────────────────────────────────────────────────

# Ordered longest-first so ".tar.gz" matches before ".gz"
_COMPOUND_SUFFIXES: list[tuple[str, str]] = [
    (".tar.gz", "tar"),
    (".tar.bz2", "tar"),
    (".tar.zst", "tar"),
]

_SIMPLE_SUFFIXES: dict[str, str] = {
    ".zip": "zip",
    ".tar": "tar",
    ".tgz": "tar",
    ".7z": "7z",
}


def _get_archive_type(path: Path) -> str | None:
    """Detect archive type from file extension. Returns 'zip', 'tar', '7z', or None."""
    name_lower = path.name.lower()
    for suffix, atype in _COMPOUND_SUFFIXES:
        if name_lower.endswith(suffix):
            return atype
    suffix = path.suffix.lower()
    return _SIMPLE_SUFFIXES.get(suffix)


def is_archive(path: Path) -> bool:
    """Return True if the path has a recognized archive extension."""
    return _get_archive_type(path) is not None


# ── Path validation ───────────────────────────────────────────────────


def _validate_entry_path(entry_path: str) -> None:
    """Reject path traversal attempts in archive entry paths."""
    parts = PurePosixPath(entry_path).parts
    if any(p == ".." for p in parts):
        raise ValueError(f"Path traversal rejected: {entry_path}")
    if PurePosixPath(entry_path).is_absolute():
        raise ValueError(f"Absolute path rejected: {entry_path}")


# ── Directory synthesis ───────────────────────────────────────────────


def _build_listing(
    all_entries: list[tuple[str, int | None]],
    subdir: str,
) -> list[dict]:
    """Build a directory listing at the given subdir level.

    all_entries: list of (full_path, uncompressed_size_or_None) for all
                 file entries in the archive. Directories are synthesized.
    subdir: directory prefix to filter by ("" for root).
    """
    prefix = (subdir.rstrip("/") + "/") if subdir else ""
    seen_dirs: set[str] = set()
    files: list[dict] = []

    for entry_path, size in all_entries:
        # Skip entries not under the requested subdir
        if not entry_path.startswith(prefix):
            continue

        # Get the relative part after the prefix
        relative = entry_path[len(prefix):]
        if not relative:
            continue

        parts = relative.split("/")
        if len(parts) == 1:
            # Direct child file
            files.append({"name": parts[0], "type": "file", "size": size})
        else:
            # Subdirectory — record the first segment
            seen_dirs.add(parts[0])

    dirs = [{"name": d, "type": "dir", "size": None} for d in sorted(seen_dirs)]
    return dirs + sorted(files, key=lambda f: f["name"])


# ── ZIP ───────────────────────────────────────────────────────────────


def _list_zip(archive_path: Path, subdir: str) -> list[dict]:
    with zipfile.ZipFile(archive_path, "r") as zf:
        entries = [
            (info.filename, info.file_size)
            for info in zf.infolist()
            if not info.is_dir()
        ]
    return _build_listing(entries, subdir)


def _extract_zip(archive_path: Path, entry_path: str) -> BytesIO:
    with zipfile.ZipFile(archive_path, "r") as zf:
        try:
            data = zf.read(entry_path)
        except KeyError:
            raise FileNotFoundError(
                f"Entry not found in archive: {entry_path}"
            )
    buf = BytesIO(data)
    buf.seek(0)
    return buf


# ── TAR ───────────────────────────────────────────────────────────────


def _tar_mode(archive_path: Path) -> str:
    """Determine tarfile open mode from extension."""
    name_lower = archive_path.name.lower()
    if name_lower.endswith(".tar.gz") or name_lower.endswith(".tgz"):
        return "r:gz"
    if name_lower.endswith(".tar.bz2"):
        return "r:bz2"
    if name_lower.endswith(".tar.zst"):
        return "r:zst"
    return "r:"


def _list_tar(archive_path: Path, subdir: str) -> list[dict]:
    with tarfile.open(archive_path, _tar_mode(archive_path)) as tf:
        entries = [
            (m.name, m.size)
            for m in tf.getmembers()
            if m.isfile()
        ]
    return _build_listing(entries, subdir)


def _extract_tar(archive_path: Path, entry_path: str) -> BytesIO:
    with tarfile.open(archive_path, _tar_mode(archive_path)) as tf:
        try:
            member = tf.getmember(entry_path)
        except KeyError:
            raise FileNotFoundError(
                f"Entry not found in archive: {entry_path}"
            )
        if not member.isfile():
            raise ValueError(f"Entry is not a file: {entry_path}")
        f = tf.extractfile(member)
        if f is None:
            raise ValueError(f"Cannot extract entry: {entry_path}")
        buf = BytesIO(f.read())
        buf.seek(0)
        return buf


# ── 7z ────────────────────────────────────────────────────────────────


def _list_7z(archive_path: Path, subdir: str) -> list[dict]:
    with py7zr.SevenZipFile(archive_path, "r") as sz:
        entries = [
            (entry.filename, entry.uncompressed)
            for entry in sz.list()
            if not entry.is_directory
        ]
    return _build_listing(entries, subdir)


def _extract_7z(archive_path: Path, entry_path: str) -> BytesIO:
    with py7zr.SevenZipFile(archive_path, "r") as sz:
        result = sz.read(targets=[entry_path])
    if not result or entry_path not in result:
        raise FileNotFoundError(
            f"Entry not found in archive: {entry_path}"
        )
    buf = result[entry_path]
    buf.seek(0)
    return buf


# ── Public API ────────────────────────────────────────────────────────

_LIST_DISPATCH = {"zip": _list_zip, "tar": _list_tar, "7z": _list_7z}
_EXTRACT_DISPATCH = {"zip": _extract_zip, "tar": _extract_tar, "7z": _extract_7z}


def list_contents(
    archive_path: Path, subdir: str = ""
) -> list[dict]:
    """List entries at a directory level within an archive.

    Returns list of dicts: {"name": str, "type": "file"|"dir", "size": int|None}
    Directories are synthesized from entry paths.
    """
    atype = _get_archive_type(archive_path)
    if atype is None:
        raise ValueError(f"Not a recognized archive: {archive_path}")
    if subdir:
        _validate_entry_path(subdir)
    return _LIST_DISPATCH[atype](archive_path, subdir)


def extract_entry(archive_path: Path, entry_path: str) -> BytesIO:
    """Extract a single file from an archive into a BytesIO buffer.

    Returns the buffer seeked to position 0, ready for reading.
    Raises FileNotFoundError if the entry doesn't exist.
    Raises ValueError if the entry is a directory or path is invalid.
    """
    _validate_entry_path(entry_path)
    atype = _get_archive_type(archive_path)
    if atype is None:
        raise ValueError(f"Not a recognized archive: {archive_path}")
    return _EXTRACT_DISPATCH[atype](archive_path, entry_path)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_archive_io.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/nightcrate/services/archive_io.py backend/tests/test_archive_io.py
git commit -m "Add archive_io service with zip listing and detection"
```

---

## Task 3: Archive I/O — tar and 7z listing tests

**Files:**
- Modify: `backend/tests/test_archive_io.py`

- [ ] **Step 1: Add tar.gz and 7z fixtures and listing tests**

Append to `backend/tests/test_archive_io.py` after the existing fixtures:

```python
import tarfile as tarfile_mod


@pytest.fixture
def tmp_tar_gz_archive(tmp_path: Path, tmp_fits_bytes: bytes) -> Path:
    """Create a tar.gz archive with nested dirs and a FITS file."""
    archive_path = tmp_path / "test_archive.tar.gz"
    with tarfile_mod.open(archive_path, "w:gz") as tf:
        for name in [
            "lights/target/image_001.fits",
            "lights/flats/flat_001.fits",
            "darks/dark_001.fits",
        ]:
            info = tarfile_mod.TarInfo(name=name)
            info.size = len(tmp_fits_bytes)
            tf.addfile(info, BytesIO(tmp_fits_bytes))
    return archive_path


@pytest.fixture
def tmp_7z_archive(tmp_path: Path, tmp_fits_bytes: bytes) -> Path:
    """Create a 7z archive with nested dirs and a FITS file."""
    archive_path = tmp_path / "test_archive.7z"
    with py7zr.SevenZipFile(archive_path, "w") as sz:
        for name in [
            "lights/target/image_001.fits",
            "lights/flats/flat_001.fits",
            "darks/dark_001.fits",
        ]:
            sz.writestr(BytesIO(tmp_fits_bytes), name)
    return archive_path
```

Add import at top:

```python
import py7zr
```

Add test classes:

```python
class TestListContentsTarGz:
    def test_root_level(self, tmp_tar_gz_archive: Path):
        entries = archive_io.list_contents(tmp_tar_gz_archive)
        names = {e["name"] for e in entries}
        assert names == {"lights", "darks"}

    def test_subdir(self, tmp_tar_gz_archive: Path):
        entries = archive_io.list_contents(
            tmp_tar_gz_archive, subdir="lights/target"
        )
        assert len(entries) == 1
        assert entries[0]["name"] == "image_001.fits"
        assert entries[0]["type"] == "file"


class TestListContents7z:
    def test_root_level(self, tmp_7z_archive: Path):
        entries = archive_io.list_contents(tmp_7z_archive)
        names = {e["name"] for e in entries}
        assert names == {"lights", "darks"}

    def test_subdir(self, tmp_7z_archive: Path):
        entries = archive_io.list_contents(
            tmp_7z_archive, subdir="lights/target"
        )
        assert len(entries) == 1
        assert entries[0]["name"] == "image_001.fits"
        assert entries[0]["type"] == "file"
```

- [ ] **Step 2: Run tests**

```bash
cd backend && uv run pytest tests/test_archive_io.py -v
```

Expected: all tests PASS (including new tar.gz and 7z tests).

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_archive_io.py
git commit -m "Add tar.gz and 7z listing tests"
```

---

## Task 4: Archive I/O — extraction tests

**Files:**
- Modify: `backend/tests/test_archive_io.py`

- [ ] **Step 1: Add extraction and security tests**

Append to `backend/tests/test_archive_io.py`:

```python
class TestExtractEntry:
    def test_extract_zip(self, tmp_zip_archive: Path):
        buf = archive_io.extract_entry(
            tmp_zip_archive, "lights/target/image_001.fits"
        )
        assert isinstance(buf, BytesIO)
        assert buf.tell() == 0
        content = buf.read()
        assert len(content) > 0

    def test_extract_tar_gz(self, tmp_tar_gz_archive: Path):
        buf = archive_io.extract_entry(
            tmp_tar_gz_archive, "lights/target/image_001.fits"
        )
        assert isinstance(buf, BytesIO)
        content = buf.read()
        assert len(content) > 0

    def test_extract_7z(self, tmp_7z_archive: Path):
        buf = archive_io.extract_entry(
            tmp_7z_archive, "lights/target/image_001.fits"
        )
        assert isinstance(buf, BytesIO)
        content = buf.read()
        assert len(content) > 0

    def test_extract_not_found(self, tmp_zip_archive: Path):
        with pytest.raises(FileNotFoundError):
            archive_io.extract_entry(tmp_zip_archive, "nonexistent.fits")

    def test_extracted_fits_is_valid(
        self, tmp_zip_archive: Path
    ):
        """Verify extracted FITS can be opened by astropy."""
        buf = archive_io.extract_entry(
            tmp_zip_archive, "lights/target/image_001.fits"
        )
        hdul = fits.open(buf, memmap=False)
        assert hdul[0].data is not None
        assert hdul[0].data.shape == (20, 30)
        assert hdul[0].header["OBJECT"] == "TestStar"
        hdul.close()


class TestPathTraversal:
    def test_dotdot_rejected(self, tmp_zip_archive: Path):
        with pytest.raises(ValueError, match="traversal"):
            archive_io.extract_entry(
                tmp_zip_archive, "../../../etc/passwd"
            )

    def test_absolute_path_rejected(self, tmp_zip_archive: Path):
        with pytest.raises(ValueError, match="Absolute"):
            archive_io.extract_entry(
                tmp_zip_archive, "/etc/passwd"
            )

    def test_dotdot_in_subdir_rejected(self, tmp_zip_archive: Path):
        with pytest.raises(ValueError, match="traversal"):
            archive_io.list_contents(
                tmp_zip_archive, subdir="lights/../../etc"
            )
```

- [ ] **Step 2: Run tests**

```bash
cd backend && uv run pytest tests/test_archive_io.py -v
```

Expected: all tests PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_archive_io.py
git commit -m "Add archive extraction and path traversal tests"
```

---

## Task 5: Widen fits_io to accept BinaryIO

**Files:**
- Modify: `backend/src/nightcrate/services/fits_io.py`
- Modify: `backend/tests/test_archive_io.py`

- [ ] **Step 1: Write failing test — load FITS from BytesIO**

Append to `backend/tests/test_archive_io.py`:

```python
from nightcrate.services import fits_io


class TestFitsFromBinaryIO:
    def test_load_image_data_from_bytesio(self, tmp_fits_bytes: bytes):
        buf = BytesIO(tmp_fits_bytes)
        data = fits_io.load_image_data(buf)
        assert data.shape == (20, 30)
        assert data.dtype == np.float64
        assert 0.0 <= data.max() <= 1.0

    def test_read_header_from_bytesio(self, tmp_fits_bytes: bytes):
        buf = BytesIO(tmp_fits_bytes)
        cards = fits_io.read_header(buf)
        keys = [c["key"] for c in cards]
        assert "OBJECT" in keys

    def test_list_extensions_from_bytesio(self, tmp_fits_bytes: bytes):
        buf = BytesIO(tmp_fits_bytes)
        exts = fits_io.list_extensions(buf)
        assert len(exts) >= 1
        assert exts[0]["has_image"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && uv run pytest tests/test_archive_io.py::TestFitsFromBinaryIO -v
```

Expected: FAIL — `TypeError` because `fits_io` functions expect `Path`, not `BytesIO`.

- [ ] **Step 3: Widen fits_io signatures**

In `backend/src/nightcrate/services/fits_io.py`, add `BinaryIO` import and update the three public functions:

Add to imports:

```python
from typing import BinaryIO
```

Change function signatures:

```python
def load_image_data(source: Path | BinaryIO, hdu: int = 0) -> np.ndarray:
```

```python
def read_header(source: Path | BinaryIO, hdu: int = 0) -> list[dict]:
```

```python
def list_extensions(source: Path | BinaryIO) -> list[dict]:
```

The internal code already uses `fits.open(file_path, memmap=False)` — astropy accepts both `Path` and file-like objects, so just rename the parameter from `file_path` to `source` and pass it through. No logic changes needed.

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_archive_io.py::TestFitsFromBinaryIO -v
```

Expected: PASS.

- [ ] **Step 5: Run existing fits_io tests to verify no regression**

```bash
cd backend && uv run pytest tests/test_fits_io.py -v
```

Expected: all existing tests still PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/src/nightcrate/services/fits_io.py backend/tests/test_archive_io.py
git commit -m "Widen fits_io to accept Path | BinaryIO"
```

---

## Task 6: Widen xisf_io to accept BinaryIO

**Files:**
- Modify: `backend/src/nightcrate/services/xisf_io.py`
- Modify: `backend/tests/test_archive_io.py`

- [ ] **Step 1: Write failing test — load XISF from BytesIO**

First, create an XISF fixture. Append to `backend/tests/test_archive_io.py`:

```python
from nightcrate.services import xisf_io


@pytest.fixture
def tmp_xisf_bytes(tmp_path: Path) -> bytes:
    """Read the test XISF fixture into bytes."""
    # Use the existing test fixture from test_xisf_io tests
    xisf_path = Path(__file__).parent / "fixtures" / "test_mono_uncompressed.xisf"
    if not xisf_path.exists():
        pytest.skip("XISF test fixture not available")
    return xisf_path.read_bytes()


class TestXisfFromBinaryIO:
    def test_load_image_data_from_bytesio(self, tmp_xisf_bytes: bytes):
        buf = BytesIO(tmp_xisf_bytes)
        data = xisf_io.load_image_data(buf)
        assert data.ndim >= 2
        assert data.dtype == np.float64

    def test_read_header_from_bytesio(self, tmp_xisf_bytes: bytes):
        buf = BytesIO(tmp_xisf_bytes)
        cards = xisf_io.read_header(buf)
        assert isinstance(cards, list)

    def test_list_extensions_from_bytesio(self, tmp_xisf_bytes: bytes):
        buf = BytesIO(tmp_xisf_bytes)
        exts = xisf_io.list_extensions(buf)
        assert len(exts) >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && uv run pytest tests/test_archive_io.py::TestXisfFromBinaryIO -v
```

Expected: FAIL — `TypeError` or `AttributeError`.

- [ ] **Step 3: Widen xisf_io signatures**

In `backend/src/nightcrate/services/xisf_io.py`:

Add import:

```python
from typing import BinaryIO
```

Update `_parse_xml_header` to accept `Path | BinaryIO`:

```python
def _parse_xml_header(source: Path | BinaryIO) -> tuple[Element, int]:
    """Read and parse the XISF XML header."""
    if isinstance(source, Path):
        f = open(source, "rb")
        owns_file = True
    else:
        f = source
        owns_file = False
    try:
        magic = f.read(8)
        if magic != XISF_MAGIC:
            raise XisfError("Not a valid XISF file")
        header_len_bytes = f.read(4)
        _reserved = f.read(4)
        header_len = struct.unpack("<I", header_len_bytes)[0]
        xml_bytes = f.read(header_len)
        header_end = f.tell()
    finally:
        if owns_file:
            f.close()
    root = ET.fromstring(xml_bytes)
    return root, header_end
```

Update `load_image_data` — the function opens the file a second time to seek to data offset. Refactor to accept `Path | BinaryIO`:

```python
def load_image_data(source: Path | BinaryIO, hdu: int = 0) -> np.ndarray:
```

Inside the function, replace `open(file_path, "rb")` with:

```python
    if isinstance(source, Path):
        f = open(source, "rb")
        owns_file = True
    else:
        f = source
        owns_file = False
    try:
        # ... existing seek/read logic using f ...
    finally:
        if owns_file:
            f.close()
```

Important: when source is BinaryIO, pass `source` to `_parse_xml_header()` too — but note that `_parse_xml_header` consumes bytes, so for BinaryIO the file position is already advanced. The data_offset in XISF is relative to file start, so `f.seek(data_offset)` works correctly on BytesIO.

Update `read_header` and `list_extensions` similarly:

```python
def read_header(source: Path | BinaryIO, hdu: int = 0) -> list[dict]:
def list_extensions(source: Path | BinaryIO) -> list[dict]:
```

These only call `_parse_xml_header()`, so the changes are straightforward — pass `source` through.

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_archive_io.py::TestXisfFromBinaryIO -v
```

Expected: PASS (or skip if fixture not available).

- [ ] **Step 5: Run existing xisf_io tests to verify no regression**

```bash
cd backend && uv run pytest tests/test_xisf_io.py -v
```

Expected: all existing tests still PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/src/nightcrate/services/xisf_io.py backend/tests/test_archive_io.py
git commit -m "Widen xisf_io to accept Path | BinaryIO"
```

---

## Task 7: Widen standard_io to accept BinaryIO

**Files:**
- Modify: `backend/src/nightcrate/services/standard_io.py`
- Modify: `backend/tests/test_archive_io.py`

- [ ] **Step 1: Write failing test — load PNG from BytesIO**

Append to `backend/tests/test_archive_io.py`:

```python
from PIL import Image

from nightcrate.services import standard_io


@pytest.fixture
def tmp_png_bytes() -> bytes:
    """Create a minimal PNG in memory."""
    img = Image.new("RGB", (40, 30), color=(128, 64, 32))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestStandardFromBinaryIO:
    def test_load_image_as_array_from_bytesio(self, tmp_png_bytes: bytes):
        buf = BytesIO(tmp_png_bytes)
        data = standard_io.load_image_as_array(buf)
        assert data.ndim >= 2
        assert data.dtype == np.float64

    def test_list_extensions_from_bytesio(self, tmp_png_bytes: bytes):
        buf = BytesIO(tmp_png_bytes)
        exts = standard_io.list_extensions(buf)
        assert len(exts) == 1
        assert exts[0]["has_image"] is True

    def test_read_header_from_bytesio(self, tmp_png_bytes: bytes):
        buf = BytesIO(tmp_png_bytes)
        cards = standard_io.read_header(buf)
        assert isinstance(cards, list)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && uv run pytest tests/test_archive_io.py::TestStandardFromBinaryIO -v
```

Expected: FAIL.

- [ ] **Step 3: Widen standard_io signatures**

In `backend/src/nightcrate/services/standard_io.py`:

Add import:

```python
from typing import BinaryIO
```

Update function signatures:

```python
def is_float_tiff(source: Path | BinaryIO) -> bool:
def load_image_data(source: Path | BinaryIO) -> np.ndarray:
def load_image_as_array(source: Path | BinaryIO) -> np.ndarray:
def load_image_bytes(source: Path | BinaryIO) -> bytes:
def read_header(source: Path | BinaryIO) -> list[dict]:
def list_extensions(source: Path | BinaryIO) -> list[dict]:
```

Key changes inside functions:

- `is_float_tiff`: `tifffile.TiffFile()` accepts file-like objects. Replace `str(file_path)` with `source`.
- `load_image_data`: `tifffile.imread()` accepts file-like objects. Replace `str(file_path)` with `source`.
- `load_image_as_array`: `Image.open()` accepts file-like objects. Pass `source` directly.
- `load_image_bytes`: Same as above.
- `read_header`: For BinaryIO, skip EXIF/PNG text extraction (metadata reading from raw bytes is best-effort). Return empty list for BinaryIO inputs.
- `list_extensions`: For BinaryIO, return a generic entry. The `name` field can use `"Image"` as a fallback when no path is available.

For `list_extensions`, handle the case where `source` is BinaryIO (no `.stem` attribute):

```python
def list_extensions(source: Path | BinaryIO) -> list[dict]:
    name = source.stem if isinstance(source, Path) else "Image"
    return [{"index": 0, "name": name, "type": "Standard image",
             "has_image": True}]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_archive_io.py::TestStandardFromBinaryIO -v
```

Expected: PASS.

- [ ] **Step 5: Run existing standard_io tests to verify no regression**

```bash
cd backend && uv run pytest tests/test_standard_io.py -v
```

Expected: all existing tests still PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/src/nightcrate/services/standard_io.py backend/tests/test_archive_io.py
git commit -m "Widen standard_io to accept Path | BinaryIO"
```

---

## Task 8: API — browse-archive endpoint

**Files:**
- Modify: `backend/src/nightcrate/api/files.py`
- Create: `backend/tests/test_archive_api.py`

- [ ] **Step 1: Write failing tests for browse-archive and archive detection**

```python
# backend/tests/test_archive_api.py
"""Tests for archive browsing API endpoints."""

import zipfile
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits
from httpx import ASGITransport, AsyncClient

from nightcrate.main import app


@pytest.fixture
def tmp_fits_bytes() -> bytes:
    """Create minimal FITS bytes."""
    data = np.zeros((20, 30), dtype=np.uint16)
    hdu = fits.PrimaryHDU(data)
    buf = BytesIO()
    hdu.writeto(buf)
    return buf.getvalue()


@pytest.fixture
def tmp_zip_with_fits(tmp_path: Path, tmp_fits_bytes: bytes) -> Path:
    """Create a zip archive containing FITS files in subdirs."""
    archive_path = tmp_path / "session.zip"
    with zipfile.ZipFile(archive_path, "w") as zf:
        zf.writestr("lights/image_001.fits", tmp_fits_bytes)
        zf.writestr("lights/image_002.fits", tmp_fits_bytes)
        zf.writestr("darks/dark_001.fits", tmp_fits_bytes)
    return archive_path


@pytest.fixture
def tmp_dir_with_archive(
    tmp_path: Path, tmp_zip_with_fits: Path
) -> Path:
    """Create a directory containing an archive file."""
    browse_dir = tmp_path / "browse_test"
    browse_dir.mkdir()
    dest = browse_dir / "session.zip"
    dest.symlink_to(tmp_zip_with_fits)
    # Also create a regular subdir and a FITS file
    (browse_dir / "subdir").mkdir()
    return browse_dir


@pytest.mark.asyncio
class TestBrowseDetectsArchives:
    async def test_archives_in_browse_response(
        self, tmp_dir_with_archive: Path
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/files/browse",
                params={"path": str(tmp_dir_with_archive)},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "archives" in data
        archive_names = [a["name"] for a in data["archives"]]
        assert "session.zip" in archive_names


@pytest.mark.asyncio
class TestBrowseArchive:
    async def test_root_listing(self, tmp_zip_with_fits: Path):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/files/browse-archive",
                params={"path": str(tmp_zip_with_fits)},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["path"] == str(tmp_zip_with_fits)
        assert data["subdir"] == ""
        assert data["parent"] is None
        dir_names = [d["name"] for d in data["dirs"]]
        assert "lights" in dir_names
        assert "darks" in dir_names

    async def test_subdir_listing(self, tmp_zip_with_fits: Path):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/files/browse-archive",
                params={
                    "path": str(tmp_zip_with_fits),
                    "subdir": "lights",
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["subdir"] == "lights"
        assert data["parent"] == ""
        file_names = [f["name"] for f in data["files"]]
        assert "image_001.fits" in file_names
        assert "image_002.fits" in file_names

    async def test_nested_parent(self, tmp_zip_with_fits: Path):
        """Verify parent computation for nested subdirs."""
        # Create a deeper archive for this test
        archive_path = tmp_zip_with_fits.parent / "deep.zip"
        with zipfile.ZipFile(archive_path, "w") as zf:
            zf.writestr("a/b/c/file.fits", b"dummy")
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/files/browse-archive",
                params={"path": str(archive_path), "subdir": "a/b"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["parent"] == "a"

    async def test_invalid_archive(self, tmp_path: Path):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/files/browse-archive",
                params={"path": str(tmp_path / "nonexistent.zip")},
            )
        assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && uv run pytest tests/test_archive_api.py -v
```

Expected: FAIL — endpoints don't exist yet.

- [ ] **Step 3: Add archives to browse response and create browse-archive endpoint**

In `backend/src/nightcrate/api/files.py`:

Add import:

```python
from nightcrate.services import archive_io
```

In the `browse()` function, after the existing loop that builds `dirs`, `files`, `projects`, add archive detection:

```python
    archives = []
    for entry in sorted(resolved.iterdir()):
        if entry.name.startswith("."):
            continue
        if entry.is_file() and archive_io.is_archive(entry):
            archives.append({"name": entry.name, "path": str(entry)})
```

Add `"archives": archives` to the return dict.

Add the new endpoint:

```python
@router.get("/browse-archive")
async def browse_archive(
    path: str = Query(...),
    subdir: str = Query(default=""),
) -> dict:
    """List contents of an archive at the given subdirectory level."""
    archive_path = Path(path).expanduser().resolve()
    if not archive_path.is_file():
        raise HTTPException(status_code=404, detail=f"Archive not found: {path}")
    if not archive_io.is_archive(archive_path):
        raise HTTPException(status_code=400, detail=f"Not a recognized archive: {path}")

    entries = archive_io.list_contents(archive_path, subdir)
    dirs = [e for e in entries if e["type"] == "dir"]
    files = [e for e in entries if e["type"] == "file"]

    # Compute parent subdir
    if not subdir:
        parent = None
    elif "/" in subdir:
        parent = subdir.rsplit("/", 1)[0]
    else:
        parent = ""

    return {
        "path": str(archive_path),
        "subdir": subdir,
        "parent": parent,
        "dirs": dirs,
        "files": files,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_archive_api.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/nightcrate/api/files.py backend/tests/test_archive_api.py
git commit -m "Add browse-archive endpoint and archive detection in browse"
```

---

## Task 9: API — archive virtual path resolution in images.py

**Files:**
- Modify: `backend/src/nightcrate/api/images.py`
- Modify: `backend/tests/test_archive_api.py`

- [ ] **Step 1: Write failing test — load image from archive virtual path**

Append to `backend/tests/test_archive_api.py`:

```python
@pytest.mark.asyncio
class TestArchiveImageLoading:
    async def test_extensions_from_archive(self, tmp_zip_with_fits: Path):
        virtual_path = f"{tmp_zip_with_fits}::lights/image_001.fits"
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/images/extensions",
                params={"path": virtual_path},
            )
        assert resp.status_code == 200
        exts = resp.json()
        assert len(exts) >= 1
        assert exts[0]["has_image"] is True

    async def test_stats_from_archive(self, tmp_zip_with_fits: Path):
        virtual_path = f"{tmp_zip_with_fits}::lights/image_001.fits"
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/images/stats",
                params={"path": virtual_path},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "channels" in data

    async def test_image_render_from_archive(self, tmp_zip_with_fits: Path):
        virtual_path = f"{tmp_zip_with_fits}::lights/image_001.fits"
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/images/image",
                params={"path": virtual_path},
            )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"
        assert len(resp.content) > 0

    async def test_header_from_archive(self, tmp_zip_with_fits: Path):
        virtual_path = f"{tmp_zip_with_fits}::lights/image_001.fits"
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/images/header",
                params={"path": virtual_path},
            )
        assert resp.status_code == 200

    async def test_invalid_entry_path(self, tmp_zip_with_fits: Path):
        virtual_path = f"{tmp_zip_with_fits}::nonexistent.fits"
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/images/extensions",
                params={"path": virtual_path},
            )
        assert resp.status_code in (404, 500)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && uv run pytest tests/test_archive_api.py::TestArchiveImageLoading -v
```

Expected: FAIL — `_resolve_path()` doesn't handle archive virtual paths.

- [ ] **Step 3: Update _resolve_path() and add _file_type_from_ext()**

In `backend/src/nightcrate/api/images.py`:

Add import:

```python
from nightcrate.services import archive_io
from typing import BinaryIO
```

Add the new helper function (after existing `_file_type`):

```python
def _file_type_from_ext(entry_name: str) -> str:
    """Determine file type purely from extension (no disk check)."""
    suffix = Path(entry_name).suffix.lower()
    if suffix in FITS_EXTENSIONS:
        return "fits"
    if suffix in XISF_EXTENSIONS:
        return "xisf"
    if suffix in STANDARD_EXTENSIONS:
        # Cannot check float TIFF without reading the file — treat as
        # standard initially; float detection happens in load path
        if suffix in {".tif", ".tiff"}:
            return "tiff_unknown"
        return "standard"
    raise HTTPException(
        status_code=422,
        detail=f"Unsupported image format in archive: {entry_name}",
    )
```

Update `_resolve_path()` to handle archive virtual paths:

```python
def _resolve_path(path: str) -> tuple[Path | BinaryIO, str, int]:
    """Resolve a file path or virtual path to (source, file_type, index)."""
    if "::" in path:
        left, right = path.split("::", 1)
        left_path = Path(left)

        # Existing pxiproject handling
        if left_path.is_dir() and left_path.suffix == ".pxiproject":
            if not left_path.is_absolute():
                raise HTTPException(status_code=400, detail="Path must be absolute")
            idx = int(right)
            return left_path, "pxiproject", idx

        # Archive handling
        if archive_io.is_archive(left_path):
            if not left_path.is_absolute():
                raise HTTPException(status_code=400, detail="Path must be absolute")
            if not left_path.is_file():
                raise HTTPException(status_code=404, detail=f"Archive not found: {left}")
            try:
                buf = archive_io.extract_entry(left_path, right)
            except FileNotFoundError:
                raise HTTPException(status_code=404, detail=f"Entry not found: {right}")
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            ft = _file_type_from_ext(right)
            # Handle TIFF float detection on in-memory data
            if ft == "tiff_unknown":
                ft = _detect_tiff_type_from_buf(buf)
            return buf, ft, 0

    # Existing single-file handling (unchanged)
    ...
```

Add TIFF detection helper:

```python
def _detect_tiff_type_from_buf(buf: BinaryIO) -> str:
    """Detect float vs standard TIFF from in-memory data."""
    import tifffile
    try:
        with tifffile.TiffFile(buf) as tif:
            is_float = tif.pages[0].dtype.kind == "f"
        buf.seek(0)
        return "float_tiff" if is_float else "standard"
    except Exception:
        buf.seek(0)
        return "standard"
```

Update `_load_image_data()` to handle `BinaryIO` source:

```python
def _load_image_data(
    p: Path | BinaryIO, ft: str, idx: int, hdu: int
) -> np.ndarray:
```

The existing dispatch branches already call `fits_io.load_image_data(p, hdu)` etc. — since those now accept `Path | BinaryIO`, no logic changes are needed inside `_load_image_data`. Just update the type hint.

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_archive_api.py::TestArchiveImageLoading -v
```

Expected: PASS.

- [ ] **Step 5: Run full test suite**

```bash
cd backend && uv run pytest -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/src/nightcrate/api/images.py backend/tests/test_archive_api.py
git commit -m "Add archive virtual path resolution to images API"
```

---

## Task 10: Frontend — API client and types

**Files:**
- Modify: `frontend/src/api/files.ts`

- [ ] **Step 1: Add ArchiveBrowseResult type and browseArchive function**

In `frontend/src/api/files.ts`, add the new interface alongside existing ones:

```typescript
export interface ArchiveEntry {
  name: string;
  path: string;
}

export interface ArchiveDirEntry {
  name: string;
}

export interface ArchiveFileEntry {
  name: string;
  size: number | null;
}

export interface ArchiveBrowseResult {
  path: string;
  subdir: string;
  parent: string | null;
  dirs: ArchiveDirEntry[];
  files: ArchiveFileEntry[];
}
```

Add `archives` to the existing `BrowseResult` interface:

```typescript
export interface BrowseResult {
  path: string;
  parent: string | null;
  dirs: DirEntry[];
  files: FileEntry[];
  projects: ProjectEntry[];
  archives: ArchiveEntry[];  // NEW
}
```

Add the API function:

```typescript
export async function browseArchive(
  archivePath: string,
  subdir: string = ""
): Promise<ArchiveBrowseResult> {
  return apiFetch<ArchiveBrowseResult>(
    `/files/browse-archive?path=${encodeURIComponent(archivePath)}&subdir=${encodeURIComponent(subdir)}`
  );
}
```

- [ ] **Step 2: Verify frontend builds**

```bash
cd frontend && npm run build
```

Expected: build succeeds. (Any references to `result.archives` in FileBrowser will come in next task.)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/files.ts
git commit -m "Add archive browse API types and client function"
```

---

## Task 11: Frontend — FileBrowser archive mode

**Files:**
- Modify: `frontend/src/components/fits/FileBrowser.tsx`

- [ ] **Step 1: Add archive state and data fetching**

In `FileBrowser.tsx`, add state variables alongside the existing `activeProject` state:

```typescript
const [activeArchive, setActiveArchive] = useState<string | null>(null);
const [archiveSubdir, setArchiveSubdir] = useState<string>("");
const [archiveResult, setArchiveResult] = useState<ArchiveBrowseResult | null>(null);
const [archiveLoading, setArchiveLoading] = useState(false);
```

Add import for `browseArchive` and `ArchiveBrowseResult` from `../../api/files`.

Add import for `FolderZip as FolderZipIcon` from `@mui/icons-material`.

Add effect hook for fetching archive contents (after the existing project effect):

```typescript
useEffect(() => {
  if (!activeArchive) return;
  setArchiveLoading(true);
  browseArchive(activeArchive, archiveSubdir)
    .then((data) => {
      setArchiveResult(data);
      setArchiveLoading(false);
    })
    .catch((err) => {
      setError(err.message || "Failed to browse archive");
      setArchiveLoading(false);
    });
}, [activeArchive, archiveSubdir]);
```

Update `navigateTo()` to also clear archive state:

```typescript
const navigateTo = (path: string) => {
  setCurrentPath(path);
  setSelectedFile(null);
  setSelectedDisplayName(null);
  setActiveProject(null);
  setActiveArchive(null);     // NEW
  setArchiveSubdir("");       // NEW
  setArchiveResult(null);     // NEW
};
```

- [ ] **Step 2: Add archive entries to directory listing**

In the directory listing render section (where `result.projects` are rendered), add archive entries after projects:

```typescript
{result.archives.map((archive) => (
  <ListItemButton
    key={archive.path}
    onClick={() => {
      setActiveArchive(archive.path);
      setArchiveSubdir("");
    }}
  >
    <ListItemIcon>
      <FolderZipIcon />
    </ListItemIcon>
    <ListItemText primary={archive.name} />
  </ListItemButton>
))}
```

- [ ] **Step 3: Add archive browse mode rendering**

Add a new rendering branch for archive mode. After the existing project browse section, add:

```typescript
{activeArchive && !archiveLoading && archiveResult && (
  <>
    {/* Back button */}
    <ListItemButton
      onClick={() => {
        if (archiveResult.parent !== null) {
          setArchiveSubdir(archiveResult.parent);
        } else {
          setActiveArchive(null);
          setArchiveResult(null);
        }
      }}
    >
      <ListItemIcon>
        <ArrowBackIcon />
      </ListItemIcon>
      <ListItemText primary="Back" />
    </ListItemButton>

    {/* Directories within archive */}
    {archiveResult.dirs.map((dir) => (
      <ListItemButton
        key={dir.name}
        onClick={() => {
          const newSubdir = archiveSubdir
            ? `${archiveSubdir}/${dir.name}`
            : dir.name;
          setArchiveSubdir(newSubdir);
        }}
      >
        <ListItemIcon>
          <FolderIcon />
        </ListItemIcon>
        <ListItemText primary={dir.name} />
      </ListItemButton>
    ))}

    {/* Files within archive */}
    {archiveResult.files.map((file) => {
      const entryPath = archiveSubdir
        ? `${archiveSubdir}/${file.name}`
        : file.name;
      const virtualPath = `${activeArchive}::${entryPath}`;
      return (
        <ListItemButton
          key={file.name}
          selected={selectedFile === virtualPath}
          onClick={() => {
            setSelectedFile(virtualPath);
            setSelectedDisplayName(file.name);
          }}
          onDoubleClick={() => onSelect(virtualPath, file.name)}
        >
          <ListItemIcon>
            <ImageIcon />
          </ListItemIcon>
          <ListItemText
            primary={file.name}
            secondary={
              file.size != null
                ? `${(file.size / 1024 / 1024).toFixed(1)} MB`
                : undefined
            }
          />
        </ListItemButton>
      );
    })}
  </>
)}

{activeArchive && archiveLoading && (
  <Box sx={{ display: "flex", justifyContent: "center", p: 4 }}>
    <CircularProgress />
  </Box>
)}
```

- [ ] **Step 4: Update breadcrumb for archive mode**

In the breadcrumb section, add archive path segments when `activeArchive` is set. After the existing path segments:

```typescript
{activeArchive && (
  <>
    <Chip
      icon={<FolderZipIcon />}
      label={activeArchive.split("/").pop()}
      size="small"
      onClick={() => setArchiveSubdir("")}
    />
    {archiveSubdir &&
      archiveSubdir.split("/").map((segment, i, arr) => (
        <Chip
          key={i}
          label={segment}
          size="small"
          onClick={() =>
            setArchiveSubdir(arr.slice(0, i + 1).join("/"))
          }
        />
      ))}
  </>
)}
```

- [ ] **Step 5: Update handleOpen to work with archive selections**

The existing `handleOpen()` already calls `onSelect(selectedFile, selectedDisplayName)` — this works as-is since `selectedFile` will contain the archive virtual path.

- [ ] **Step 6: Verify frontend builds**

```bash
cd frontend && npm run build
```

Expected: build succeeds.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/fits/FileBrowser.tsx
git commit -m "Add archive browse mode to FileBrowser"
```

---

## Task 12: Update README and run final checks

**Files:**
- Modify: `README.md`
- Modify: `PLAN.md`

- [ ] **Step 1: Add py7zr to README acknowledgments table**

Find the Open Source Acknowledgments table in `README.md` and add:

```markdown
| [py7zr](https://github.com/miurahr/py7zr) | LGPL-2.1+ | 7z archive extraction |
```

- [ ] **Step 2: Run all backend checks**

```bash
cd backend && uv run ruff check src/ tests/
cd backend && uv run ruff format --check src/ tests/
cd backend && uv run bandit -r src/
cd backend && uv run pytest -v
```

Expected: all pass.

- [ ] **Step 3: Run frontend build**

```bash
cd frontend && npm run build
```

Expected: build succeeds.

- [ ] **Step 4: Fix any issues found in steps 2-3**

If ruff format reports issues, run `uv run ruff format src/ tests/`. If lint issues, fix them. Re-run checks until all pass.

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "Add py7zr to README acknowledgments"
```

---

## Task 13: Update CLAUDE.md with archive viewer documentation

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add Archive Browser section to CLAUDE.md**

In the Image Viewer section of `CLAUDE.md`, after the existing format/architecture documentation, add:

```markdown
## Archive Browser

Supports browsing into archive files as if they were folders. Selecting an image inside an archive extracts it in-memory and loads it through the standard image pipeline.

**Supported formats:** zip, tar, tar.gz, tar.bz2, tar.zst, 7z

**Architecture:**
- `services/archive_io.py` — format dispatch (zip/tar/7z), TOC listing, in-memory extraction to BytesIO
- `api/files.py` — `browse-archive` endpoint, archive detection in directory browse
- `api/images.py` — archive branch in `_resolve_path()` for `::` virtual paths
- I/O services (`fits_io`, `xisf_io`, `standard_io`) accept `Path | BinaryIO`

**Virtual paths:** `{archive_path}::{entry_path}` (same `::` separator as pxiproject)

**In-memory extraction:** No temp files. Archive entries are extracted to `BytesIO` and passed directly to I/O services.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "Add archive browser documentation to CLAUDE.md"
```
