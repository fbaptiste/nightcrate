"""Deterministic seed hash function — Contract v1.

The hash format is a versioned contract. Once released it MUST NOT change
without a migration that re-hashes all stored seed_hash values.
"""

import hashlib
import math
import re
from typing import Any

HASH_CONTRACT_VERSION = "1"

_FIELD_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

_NULL_SENTINEL = "\x00NULL\x00"


def _encode_value(key: str, value: Any) -> str:
    """Encode a single value to its canonical string representation."""
    if isinstance(value, bool):
        return "1" if value else "0"
    if value is None:
        return _NULL_SENTINEL
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value):
            raise ValueError(f"Field '{key}': NaN is not allowed in seed hash fields")
        if math.isinf(value):
            raise ValueError(f"Field '{key}': infinity is not allowed in seed hash fields")
        return repr(value)
    if isinstance(value, str):
        if "\n" in value or "\r" in value:
            raise ValueError(f"Field '{key}': newlines are not allowed in seed hash string values")
        return value
    if isinstance(value, bytes):
        raise ValueError(f"Field '{key}': bytes values are not allowed in seed hash fields")
    raise ValueError(
        f"Field '{key}': unsupported type {type(value).__name__!r} in seed hash fields"
    )


def compute_seed_hash(fields: dict[str, Any]) -> str:
    """Compute a deterministic SHA-256 hash of the given fields.

    Returns a lowercase hex string. The serialization format is a versioned
    contract — do not change this function after release.

    Serialization rules:
    - Keys sorted alphabetically
    - Each key emitted as one line: ``key=<encoded_value>``
    - Lines joined with ``\\n``
    - Encoded as UTF-8
    - SHA-256 hexdigest (lowercase)

    Raises:
        ValueError: if a field name is invalid or a value type is unsupported.
    """
    for key in fields:
        if not _FIELD_NAME_RE.match(key):
            raise ValueError(f"Invalid field name {key!r}: must match [a-zA-Z_][a-zA-Z0-9_]*")

    lines = []
    for key in sorted(fields):
        encoded = _encode_value(key, fields[key])
        lines.append(f"{key}={encoded}")

    payload = "\n".join(lines).encode("utf-8")
    return hashlib.sha256(payload).hexdigest().lower()
