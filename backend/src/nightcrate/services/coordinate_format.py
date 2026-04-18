"""Coordinate display formatting for latitude/longitude.

Converts decimal degrees to sexagesimal strings with cardinal directions
for display in the Locations UI. Storage remains decimal degrees.
"""

from astropy import units as u
from astropy.coordinates import Angle

_SEP = ("\u00b0", "\u2032", "\u2033")  # °  prime  double-prime


def _format_dms(decimal_deg: float) -> str:
    """Format a non-negative decimal degree value as DD°MM′SS″."""
    angle = Angle(abs(decimal_deg), unit=u.deg)
    return angle.to_string(unit=u.deg, sep=_SEP, precision=0, pad=True)


def format_latitude(decimal_deg: float) -> str:
    """Format a decimal latitude as a sexagesimal display string.

    Example: 33.465  -> "33°27′54″ N"
             -33.465 -> "33°27′54″ S"
    """
    if not -90.0 <= decimal_deg <= 90.0:
        raise ValueError(f"Latitude out of range [-90, 90]: {decimal_deg}")
    direction = "N" if decimal_deg >= 0 else "S"
    return f"{_format_dms(decimal_deg)} {direction}"


def format_longitude(decimal_deg: float) -> str:
    """Format a decimal longitude as a sexagesimal display string.

    Assumes input is normalized to [-180, 180].
    Example: -112.074 -> "112°04′26″ W"
              112.074 -> "112°04′26″ E"
    """
    if not -180.0 <= decimal_deg <= 180.0:
        raise ValueError(f"Longitude out of range [-180, 180]: {decimal_deg}")
    direction = "E" if decimal_deg >= 0 else "W"
    return f"{_format_dms(decimal_deg)} {direction}"
