"""File system browsing endpoints."""

import platform
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/files", tags=["files"])

FITS_EXTENSIONS = {".fits", ".fit", ".fts"}


@router.get("/volumes")
async def list_volumes() -> list[dict]:
    """List available filesystem volumes/mount points."""
    volumes: list[dict] = []

    if platform.system() == "Darwin":
        vol_root = Path("/Volumes")
        if vol_root.is_dir():
            for entry in sorted(vol_root.iterdir(), key=lambda e: e.name.lower()):
                if entry.is_dir() and not entry.name.startswith("."):
                    volumes.append({"name": entry.name, "path": str(entry)})
        # Always include home
        home = Path.home()
        volumes.insert(0, {"name": f"~ ({home.name})", "path": str(home)})
    else:
        # Linux / other: just home and root
        home = Path.home()
        volumes.append({"name": f"~ ({home.name})", "path": str(home)})
        volumes.append({"name": "/", "path": "/"})

    return volumes


@router.get("/browse")
async def browse(
    path: str = Query(default="~", description="Directory path to list"),
) -> dict:
    """List directory contents — subdirectories and FITS files only."""
    p = Path(path).expanduser().resolve()

    if not p.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {p}")

    dirs: list[dict] = []
    files: list[dict] = []

    try:
        entries = sorted(p.iterdir(), key=lambda e: e.name.lower())
    except PermissionError:
        raise HTTPException(status_code=403, detail=f"Permission denied: {p}") from None

    for entry in entries:
        # Skip hidden files/dirs
        if entry.name.startswith("."):
            continue
        if entry.is_dir():
            dirs.append({"name": entry.name, "path": str(entry)})
        elif entry.is_file() and entry.suffix.lower() in FITS_EXTENSIONS:
            try:
                size = entry.stat().st_size
            except OSError:
                size = 0
            files.append({"name": entry.name, "path": str(entry), "size": size})

    return {
        "path": str(p),
        "parent": str(p.parent) if p != p.parent else None,
        "dirs": dirs,
        "files": files,
    }
