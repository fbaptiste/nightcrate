"""Shared helpers used by the per-source DSO loaders.

v0.14.0 had a single OpenNGC-specific loader. v0.15.0 added four more
parser strategies (Sharpless, Barnard, 50 MGC, augment CSV) that all
share the same low-level patterns — file-hash check, source-registry
upsert, and string normalisation. This module holds those primitives so
the per-strategy loaders stay focused on their parser-specific logic.
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
import sqlite3
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from nightcrate.catalog_loader.designations import normalize_designation as normalize_designation
from nightcrate.catalog_loader.loader import SourceResult
from nightcrate.catalog_loader.registry import CatalogSource

# ── Small value parsers ─────────────────────────────────────────────────────


def maybe_float(value: str | None) -> float | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def maybe_str(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


_GREEK_NAMES: dict[str, str] = {
    "alpha": "α",
    "beta": "β",
    "gamma": "γ",
    "delta": "δ",
    "epsilon": "ε",
    "zeta": "ζ",
    "eta": "η",
    "theta": "θ",
    "iota": "ι",
    "kappa": "κ",
    "lambda": "λ",
    "mu": "μ",
    "nu": "ν",
    "xi": "ξ",
    "pi": "π",
    "rho": "ρ",
    "sigma": "σ",
    "tau": "τ",
    "upsilon": "υ",
    "phi": "φ",
    "chi": "χ",
    "psi": "ψ",
    "omega": "ω",
}
_GREEK_PATTERN = "|".join(_GREEK_NAMES)
_GREEK_PLACEHOLDER_RE = re.compile(rf"\{{({_GREEK_PATTERN})\}}", re.IGNORECASE)
# Bare Greek names in these catalogs are lowercase (for example ``gamma^2``).
# Keeping this case-sensitive avoids corrupting T Tauri names such as ``HL Tau``.
_BARE_GREEK_RE = re.compile(rf"\b({_GREEK_PATTERN})\b")
_SUPERSCRIPT_RE = re.compile(r"\^(\d+)")
_SUPERSCRIPT_DIGITS = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")


def clean_tex_name(value: str | None) -> str | None:
    """Render the small TeX-like name subset used by the WR and HH tables."""
    cleaned = maybe_str(value)
    if cleaned is None:
        return None
    cleaned = _GREEK_PLACEHOLDER_RE.sub(lambda match: _GREEK_NAMES[match.group(1).lower()], cleaned)
    cleaned = _BARE_GREEK_RE.sub(lambda match: _GREEK_NAMES[match.group(1)], cleaned)
    cleaned = _SUPERSCRIPT_RE.sub(
        lambda match: match.group(1).translate(_SUPERSCRIPT_DIGITS), cleaned
    )
    return maybe_str(cleaned.replace("{", "").replace("}", ""))


# ── dso_catalog_source upsert ───────────────────────────────────────────────


def upsert_catalog_source(
    cur: sqlite3.Cursor,
    source: CatalogSource,
    file_hash: str,
    row_count: int,
) -> int:
    """Insert or update the ``dso_catalog_source`` row for *source*.

    Returns the row's integer id. Any follow-up DSO inserts use this as
    their ``source_catalog_id`` FK so a future wipe-and-reload can
    ``DELETE FROM dso WHERE source_catalog_id = ?`` cleanly.
    """
    cur.execute(
        "SELECT id FROM dso_catalog_source WHERE source_id = ?",
        (source.source_id,),
    )
    existing = cur.fetchone()
    if existing is None:
        cur.execute(
            """
            INSERT INTO dso_catalog_source (
                source_id, category, display_name, version, source_url,
                file_path, file_hash, license, attribution, row_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source.source_id,
                source.category,
                source.display_name,
                source.version,
                source.source_url,
                str(source.file_path),
                file_hash,
                source.license,
                source.attribution,
                row_count,
            ),
        )
        new_id = cur.lastrowid
        if new_id is None:
            raise RuntimeError("dso_catalog_source INSERT returned no row id")
        return new_id

    cur.execute(
        """
        UPDATE dso_catalog_source SET
            category = ?, display_name = ?, version = ?, source_url = ?,
            file_path = ?, file_hash = ?, license = ?, attribution = ?,
            loaded_at = datetime('now'), row_count = ?
        WHERE id = ?
        """,
        (
            source.category,
            source.display_name,
            source.version,
            source.source_url,
            str(source.file_path),
            file_hash,
            source.license,
            source.attribution,
            row_count,
            existing[0],
        ),
    )
    return existing[0]


# ── Hash-check preamble used by every loader ────────────────────────────────


@dataclass(frozen=True, slots=True)
class LoaderPreflight:
    """Outcome of the pre-load hash check.

    When ``status`` is ``missing`` / ``unchanged``, the loader returns
    the ``preset_result`` immediately. Otherwise it proceeds with the
    heavy load and uses the caller's own per-source logic.
    """

    preset_result: SourceResult | None


def check_source_state(
    conn: sqlite3.Connection,
    source: CatalogSource,
    effective_hash: str,
    *,
    force: bool,
) -> LoaderPreflight:
    """Handle the missing / hash-match short-circuit shared by all loaders.

    Returns a ``LoaderPreflight`` whose ``preset_result`` is non-None when
    the caller should early-return (file missing or hash unchanged).
    A ``None`` return signals "proceed with the full load"; the caller is
    responsible for ``BEGIN``, clearing prior rows, calling
    :func:`upsert_catalog_source`, parsing, inserting, and committing.
    """
    if not source.file_path.exists():
        return LoaderPreflight(
            SourceResult(
                source_id=source.source_id,
                status="missing",
                error=f"file not found: {source.file_path}",
            )
        )

    cur = conn.cursor()
    cur.execute(
        "SELECT id, file_hash FROM dso_catalog_source WHERE source_id = ?",
        (source.source_id,),
    )
    existing = cur.fetchone()
    if existing and existing[1] == effective_hash and not force:
        cur.execute("SELECT row_count FROM dso_catalog_source WHERE id = ?", (existing[0],))
        row = cur.fetchone()
        dso_count = int(row[0]) if row else 0
        return LoaderPreflight(
            SourceResult(
                source_id=source.source_id,
                status="unchanged",
                dso_count=dso_count,
            )
        )
    return LoaderPreflight(preset_result=None)


# ── Retry layer shared between GitHub (remote.py) + VizieR (vizier.py) ──────

_DEFAULT_MAX_ATTEMPTS = 3
_RETRY_BACKOFF_MIN_S = 0.6
_RETRY_BACKOFF_MAX_S = 1.4


@dataclass(frozen=True, slots=True)
class RetryEvent:
    label: str
    failed_attempt: int
    next_attempt: int
    delay_s: float
    error: str


async def retry_with_backoff[T](
    coro_factory: Callable[[], Awaitable[T]],
    *,
    label: str,
    logger: logging.Logger,
    max_attempts: int = _DEFAULT_MAX_ATTEMPTS,
    on_retry: Callable[[RetryEvent], None] | None = None,
) -> T:
    """Run *coro_factory* up to *max_attempts* times with jittered backoff.

    Sits on top of ``services/http_client.get``'s own single-retry-per-call,
    so the worst case is ~2 × max_attempts underlying HTTP attempts per
    URL. Used by the GitHub and VizieR fetchers.
    """
    last_exc: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await coro_factory()
        except Exception as exc:  # noqa: BLE001 — diagnostic-only retry layer
            last_exc = exc
            logger.warning(
                "[%s] %s attempt %d/%d failed: %s",
                logger.name.rsplit(".", 1)[-1],
                label,
                attempt,
                max_attempts,
                exc,
            )
            if attempt == max_attempts:
                raise
            delay = random.uniform(  # nosec B311 - retry jitter, not security-sensitive
                _RETRY_BACKOFF_MIN_S, _RETRY_BACKOFF_MAX_S
            )
            if on_retry is not None:
                on_retry(
                    RetryEvent(
                        label=label,
                        failed_attempt=attempt,
                        next_attempt=attempt + 1,
                        delay_s=delay,
                        error=str(exc) or type(exc).__name__,
                    )
                )
            await asyncio.sleep(delay)
    raise last_exc if last_exc is not None else RuntimeError("retry loop exhausted")
