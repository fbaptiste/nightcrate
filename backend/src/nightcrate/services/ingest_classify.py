"""Pure file/frame classification for the directory-scan ingest pipeline (v0.40.0).

Header-driven, never folder-name driven (arc decision 2026-06-25). Given a file's
extension and — for FITS/XISF — its parsed header metadata, decide which bucket it
lands in:

  * ``sub_frame``      — a raw light/dark/flat/bias/dark_flat exposure
  * ``processed_image``— a stack / master / processed export
  * ``pxiproject``     — a PixInsight project asset
  * ``log``            — a session / guiding / autofocus log (parsed in v0.43/0.44)
  * ``other``          — anything we don't catalog as the above (incl. standard
                         image exports and archives in v0.40.0)

No DB, no I/O here — this is the decision layer the scanner and ingest API call.
"""

from __future__ import annotations

import re
from typing import Any

from nightcrate.services.fits_header_map import normalize_frame_type
from nightcrate.services.path_resolver import (
    FITS_EXTENSIONS,
    STANDARD_EXTENSIONS,
    XISF_EXTENSIONS,
)

# Module-level tuple: ruff format strips parens from inline ``except (A, B):`` on
# py3.14, producing invalid Py2 syntax. Referencing a constant sidesteps it.
_COERCE_ERRORS = (TypeError, ValueError)

# Categories used both as file_location.category and as routing buckets.
CATEGORY_SUB = "sub_frame"
CATEGORY_PROCESSED = "processed"
CATEGORY_PXIPROJECT = "pxiproject"
CATEGORY_LOG = "log"
CATEGORY_OTHER = "other"

# Frame types stored on sub_frame.
FRAME_TYPES = ("light", "dark", "flat", "bias", "dark_flat", "unknown")

# Header-only formats we parse + classify by IMAGETYP / stack signals.
_HEADER_EXTENSIONS = FITS_EXTENSIONS | XISF_EXTENSIONS

# Dark-flat spellings (calibration for flats; matched as flats, never as darks-on-
# filter). normalize_frame_type doesn't cover these, so handle them explicitly.
_DARK_FLAT_RAW = {
    "flatdark",
    "darkflat",
    "flat dark",
    "dark flat",
    "flatdarks",
    "darkflats",
}

# Log filenames we recognize and park for later parsing.
_LOG_NAME_RE = re.compile(
    r"(phd2.*\.txt|.*guidelog.*\.txt|autorun_log.*\.txt|.*\.autofocus|autofocus.*\.json)$",
    re.IGNORECASE,
)


def classify_extension(name: str, *, is_dir: bool = False) -> str:
    """First-pass category from the path alone (no header read).

    Returns one of the CATEGORY_* constants. ``sub_frame`` here means "a
    header-bearing image worth parsing" — :func:`classify_frame` refines it into
    sub vs processed once the header is known.
    """
    lower = name.lower()
    if is_dir or lower.endswith(".pxiproject"):
        return CATEGORY_PXIPROJECT
    if _LOG_NAME_RE.search(lower):
        return CATEGORY_LOG
    ext = _ext(lower)
    if ext in _HEADER_EXTENSIONS:
        return CATEGORY_SUB
    if ext in STANDARD_EXTENSIONS:
        # Finished/processed exports (TIFF/PNG/JPG) carry no FITS header to
        # classify; gallery promotion is v0.41.0, so park as "other" for now.
        return CATEGORY_OTHER
    return CATEGORY_OTHER


def _ext(lower_name: str) -> str:
    dot = lower_name.rfind(".")
    return lower_name[dot:] if dot != -1 else ""


def is_stack(meta: dict[str, Any], raw_header: dict[str, Any]) -> bool:
    """True if header signals a stacked/combined master rather than a raw sub.

    Signals (any one): NCOMBINE / STACKCNT > 1, an IMAGETYP naming a master, or
    PixInsight integration history.
    """
    for key in ("pi_ncombine",):
        n = _as_int(meta.get(key))
        if n is not None and n > 1:
            return True
    for raw_key in ("STACKCNT", "NCOMBINE", "NIMAGES"):
        n = _as_int(raw_header.get(raw_key))
        if n is not None and n > 1:
            return True
    imagetyp = str(raw_header.get("IMAGETYP", "")).strip().lower()
    if "master" in imagetyp or "integration" in imagetyp or "stack" in imagetyp:
        return True
    for value in raw_header.values():
        if isinstance(value, str) and "imageintegration" in value.replace(" ", "").lower():
            return True
    return False


def classify_frame(meta: dict[str, Any], raw_header: dict[str, Any]) -> tuple[str, str | None]:
    """Refine a header-bearing image into (route, frame_type).

    ``route`` is ``CATEGORY_SUB`` or ``CATEGORY_PROCESSED``. ``frame_type`` is one
    of FRAME_TYPES for subs (``unknown`` when IMAGETYP is missing/unrecognized);
    for processed images it carries the best-guess frame type or ``None``.
    """
    frame_type = _frame_type_from_header(raw_header, meta)
    if is_stack(meta, raw_header):
        return CATEGORY_PROCESSED, frame_type
    return CATEGORY_SUB, frame_type or "unknown"


# Qualifier words a stacked-master IMAGETYP wraps around the real frame type, e.g.
# "Master Dark" / "Integration Flat". Stripped so the underlying type is recovered.
_MASTER_QUALIFIERS = ("master", "integration", "stacked", "stack", "combined")


def _frame_type_from_header(raw_header: dict[str, Any], meta: dict[str, Any]) -> str | None:
    raw = raw_header.get("IMAGETYP")
    if raw is None:
        # extract_metadata copies IMAGETYP into meta["frame_type"] (already
        # normalized when it was a plain type; raw passthrough otherwise).
        raw = meta.get("frame_type")
    if raw is None:
        return None
    cleaned = str(raw).strip().lower()
    if cleaned in FRAME_TYPES:
        return cleaned
    df = _match_dark_flat(cleaned)
    if df:
        return df
    # Recover the type from a master IMAGETYP: "master dark" -> "dark".
    core = cleaned
    for word in _MASTER_QUALIFIERS:
        core = core.replace(word, "")
    core = core.strip()
    if core and core != cleaned:
        df = _match_dark_flat(core)
        if df:
            return df
        recovered = normalize_frame_type(core)
        if recovered:
            return recovered
    return normalize_frame_type(cleaned)


def _match_dark_flat(value: str) -> str | None:
    return "dark_flat" if value in _DARK_FLAT_RAW else None


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value))
    except _COERCE_ERRORS:
        return None
