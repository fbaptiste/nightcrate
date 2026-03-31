"""File system browsing endpoints."""

import platform
import string
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/files", tags=["files"])

IMAGE_EXTENSIONS = {".fits", ".fit", ".fts", ".xisf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}


@router.get("/volumes")
async def list_volumes() -> list[dict]:
    """List available filesystem volumes/mount points."""
    volumes: list[dict] = []
    system = platform.system()

    # Always include home first
    home = Path.home()
    volumes.append({"name": f"~ ({home.name})", "path": str(home)})

    if system == "Darwin":
        vol_root = Path("/Volumes")
        if vol_root.is_dir():
            for entry in sorted(vol_root.iterdir(), key=lambda e: e.name.lower()):
                if entry.is_dir() and not entry.name.startswith("."):
                    volumes.append({"name": entry.name, "path": str(entry)})
    elif system == "Windows":
        for letter in string.ascii_uppercase:
            drive = Path(f"{letter}:\\")
            if drive.exists():
                volumes.append({"name": f"{letter}:", "path": str(drive)})
    else:
        # Linux
        volumes.append({"name": "/", "path": "/"})
        media = Path("/media")
        if media.is_dir():
            for user_dir in media.iterdir():
                if user_dir.is_dir():
                    for mount in sorted(user_dir.iterdir()):
                        if mount.is_dir():
                            volumes.append({"name": mount.name, "path": str(mount)})
        mnt = Path("/mnt")
        if mnt.is_dir():
            for entry in sorted(mnt.iterdir()):
                if entry.is_dir():
                    volumes.append({"name": entry.name, "path": str(entry)})

    return volumes


@router.get("/browse")
async def browse(
    path: str = Query(default="~", description="Directory path to list"),
) -> dict:
    """List directory contents — subdirectories and image files only."""
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
        elif entry.is_file() and entry.suffix.lower() in IMAGE_EXTENSIONS:
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
