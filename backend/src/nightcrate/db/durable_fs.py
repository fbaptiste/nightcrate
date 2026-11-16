"""Small durable filesystem primitives used by workspace upgrades."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def fsync_dir(path: Path) -> None:
    """Flush directory metadata on POSIX."""
    if os.name == "nt":
        return
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    fd = os.open(path, flags)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def durable_write(path: Path, data: bytes) -> None:
    """Atomically publish bytes and flush the containing directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        fsync_dir(path.parent)
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


def durable_remove(path: Path) -> None:
    """Remove a file and flush the containing directory."""
    try:
        path.unlink()
    except FileNotFoundError:
        return
    fsync_dir(path.parent)
