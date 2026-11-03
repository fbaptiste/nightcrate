"""Dependency-free normalization for DSO designations."""

from __future__ import annotations

import re

_SEARCH_STRIP_RE = re.compile(r"[\s\-_]+")
_LONG_TO_SHORT_PREFIX: dict[str, str] = {
    "messier": "m",
    "caldwell": "c",
    "sharpless2": "sh2",
    "barnard": "b",
    "melotte": "mel",
    "collinder": "cr",
    "herbigharo": "hh",
    "wolfrayet": "wr",
    "ruprecht": "ru",
    "dolidze": "do",
    "hickson": "hcg",
}
_MCG_RE = re.compile(r"^([+-]?)(\d+)-(\d+)-(\d+)([A-Za-z]*)$")
_PNG_RE = re.compile(r"^(\d{1,3}(?:\.\d+)?)\s*([+-])\s*(\d{1,2}(?:\.\d+)?)$")
_WR_RE = re.compile(r"^(\d+)([A-Za-z]*)$")
_PN_QUERY_RE = re.compile(r"^\s*(?:PN\s*G|PNG)\s*(.+?)\s*$", re.IGNORECASE)
_MCG_QUERY_RE = re.compile(r"^\s*MCG\s*(.+?)\s*$", re.IGNORECASE)


def canonical_identifier(catalog: str, identifier: str) -> str:
    """Return the storage form for a structured catalog identifier."""
    value = identifier.strip()
    if catalog == "mcg":
        match = _MCG_RE.fullmatch(value)
        if match is not None:
            sign, first, second, third, suffix = match.groups()
            sign = sign or "+"
            return f"{sign}{int(first):02d}-{int(second):02d}-{int(third):03d}{suffix.lower()}"
    elif catalog == "png":
        match = _PNG_RE.fullmatch(value)
        if match is not None:
            longitude, sign, latitude = match.groups()
            return f"{float(longitude):05.1f}{sign}{float(latitude):04.1f}"
    elif catalog == "wr":
        match = _WR_RE.fullmatch(value)
        if match is not None:
            number, suffix = match.groups()
            return f"{int(number)}{suffix.lower()}"
    return value


def canonical_legacy_identifier(catalog: str, identifier: str) -> str:
    """Return the repaired storage form for a pre-0066 identifier."""
    value = identifier.strip()
    if catalog == "mcg" and not value.startswith(("+", "-")):
        # The pre-0066 parser dropped the minus from tight ``MCG-…`` tokens.
        value = "-" + value
    return canonical_identifier(catalog, value)


def normalize_designation(query: str) -> str:
    """Return the one search-key form used by loaders and API searches."""
    pn_match = _PN_QUERY_RE.fullmatch(query)
    if pn_match is not None:
        return "png" + canonical_identifier("png", pn_match.group(1)).casefold()

    mcg_match = _MCG_QUERY_RE.fullmatch(query)
    if mcg_match is not None:
        return "mcg" + canonical_identifier("mcg", mcg_match.group(1)).casefold()

    normalized = _SEARCH_STRIP_RE.sub("", query).lower()
    for long, short in _LONG_TO_SHORT_PREFIX.items():
        if normalized.startswith(long):
            return short + normalized[len(long) :]
    return normalized
