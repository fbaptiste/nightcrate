"""Parse OpenNGC's ``Identifiers`` column into catalog cross-references.

Example input::

    "C 020, LBN 373"
    "MCG-00-07-079, PGC 10266, UGC 2271"
    "Sh2-281, LBN 974"

Output: a list of ``ParsedCrossRef`` objects with each token mapped to
the project's closed ``dso_designation.catalog`` vocabulary. Unknown
tokens are dropped silently — the raw column value is preserved on
``dso.raw_other_id`` so future parser improvements can reconsume
them without a full reload.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Mapping of OpenNGC's token prefixes → our dso_designation.catalog vocabulary.
# Keys are case-sensitive; tokens are normalized before lookup. Order doesn't
# matter here — prefix matching is done greedily by length at parse time.
PREFIX_MAP: dict[str, str] = {
    "C": "caldwell",
    "UGC": "ugc",
    "PGC": "pgc",
    "LBN": "lbn",
    "LDN": "ldn",
    "MCG": "mcg",
    "ESO": "eso",
    "Arp": "arp",
    "HCG": "hickson",
    "Sh2": "sharpless2",
    "B": "barnard",
    "VdB": "vdb",
    "Ced": "cederblad",
    "PK": "pk",
    "RCW": "rcw",
    "Gum": "gum",
    "Mrk": "mrk",
    "Terzan": "terzan",
    "Pal": "pal",
    "Mel": "mel",
    "Cr": "cr",
    "Stock": "stock",
    "Ru": "ruprecht",
    "Abell": "abell",
    "Do": "dolidze",
    "DWB": "dwb",
}

# Longest prefixes first, so e.g. "Sh2" beats "S*" style competitors and
# "HCG" beats "H".
_SORTED_PREFIXES = sorted(PREFIX_MAP.keys(), key=len, reverse=True)


@dataclass(frozen=True, slots=True)
class ParsedCrossRef:
    catalog: str
    identifier: str


_PURE_NUMERIC_RE = re.compile(r"^0*(\d+)([A-Za-z]*)$")


def _strip_separator(rest: str) -> str:
    """Drop the prefix→identifier separator.

    OpenNGC uses two separator styles:
    - Tight-dash (no whitespace): ``Sh2-281`` → identifier ``281``.
    - Whitespace: ``MCG -02-01-031`` → identifier ``-02-01-031``.

    When the original string starts with ``-`` (tight-dash style), we strip
    that one dash. When it starts with whitespace, we only strip whitespace
    — any subsequent ``-`` or ``+`` is part of the identifier itself.
    """
    if not rest:
        return ""
    if rest[0] == "-":
        return rest[1:].strip()
    return rest.strip()


def _normalize_identifier(identifier: str) -> str:
    """Strip leading zeros from simple numeric identifiers.

    Kept conservative: only applies when the whole identifier is digits
    optionally followed by a letter suffix (e.g., ``"020"`` → ``"20"``,
    ``"001A"`` → ``"1A"``). Compound codes like ``"-02-01-031"`` or
    ``"+03-01-029"`` pass through verbatim so MCG / ESO-style identifiers
    don't lose structure.
    """
    match = _PURE_NUMERIC_RE.match(identifier)
    if match is None:
        return identifier
    digits, suffix = match.groups()
    return digits + suffix


def _match_prefix(token: str) -> tuple[str, str] | None:
    """Return ``(catalog, identifier)`` for a token, or None if no prefix matches."""
    token = token.strip()
    if not token:
        return None

    for prefix in _SORTED_PREFIXES:
        if not token.startswith(prefix):
            continue

        rest = token[len(prefix) :]

        # For single-letter prefixes the next character must be whitespace or
        # a digit, otherwise we'd greedily eat other catalog codes (e.g., 'B'
        # would match 'BD+12 345' — Bonner Durchmusterung, not Barnard). For
        # longer prefixes we're less worried about collisions.
        if len(prefix) == 1:
            if not rest or (not rest[0].isspace() and not rest[0].isdigit() and rest[0] != "-"):
                continue

        identifier = _strip_separator(rest)
        if not identifier:
            continue

        catalog = PREFIX_MAP[prefix]
        return catalog, _normalize_identifier(identifier)

    return None


def parse_other_id(raw: str | None) -> list[ParsedCrossRef]:
    """Tokenize OpenNGC's ``Identifiers`` field into recognized cross-references.

    Commas are the separator. Tokens that don't match a known prefix are
    dropped silently. The raw string should still be preserved by the caller
    on ``dso.raw_other_id`` for future re-parsing.
    """
    if not raw:
        return []

    results: list[ParsedCrossRef] = []
    for token in raw.split(","):
        match = _match_prefix(token)
        if match is None:
            continue
        catalog, identifier = match
        results.append(ParsedCrossRef(catalog=catalog, identifier=identifier))
    return results
