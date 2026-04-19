"""Hash helpers for the DSO catalog loader.

Two flavours:

- ``file_sha256`` — sha256 of a catalog source file's bytes. Used to decide
  whether a registered source needs to be reloaded.
- ``row_sha256`` — sha256 of a normalized representation of a parsed row.
  Stored alongside each ``dso`` record for future merge / reproducibility
  workflows. Parallels the equipment seed loader's ``seed_hash`` column
  in purpose but not in wire format — the two hashes are independent.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

_CHUNK = 1 << 20  # 1 MiB
_NULL_SENTINEL = "\x00NULL\x00"


def file_sha256(path: Path) -> str:
    """Return the lowercase hex sha256 digest of the file at *path*."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(_CHUNK):
            h.update(chunk)
    return h.hexdigest()


def _encode(value: Any) -> str:
    if value is None:
        return _NULL_SENTINEL
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        return value
    raise TypeError(f"unsupported type for row hash: {type(value).__name__}")


def row_sha256(fields: dict[str, Any]) -> str:
    """Hash a dict of scalar fields.

    Keys sorted, ``key=value`` lines joined with ``\\n``. Newlines in values
    are replaced with spaces so the wire format stays one-line-per-field.
    """
    lines: list[str] = []
    for key in sorted(fields):
        encoded = _encode(fields[key]).replace("\n", " ").replace("\r", " ")
        lines.append(f"{key}={encoded}")
    payload = "\n".join(lines).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
