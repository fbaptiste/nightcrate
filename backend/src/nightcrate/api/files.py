"""File system browsing endpoints."""

import platform
import string
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from nightcrate.api.images import ALL_EXTENSIONS
from nightcrate.services import archive_io, pxiproject_io

router = APIRouter(prefix="/api/files", tags=["File Browser"])
PROJECT_EXTENSIONS = {".pxiproject"}


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
    projects: list[dict] = []
    archives: list[dict] = []

    try:
        entries = sorted(p.iterdir(), key=lambda e: e.name.lower())
    except PermissionError:
        raise HTTPException(status_code=403, detail=f"Permission denied: {p}") from None

    for entry in entries:
        # Skip hidden files/dirs
        if entry.name.startswith("."):
            continue
        if entry.is_dir():
            if entry.suffix.lower() in PROJECT_EXTENSIONS:
                projects.append({"name": entry.name, "path": str(entry)})
            else:
                dirs.append({"name": entry.name, "path": str(entry)})
        elif entry.is_file():
            if archive_io.is_archive(entry):
                archives.append({"name": entry.name, "path": str(entry)})
            elif entry.suffix.lower() in ALL_EXTENSIONS:
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
        "projects": projects,
        "archives": archives,
    }


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


@router.get("/browse-project")
async def browse_project(
    path: str = Query(..., description="Path to .pxiproject directory"),
) -> dict:
    """List images inside a PixInsight project bundle."""
    p = Path(path).expanduser().resolve()

    if not p.is_dir() or p.suffix.lower() not in PROJECT_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Not a .pxiproject directory: {p}")

    try:
        images = pxiproject_io.list_project_images(p)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {
        "path": str(p),
        "parent": str(p.parent),
        "images": images,
    }
