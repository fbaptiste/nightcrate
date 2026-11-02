"""Natural ordering for user-facing DSO designations."""

from __future__ import annotations

import re

_PREFIX_RE = re.compile(r"^([A-Za-z]+(?:2(?=[\s-]|\d))?)")
_NUMBER_RE = re.compile(r"\d+")
_IGNORED_REMAINDER_RE = re.compile(r"[\s_-]+")

_CATALOG_PRIORITY: tuple[str, ...] = ("messier", "ngc", "ic", "caldwell")


def catalog_rank(catalog: str) -> int:
    """Return the fixed designation-catalog rank used throughout the DSO API.

    The catalog code is a separate tie-breaker, so every code outside the four
    primary-name catalogs shares the final rank and sorts alphabetically.
    """
    try:
        return _CATALOG_PRIORITY.index(catalog)
    except ValueError:
        return len(_CATALOG_PRIORITY)


def designation_sort_key(value: str | None) -> str | None:
    """Return a SQLite-safe natural key for a displayed designation.

    Prefixes compare case-insensitively, followed by every numeric component
    as an integer and then the non-numeric remainder.  The fixed-width length
    prefix keeps arbitrarily large identifiers numeric without converting them
    through SQLite's bounded integer type.
    """
    if value is None:
        return None

    normalized = value.strip().casefold()
    match = _PREFIX_RE.match(normalized)
    prefix = match.group(1) if match else ""
    rest = normalized[match.end() :] if match else normalized

    numbers: list[str] = []
    for digits in _NUMBER_RE.findall(rest):
        canonical = digits.lstrip("0") or "0"
        numbers.append(f"N{len(canonical):010d}:{canonical}")
    remainder = _IGNORED_REMAINDER_RE.sub("", _NUMBER_RE.sub("", rest))
    return f"{prefix}\x1f{''.join(numbers)}!{remainder}"
