"""Thin wrapper for CDS Aladin's ``hips2fits`` image service.

Only builds the URL and fetches the bytes via ``services.http_client``.
The full thumbnail lifecycle (cache lookup, fallback chain, eviction)
lives in ``services.thumbnails``.

Service reference: https://alasky.cds.unistra.fr/hips-image-services/hips2fits
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Mapping
from urllib.parse import urlencode

from nightcrate.services import http_client

logger = logging.getLogger("nightcrate.hips_client")

HIPS2FITS_BASE = "https://alasky.cds.unistra.fr/hips-image-services/hips2fits"

HIPS_DSS2_COLOR = "CDS/P/DSS2/color"
HIPS_DSS2_RED = "CDS/P/DSS2/red"
HIPS_DSS2_BLUE = "CDS/P/DSS2/blue"

# CDS can be slow on first-time HiPS renders; give them a generous budget.
_FETCH_TIMEOUT_S = 20.0


def build_hips2fits_url(
    hips: str,
    *,
    ra_deg: float,
    dec_deg: float,
    width: int,
    height: int,
    fov_deg: float,
    fmt: str = "jpg",
) -> str:
    """Compose the ``hips2fits`` query URL.

    Keeps the HiPS name as an opaque string so callers can swap DSS2
    variants or experiment with other HiPS surveys without churn here.
    """
    params = {
        "hips": hips,
        "width": str(width),
        "height": str(height),
        "ra": f"{ra_deg:.6f}",
        "dec": f"{dec_deg:.6f}",
        "fov": f"{fov_deg:.6f}",
        "format": fmt,
    }
    return f"{HIPS2FITS_BASE}?{urlencode(params)}"


def build_hips2fits_wcs_url(
    hips: str,
    wcs_header: Mapping[str, int | float | str],
    *,
    fmt: str = "jpg",
) -> str:
    """Compose a ``hips2fits`` URL using a custom WCS header.

    Used by the v0.18.0 sky-tile cache to render off-centre TAN tiles
    on a shared tangent plane: every cell in a HEALPix region passes
    the same ``CRVAL1/2`` and only differs in ``CRPIX1/2``, so adjacent
    cells render pixel-perfectly aligned.

    ``wcs_header`` must include ``NAXIS1`` / ``NAXIS2`` (hips2fits relies
    on them to set output dimensions — ``astropy.wcs.WCS.to_header()``
    omits them because they belong to the HDU, not the WCS). Build the
    dict with ``services.sky_tiles.cell_wcs_dict``.

    The ``wcs`` parameter is a JSON dict per the hips2fits spec
    (verified at <https://alasky.cds.unistra.fr/hips-image-services/hips2fits>).
    ``urlencode`` handles the percent-escaping.
    """
    params = {
        "hips": hips,
        "wcs": json.dumps(dict(wcs_header), separators=(",", ":")),
        "format": fmt,
    }
    return f"{HIPS2FITS_BASE}?{urlencode(params)}"


async def fetch_hips_image(url: str) -> bytes:
    """Fetch an image from ``hips2fits``, raising on any non-OK response.

    Rejects bodies that don't look like an image — CDS occasionally
    serves an HTML error page with HTTP 200 when a HiPS is temporarily
    unavailable. JPEG starts with ``FF D8``; PNG starts with
    ``89 50 4E 47``. Anything else triggers a RuntimeError so the caller
    can fall back to the next HiPS in the chain.

    Logs the full upstream URL + timing at DEBUG so pan/fetch problems
    are traceable against CDS's own latency.
    """
    logger.debug("[hips] → GET %s", url)
    t0 = time.perf_counter()
    try:
        response = await http_client.get(
            url,
            label="hips2fits",
            follow_redirects=True,
            timeout=_FETCH_TIMEOUT_S,
        )
    except Exception as exc:
        dt_ms = (time.perf_counter() - t0) * 1000
        logger.debug("[hips] ✗ %s after %.0f ms — %s", url, dt_ms, exc)
        raise
    dt_ms = (time.perf_counter() - t0) * 1000
    if response.status_code >= 400:
        logger.debug("[hips] ← HTTP %d in %.0f ms (%s)", response.status_code, dt_ms, url)
        raise RuntimeError(f"hips2fits returned HTTP {response.status_code}")
    body = response.content
    if not body:
        logger.debug("[hips] ← empty body in %.0f ms (%s)", dt_ms, url)
        raise RuntimeError("hips2fits returned empty body")
    if not (body.startswith(b"\xff\xd8") or body.startswith(b"\x89PNG")):
        logger.debug(
            "[hips] ← non-image (first 16: %r) in %.0f ms (%s)",
            body[:16],
            dt_ms,
            url,
        )
        raise RuntimeError(f"hips2fits returned non-image body (first 16 bytes: {body[:16]!r})")
    logger.debug("[hips] ← %d bytes in %.0f ms (%s)", len(body), dt_ms, url)
    return body
