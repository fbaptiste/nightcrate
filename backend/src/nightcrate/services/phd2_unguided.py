"""Unguided RA reconstruction — PHDLogViewer recurrence (spec v4 §6.2)."""

from __future__ import annotations

from nightcrate.services.phd2_models import LogSection


def reconstruct_unguided_ra(
    section: LogSection,
    *,
    undo_corrections: bool = True,
) -> list[float | None]:
    """Cumulative unguided RA position trace, aligned 1:1 with section.samples.

    The recurrence ``move = raraw - prev_raraw - prev_raguide`` backs out the
    cumulative correction (Mount pulse OR AO offset — both live in
    ``ra_guide_px``) so the trace shows the drift the mount would have shown
    with neither source of correction active. AO frames with valid star data
    accumulate alongside Mount frames.

    DROP frames (``ra_raw_px is None`` or ``error_code != 0``) emit ``None``
    without advancing ``prev_*`` — the next valid frame's ``move`` correctly
    spans the gap.

    ``undo_corrections=False`` pins ``prev_raguide = 0`` so the output is the
    raw position anchored at zero (sanity check; not used by the UI).
    """
    out: list[float | None] = []
    rapos = 0.0
    prev_raraw = 0.0
    prev_raguide = 0.0
    for s in section.samples:
        if s.ra_raw_px is None or s.error_code != 0:
            out.append(None)
            continue
        raraw = s.ra_raw_px
        raguide = s.ra_guide_px or 0.0
        rapos += raraw - prev_raraw - prev_raguide
        out.append(rapos)
        prev_raraw = raraw
        prev_raguide = raguide if undo_corrections else 0.0
    return out
