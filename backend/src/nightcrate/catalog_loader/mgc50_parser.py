"""FITS binary-table parser for the 50 MGC ``catalog.fits`` file.

The upstream GitHub mirror at https://github.com/davidohlson/50MGC
distributes the catalog as FITS binary tables under ``data/catalog.fits``
(and a stripped ``catalog_short.fits`` that omits the distance columns
we need). We always fetch the full catalog and read four columns:

    pgc             — PGC number (int; HyperLeda cross-reference)
    bestdist        — best distance estimate (float, Mpc)
    bestdist_error  — uncertainty on bestdist (float, Mpc; optional)
    bestdist_method — method tag string (one of CF3-Z, Karachentsev,
                      NED-D, Mei, Cantiello, EVCC, HyperLeda); optional

Rows with missing/invalid ``pgc`` (<= 0) or missing ``bestdist`` are
skipped — they can't be cross-referenced into the DSO catalog and carry
no augmentation value. The README documents all distances in Mpc; the
augmenter applies the × 1e6 conversion to parsecs.

The v0.15.0 Patch 1 spec called for a fixed-width parser (matching the
VizieR ``tablea1.dat`` layout), but the author's GitHub mirror — which
Patch 2 picked to sidestep CDS flakiness — ships only the FITS artefact.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from astropy.io import fits

_PGC_COL = "pgc"
_BEST_DIST_COL = "bestdist"
_E_BEST_DIST_COL = "bestdist_error"
_METHOD_COL = "bestdist_method"

# Tuple constant sidesteps the py314 ruff-format bug where `except (A, B):`
# gets its parens stripped into the Python 2 `except A, B:` form.
_COERCE_ERRS: tuple[type[BaseException], ...] = (TypeError, ValueError)


@dataclass(frozen=True, slots=True)
class Parsed50mgcRow:
    pgc: int
    best_dist_mpc: float
    e_best_dist_mpc: float | None
    f_best_dist: str | None


def _maybe_float(value) -> float | None:
    """Return a finite float or None for NaN / masked / non-numeric input."""
    try:
        f = float(value)
    except _COERCE_ERRS:
        return None
    if np.isnan(f):
        return None
    return f


def _maybe_str(value) -> str | None:
    """Strip a FITS byte/str value; return None if empty after strip."""
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    text = str(value).strip()
    return text or None


def parse_50mgc_fits(path: Path) -> Iterator[Parsed50mgcRow]:
    """Yield one :class:`Parsed50mgcRow` per usable row in *path*.

    Skips rows with ``pgc <= 0`` (HyperLeda's "no cross-reference"
    sentinel), missing/NaN ``bestdist``, or ``bestdist <= 0``. Malformed
    rows are dropped silently; the augmenter tracks read-vs-yielded
    counts in its own logging.
    """
    with fits.open(path, memmap=False) as hdul:
        # HDU 0 is the primary header on binary-table FITS; data lives in
        # the first extension.
        if len(hdul) < 2 or hdul[1].data is None:
            return
        table = hdul[1].data
        columns = {name.lower() for name in table.columns.names}

    for required in (_PGC_COL, _BEST_DIST_COL):
        if required not in columns:
            raise ValueError(
                f"{path}: FITS table missing required column {required!r} "
                f"(columns present: {sorted(columns)})"
            )

    has_e_best = _E_BEST_DIST_COL in columns
    has_method = _METHOD_COL in columns

    pgc_raw = table.field(_PGC_COL)
    best_raw = table.field(_BEST_DIST_COL)
    e_best_raw = table.field(_E_BEST_DIST_COL) if has_e_best else None
    method_raw = table.field(_METHOD_COL) if has_method else None

    for i in range(len(table)):
        try:
            pgc = int(pgc_raw[i])
        except _COERCE_ERRS:
            continue
        if pgc <= 0:
            continue

        best_dist = _maybe_float(best_raw[i])
        if best_dist is None or best_dist <= 0:
            continue

        yield Parsed50mgcRow(
            pgc=pgc,
            best_dist_mpc=best_dist,
            e_best_dist_mpc=_maybe_float(e_best_raw[i]) if e_best_raw is not None else None,
            f_best_dist=_maybe_str(method_raw[i]) if method_raw is not None else None,
        )
