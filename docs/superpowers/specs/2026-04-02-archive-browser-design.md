# Archive Browser — Design Spec

**Version:** v0.6.0
**Date:** 2026-04-02
**Status:** Approved

## Overview

Archives (.zip, .tar, .tar.gz, .tar.bz2, .tar.zst, .7z) are treated as transparent folders in the file browser. Users navigate into them, browse subdirectories, and select image files — which are extracted in-memory and loaded through the existing image pipeline with full viewer support (stretch, histogram, aberration inspector, pixel inspector, statistics).

## Supported Archive Formats

| Format | Extensions | Python Module |
|--------|-----------|---------------|
| ZIP | `.zip` | `zipfile` (stdlib) |
| TAR | `.tar` | `tarfile` (stdlib) |
| TAR+gzip | `.tar.gz`, `.tgz` | `tarfile` (stdlib) |
| TAR+bzip2 | `.tar.bz2` | `tarfile` (stdlib) |
| TAR+zstd | `.tar.zst` | `tarfile` (stdlib) |
| 7z | `.7z` | `py7zr` (LGPL-2.1+) |

ZIP and TAR variants use Python stdlib only. 7z requires `py7zr` (pure Python, no external binaries).

## Virtual Path Scheme

Reuses the existing `::` separator from pxiproject support:

```
/path/to/archive.zip::subdir/image.fits
```

- Left side: absolute path to the archive file on disk
- Right side: entry path within the archive (forward slashes, no leading slash)

`_resolve_path()` in `api/images.py` already splits on `::`. It gains a new branch: if the left side has an archive extension, treat as archive. Extract the entry in-memory, detect the extracted file's type by extension, and hand off to the existing I/O pipeline.

## Backend

### New Service: `services/archive_io.py`

Single module handling all archive formats through a unified interface. Estimated ~150 lines.

#### Constants

```python
ARCHIVE_EXTENSIONS = {
    ".zip",
    ".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tar.zst",
    ".7z",
}
```

Note: `.tar.gz` etc. are compound suffixes. Detection uses `_get_archive_type(path)` which checks suffixes in longest-first order to avoid `.gz` matching alone.

#### Functions

**`is_archive(path: Path) -> bool`**

Returns True if the path has a recognized archive extension.

**`list_contents(archive_path: Path, subdir: str = "") -> list[dict]`**

Lists entries at a given directory level within the archive. Reads the archive's table of contents only — does not extract any files.

Returns a list of dicts:
```python
{
    "name": str,           # entry name (filename only, no path prefix)
    "type": "file" | "dir",
    "size": int | None,    # uncompressed size in bytes (files only)
}
```

Directories are synthesized from entry paths — archives don't always have explicit directory entries (especially zip files created on different platforms). Walk all entries, split paths, and build the directory tree for the requested subdir level.

**`extract_entry(archive_path: Path, entry_path: str) -> BytesIO`**

Extracts a single file entry from the archive into a `BytesIO` buffer. Returns the buffer seeked to position 0, ready for reading.

Raises `FileNotFoundError` if the entry doesn't exist, `ValueError` if the entry is a directory.

**Security:** Validates that `entry_path` doesn't contain path traversal sequences (`..`, absolute paths). Rejects entries with suspicious names.

#### Format Dispatch

Internal helper `_get_archive_type(path: Path) -> str` returns `"zip"`, `"tar"`, or `"7z"`. Each format has a pair of private functions:

- `_list_zip(path, subdir)` / `_extract_zip(path, entry_path)`
- `_list_tar(path, subdir)` / `_extract_tar(path, entry_path)`
- `_list_7z(path, subdir)` / `_extract_7z(path, entry_path)`

**ZIP:** `zipfile.ZipFile.namelist()` for listing, `.read(entry_path)` for extraction (returns bytes, wrap in BytesIO).

**TAR:** `tarfile.open(path)` with appropriate mode (`r:`, `r:gz`, `r:bz2`, `r:zst`). `.getmembers()` for listing, `.extractfile(member)` for extraction (returns file-like object, read into BytesIO).

**7z:** `py7zr.SevenZipFile(path, 'r')` . `.list()` for listing, `.read(targets=[entry_path])` for extraction (returns `{name: BytesIO}` dict).

### I/O Service Changes

Widen the input type of the load/read functions from `Path` to `Path | BinaryIO` in all four I/O services:

**`fits_io.py`:**
- `load_image_data(source: Path | BinaryIO, hdu: int = 0)`
- `read_header(source: Path | BinaryIO, hdu: int = 0)`
- `list_extensions(source: Path | BinaryIO)`
- `astropy.io.fits.open()` already accepts file-like objects natively. Change is type hints + passing through.

**`xisf_io.py`:**
- `load_image_data(source: Path | BinaryIO, hdu: int = 0)`
- `read_header(source: Path | BinaryIO, hdu: int = 0)`
- `list_extensions(source: Path | BinaryIO)`
- Custom parser uses `open(path, "rb")` then `f.seek()`/`f.read()`. For BinaryIO input, skip the `open()` call and use the object directly — BytesIO supports seek/read.

**`standard_io.py`:**
- `load_image_data(source: Path | BinaryIO)`
- `load_image_as_array(source: Path | BinaryIO)`
- `read_header(source: Path | BinaryIO)`
- `list_extensions(source: Path | BinaryIO)`
- Pillow `Image.open()` and `tifffile.TiffFile()` both accept file-like objects natively.

**`pxiproject_io.py`:**
- No changes needed. A pxiproject inside an archive doesn't make sense (it's a directory bundle, not a single file).

### API Changes

**`api/files.py`:**

Add `archives` to the directory browse response:

```python
# GET /api/files/browse?path={dir_path}
{
    "path": str,
    "parent": str | None,
    "dirs": [...],
    "files": [...],
    "projects": [...],
    "archives": [{"name": str, "path": str}]  # NEW
}
```

Archives detected by extension when listing directory contents (same pattern as `.pxiproject` detection for `projects`).

New endpoint for browsing inside an archive:

```python
# GET /api/files/browse-archive?path={archive_path}&subdir={subdir}
{
    "path": str,        # archive path
    "subdir": str,      # current subdir within archive ("" for root)
    "parent": str | None,  # parent subdir, or None if at archive root
    "dirs": [{"name": str}],
    "files": [{"name": str, "size": int | None}]
}
```

**`api/images.py`:**

`_resolve_path()` updated:

```python
def _resolve_path(path: str) -> tuple[Path | BinaryIO, str, int]:
    if "::" in path:
        left, right = path.split("::", 1)
        left_path = Path(left)

        if left_path.is_dir() and left_path.suffix == ".pxiproject":
            # existing pxiproject handling
            return (left_path, "pxiproject", int(right))

        if archive_io.is_archive(left_path):
            buf = archive_io.extract_entry(left_path, right)
            file_type = _file_type_from_ext(right)
            return (buf, file_type, 0)

    # existing single-file handling
    ...
```

The return type changes from `tuple[Path, str, int]` to `tuple[Path | BinaryIO, str, int]`. All downstream endpoint functions already pass this value through to the I/O services, which now accept `Path | BinaryIO`.

`_file_type_from_ext(entry_name: str) -> str` is a new helper that determines file type purely from extension (unlike the existing `_file_type()` which also checks if the file exists on disk). For float TIFF detection on in-memory data: attempt `tifffile.TiffFile(buf)` and check dtype, then `buf.seek(0)` before returning.

### Aberration Inspector

`api/aberration.py` uses file paths as cache keys. For archive entries, the cache key becomes the full virtual path string (`archive_path::entry_path`). The aberration service calls the image loading pipeline, which handles the extraction transparently — no changes needed in aberration logic itself, only in cache key construction.

## Frontend

### FileBrowser.tsx Changes

**New state:**
```typescript
const [activeArchive, setActiveArchive] = useState<string | null>(null);
const [archiveSubdir, setArchiveSubdir] = useState<string>("");
```

**Three browse modes** (mutually exclusive):
1. **Directory mode** (existing) — `activeProject == null && activeArchive == null`
2. **Project mode** (existing) — `activeProject != null`
3. **Archive mode** (new) — `activeArchive != null`

**Archive detection in directory listing:**
- Backend returns `archives` array alongside `dirs`, `files`, `projects`
- Archives rendered with MUI `FolderZipIcon`
- Single-click on archive → `setActiveArchive(path)`, `setArchiveSubdir("")`

**Archive browsing:**
- Fetches `browseArchive(activeArchive, archiveSubdir)` on mount/subdir change
- Displays dirs and files at current level
- Click on dir → `setArchiveSubdir(newSubdir)`
- Click on file → constructs virtual path `${activeArchive}::${archiveSubdir ? archiveSubdir + '/' : ''}${file.name}` and calls `onSelect(virtualPath, file.name)`

**Breadcrumb:**
- When inside an archive: shows filesystem path up to the archive, then archive segments
- Archive name shown with zip icon to distinguish it from regular path segments
- Click archive name in breadcrumb → return to archive root
- Click segment before archive → exit archive, return to containing directory

**Back button:**
- Inside archive subdir → go up one level within archive
- At archive root → exit archive, return to containing directory

### API Client: `api/files.ts`

New function:
```typescript
export async function browseArchive(
  archivePath: string,
  subdir: string = ""
): Promise<ArchiveBrowseResult> {
  const params = new URLSearchParams({ path: archivePath, subdir });
  const res = await fetch(`/api/files/browse-archive?${params}`);
  return res.json();
}

interface ArchiveBrowseResult {
  path: string;
  subdir: string;
  parent: string | null;
  dirs: Array<{ name: string }>;
  files: Array<{ name: string; size: number | null }>;
}
```

No changes needed in `api/images.ts` — virtual paths are already passed as opaque strings.

## New Dependency

| Package | Version | License | Purpose |
|---------|---------|---------|---------|
| `py7zr` | latest | LGPL-2.1+ | 7z archive extraction |

Install: `uv add py7zr`
Update: README.md Open Source Acknowledgments table

## Security

- **Path traversal:** `archive_io.extract_entry()` validates entry paths — rejects `..` segments, absolute paths, and any path that would escape the archive root
- **Zip bombs:** Not a concern for this use case (user's own archived imaging data), but `list_contents()` should not extract — only read the TOC
- **Memory:** Astrophotography files are typically 50-200MB (26MP mono, 16-bit). These are loaded into memory for processing regardless of source, so in-memory extraction adds no overhead beyond what already exists

## Not In Scope (Future)

- **Nested archives** — archive within an archive (e.g., a zip containing a tar.gz). Would require recursive extraction and a multi-level virtual path scheme (`archive.zip::inner.tar.gz::image.fits`).
- **Archive creation or modification** — NightCrate is read-only for source data
- **Archive-aware ingestion** — cataloging sessions from archived data into the database
- **Streaming large archives** — current approach reads TOC into memory; for extremely large archives (10,000+ entries) this could be paginated
