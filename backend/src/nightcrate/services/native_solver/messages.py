"""Stable user-facing failure messages for the built-in solver."""

MESSAGES: dict[str, str] = {
    "stars_not_installed": (
        "The built-in solver needs the plate-solving stars, a one-time 1.14 GB download."
    ),
    "no_ranges": "No field ranges are built yet. Build one in Admin → Plate-solving stars.",
    "too_few_stars": (
        "Only {n} stars were detected; at least {m} are needed. "
        "Check focus, clouds or the exposure."
    ),
    "no_match": (
        "No match found. {n} stars were detected, but none of the built field ranges matched them."
    ),
    "field_not_built": (
        "This image's field ({field:.2f}°) needs “{name}” in Admin → Plate-solving stars, "
        "which isn't built yet. Build it to blind solve this image."
    ),
    "ambiguous": "Two different solutions fit this image, so neither is used.",
    "time_limit": "The search ran out of time before finding a solution.",
    "cancelled": "Solve cancelled.",
}
