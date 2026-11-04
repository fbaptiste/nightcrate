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


def _append_unique(values: list[str], value: str) -> None:
    if value not in values and len(values) < 4:
        values.append(value)


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


def designation_search_prefixes(query: str) -> list[str]:
    """Return search prefixes, including padded forms for partial structured names."""
    prefixes = [normalize_designation(query)]

    mcg_match = _MCG_QUERY_RE.fullmatch(query)
    if mcg_match is not None:
        value = mcg_match.group(1).replace(" ", "")
        partial = re.fullmatch(r"([+-]?)(\d{1,2})(?:-(\d{0,2}))?(?:-(\d{0,3}))?", value)
        if partial is not None:
            sign, first, second, third = partial.groups()
            sign = sign or "+"
            if third is None and second is None:
                for width in range(len(first), 3):
                    _append_unique(prefixes, f"mcg{sign}{first.zfill(width)}")
            elif third is None:
                first = first.zfill(2)
                if second:
                    for width in range(len(second), 3):
                        _append_unique(prefixes, f"mcg{sign}{first}-{second.zfill(width)}")
                else:
                    _append_unique(prefixes, f"mcg{sign}{first}-")
            elif not third:
                _append_unique(prefixes, f"mcg{sign}{first.zfill(2)}-{second.zfill(2)}-")
        return prefixes

    pn_match = _PN_QUERY_RE.fullmatch(query)
    if pn_match is None:
        return prefixes
    value = pn_match.group(1).replace(" ", "")
    partial = re.fullmatch(r"(\d{1,3})(\.\d*)?([+-])?(\d{0,2})?(\.\d*)?", value)
    if partial is None:
        return prefixes
    longitude, longitude_fraction, sign, latitude, latitude_fraction = partial.groups()
    if longitude_fraction is None and sign is None:
        for width in range(len(longitude) + 1, 4):
            _append_unique(prefixes, f"png{longitude.zfill(width)}")
        return prefixes

    longitude_prefix = longitude.zfill(3) + (longitude_fraction or "")
    if sign is None:
        _append_unique(prefixes, f"png{longitude_prefix}")
        return prefixes
    if latitude_fraction is not None:
        latitude_prefix = (latitude or "").zfill(2) + latitude_fraction
        _append_unique(prefixes, f"png{longitude_prefix}{sign}{latitude_prefix}")
    elif latitude:
        for width in range(len(latitude), 3):
            _append_unique(
                prefixes,
                f"png{longitude_prefix}{sign}{latitude.zfill(width)}",
            )
    else:
        _append_unique(prefixes, f"png{longitude_prefix}{sign}")
    return prefixes
