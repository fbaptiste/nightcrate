"""Bandpass line-name vocabulary and header-spelling canonicalization.

Two things live here, both pure and stdlib-only:

* ``LINE_NAMES`` — the closed bandpass vocabulary, mirroring the
  ``filter_passband.line_name`` CHECK (migration 0005) and the
  ``project_session.line_name`` CHECK (migration 0035). The TypeScript copy is
  ``frontend/src/lib/lineNames.ts``; adding a value means updating the migration,
  this tuple, and that file.
* ``canonicalize_line_name`` — fold a FITS ``FILTER`` spelling onto that
  vocabulary, plus ``normalize_label``, the normalization it is keyed on.

This module is deliberately separate from ``services/fits_header_map.py``, which
carries a *different* map (``FILTER_NAME_ALIASES``) applied inside
``extract_metadata``. That one produces the display short-form stored in
``sub_frame.filter_name_hint`` (``"Red"``, ``"Lum"``, …); this one produces the
passband vocabulary (``"R"``, ``"Lum"``, …). Both are needed and they are not
interchangeable.
"""

from __future__ import annotations

import re
import unicodedata

# Closed bandpass vocabulary — mirrors filter_passband.line_name (migration 0005).
LINE_NAMES: tuple[str, ...] = (
    "Ha",
    "Hb",
    "Oiii",
    "Sii",
    "Nii",
    "OI",
    "Lum",
    "R",
    "G",
    "B",
    "R+",
    "UVIR",
    "LP",
    "ND",
    "other",
)

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_label(value: str) -> str:
    """Return the canonical, comparison-ready form of a raw header value.

    Deterministic pipeline, applied in order:

    1. Unicode NFKC normalization.
    2. Strip leading / trailing whitespace.
    3. Collapse internal whitespace runs to a single space.
    4. Remove zero-width and control characters (Unicode category ``C*``),
       keeping the regular spaces produced by step 3.
    5. Lowercase.

    Punctuation, hyphens, slashes and parentheses are **preserved** — ``"7nm Ha"``
    and ``"7 nm Ha"`` are intentionally different labels. Used both as the key for
    :data:`_LINE_NAME_MAP` and as the grouping key for filter names that aren't
    recognized line names, so that ``"Antlia ALP-T"`` and ``"antlia  alp-t"`` land
    in the same derived session.
    """
    s = unicodedata.normalize("NFKC", value)
    s = s.strip()
    s = _WHITESPACE_RE.sub(" ", s)
    s = "".join(ch for ch in s if ch == " " or not unicodedata.category(ch).startswith("C"))
    return s.lower()


# Closed, code-level map (grows only by code change). Keys are the
# `normalize_label`-normalized form of accepted header spellings; values are the
# canonical `line_name` vocabulary. A value not in this map is "not a line name".
_LINE_NAME_MAP: dict[str, str] = {
    # Ha
    "ha": "Ha",
    "h-a": "Ha",
    "h alpha": "Ha",
    "h-alpha": "Ha",
    "halpha": "Ha",
    "hydrogen alpha": "Ha",
    "hydrogen-alpha": "Ha",
    # Hb
    "hb": "Hb",
    "h-b": "Hb",
    "h beta": "Hb",
    "h-beta": "Hb",
    "hbeta": "Hb",
    "hydrogen beta": "Hb",
    # Oiii
    "oiii": "Oiii",
    "o3": "Oiii",
    "o-iii": "Oiii",
    "o iii": "Oiii",
    "oxygen iii": "Oiii",
    "oxygen-iii": "Oiii",
    "oxygeniii": "Oiii",
    # Sii
    "sii": "Sii",
    "s2": "Sii",
    "s-ii": "Sii",
    "s ii": "Sii",
    "sulfur ii": "Sii",
    "sulphur ii": "Sii",
    "sulfur-ii": "Sii",
    # Lum
    "l": "Lum",
    "lum": "Lum",
    "luminance": "Lum",
    "clear": "Lum",
    # R / G / B
    "r": "R",
    "red": "R",
    "g": "G",
    "green": "G",
    "b": "B",
    "blue": "B",
    # UVIR
    "uvir": "UVIR",
    "uv/ir": "UVIR",
    "uv-ir": "UVIR",
    "uv ir cut": "UVIR",
}


def canonicalize_line_name(value: str) -> str | None:
    """Fold a FITS ``FILTER`` spelling onto the canonical ``line_name`` vocabulary.

    Returns ``None`` when *value* isn't a recognized line name — callers then fall
    back to the raw label (session derivation) or to no line name at all
    (``processed_image``).
    """
    if not value:
        return None
    return _LINE_NAME_MAP.get(normalize_label(value))
