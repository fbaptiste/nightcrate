"""Thin wrapper for CDS Aladin's ``hips2fits`` image service.

Only builds the URL and fetches the bytes via ``services.http_client``.
The full thumbnail lifecycle (cache lookup, fallback chain, eviction)
lives in ``services.thumbnails``.

Service reference: https://alasky.cds.unistra.fr/hips-image-services/hips2fits
"""

from __future__ import annotations

from urllib.parse import urlencode

from nightcrate.services import http_client

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


async def fetch_hips_image(url: str) -> bytes:
    """Fetch an image from ``hips2fits``, raising on any non-OK response.

    Rejects bodies that don't look like an image — CDS occasionally
    serves an HTML error page with HTTP 200 when a HiPS is temporarily
    unavailable. JPEG starts with ``FF D8``; PNG starts with
    ``89 50 4E 47``. Anything else triggers a RuntimeError so the caller
    can fall back to the next HiPS in the chain.
    """
    response = await http_client.get(
        url,
        label="hips2fits",
        follow_redirects=True,
        timeout=_FETCH_TIMEOUT_S,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"hips2fits returned HTTP {response.status_code}")
    body = response.content
    if not body:
        raise RuntimeError("hips2fits returned empty body")
    if not (body.startswith(b"\xff\xd8") or body.startswith(b"\x89PNG")):
        raise RuntimeError(f"hips2fits returned non-image body (first 16 bytes: {body[:16]!r})")
    return body
