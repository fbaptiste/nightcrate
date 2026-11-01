"""Resolve native-solver position and scale hints."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class SolveHints:
    ra_deg: float | None = None
    dec_deg: float | None = None
    scale_arcsec: float | None = None
    position_source: Literal["request", "header", "none"] = "none"
    scale_source: Literal["request", "header", "none"] = "none"


def hints_for(
    cards: list[dict],
    *,
    image_height: int,
    ra_hint: float | None,
    dec_hint: float | None,
    scale_hint_arcsec: float | None = None,
    fov_hint: float | None = None,
    ignore_position: bool = False,
    ignore_scale: bool = False,
) -> SolveHints:
    """Return request-over-header hints in the solver's units."""
    # Local import avoids a module cycle: plate_solve dispatches to solve_image.
    from nightcrate.services.plate_solve import _parse_dec, _parse_ra, cards_to_dict

    raw = cards_to_dict(cards)
    ra: float | None = None
    dec: float | None = None
    position_source: Literal["request", "header", "none"] = "none"
    if not ignore_position:
        if ra_hint is not None and dec_hint is not None:
            ra, dec = ra_hint, dec_hint
            position_source = "request"
        else:
            header_ra, header_dec = _parse_ra(raw), _parse_dec(raw)
            if header_ra is not None and header_dec is not None:
                ra, dec = header_ra, header_dec
                position_source = "header"
    scale: float | None = None
    scale_source: Literal["request", "header", "none"] = "none"
    if not ignore_scale:
        if scale_hint_arcsec is not None:
            scale = scale_hint_arcsec
            scale_source = "request"
        elif fov_hint is not None and image_height > 0:
            scale = fov_hint * 3600.0 / image_height
            scale_source = "request"
        else:
            try:
                focal_length = float(raw["FOCALLEN"])
                pixel_size = float(raw.get("YPIXSZ") or raw["XPIXSZ"])
                if focal_length > 0 and pixel_size > 0:
                    scale = 206.265 * pixel_size / focal_length
                    scale_source = "header"
            except KeyError, TypeError, ValueError:
                pass
    return SolveHints(ra, dec, scale, position_source, scale_source)
