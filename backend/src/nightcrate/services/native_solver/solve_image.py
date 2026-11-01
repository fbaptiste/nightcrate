"""Synchronous orchestration for one built-in plate solve."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import numpy as np

from nightcrate.services import pixel_loader, pxiproject_io, xisf_io
from nightcrate.services.coordinate_format import format_dec_dms, format_ra_hms
from nightcrate.services.plate_solve_models import (
    AttemptOutcome,
    ImageReadError,
    PlateSolveResult,
    SolveAttempt,
    SolveStep,
)
from nightcrate.services.star_catalog import handles
from nightcrate.services.star_catalog.ranges import built_layers, built_ranges, range_for_field
from nightcrate.services.star_catalog.store import SIRIL_SOURCE, installed

from .extract import _has_bayer_header, extract_for_index, extract_near
from .hints import SolveHints, hints_for
from .index_search import search_index
from .messages import MESSAGES
from .models import DetectedStars, SolveOutcome, SolveReporter
from .near_catalog import search_near_catalog

_OVERALL_SECONDS = 60.0
_NEAR_SECONDS = 20.0
_BLIND_KNOWN_SECONDS = 10.0
_BLIND_UNKNOWN_SECONDS = 30.0


@dataclass
class _Attempt:
    outcome: SolveOutcome
    path: str


class _RecordingReporter:
    """Collect result history while forwarding live reporter events."""

    def __init__(self, delegate: SolveReporter) -> None:
        self.delegate = delegate
        self.attempts: list[SolveAttempt] = []
        self.current: SolveAttempt | None = None
        self._started = 0.0

    def plan(self, steps: list[SolveStep]) -> None:
        self.delegate.plan(list(steps))

    def start(self, attempt: SolveAttempt, *, started_at: float | None = None) -> None:
        if self.current is not None:
            raise RuntimeError("a solve attempt is already active")
        self.current = attempt
        self._started = time.perf_counter() if started_at is None else started_at
        self.attempts.append(attempt)
        self.delegate.start(attempt)

    def searched(self, layers: list[str], ranges: list[str]) -> None:
        if self.current is None:
            raise RuntimeError("searched layers require an active solve attempt")
        for layer in layers:
            if layer not in self.current.layers:
                self.current.layers.append(layer)
        for range_id in ranges:
            if range_id not in self.current.ranges:
                self.current.ranges.append(range_id)
        self.delegate.searched(list(layers), list(ranges))

    def finish(self, outcome: AttemptOutcome, *, detail: str | None = None) -> None:
        if self.current is None:
            raise RuntimeError("finishing requires an active solve attempt")
        self.current.outcome = outcome
        self.current.seconds = time.perf_counter() - self._started
        self.current.detail = detail
        self.delegate.finish(outcome, detail=detail)
        self.current = None

    def set_sources(self, hints: SolveHints) -> None:
        if self.current is None:
            raise RuntimeError("setting sources requires an active solve attempt")
        self.current.position_source = hints.position_source
        self.current.scale_source = hints.scale_source
        self.delegate.set_sources(hints.position_source, hints.scale_source)


def _unsolved(
    reason: str, *, detected: int = 0, minimum: int = 0, **values: object
) -> PlateSolveResult:
    template = MESSAGES[reason]
    message = template.format(n=detected, m=minimum, **values)
    return PlateSolveResult(
        solved=False,
        solver="native",
        error_message=message,
        failure_reason=reason,
        stars_detected=detected or None,
    )


def _solved(outcome: SolveOutcome, path: str, elapsed: float) -> PlateSolveResult:
    if outcome.wcs is None:
        raise ValueError("a solved outcome must include WCS data")
    wcs = outcome.wcs
    from nightcrate.services.plate_solve import pixel_scale_from_cd, rotation_from_cd

    scale = pixel_scale_from_cd(float(wcs.cd[1, 0]), float(wcs.cd[1, 1]))
    return PlateSolveResult(
        solved=True,
        solver="native",
        star_catalog=f"Siril Gaia DR3 astrometry {SIRIL_SOURCE.version}",
        stars_detected=outcome.detected_count,
        stars_matched=outcome.matched_count,
        rms_px=outcome.rms_px,
        rms_arcsec=outcome.rms_arcsec,
        log_odds=outcome.log_odds,
        solve_path=path,
        scale_stage=outcome.scale_stage,
        ra_deg=round(wcs.crval_ra, 6),
        dec_deg=round(wcs.crval_dec, 6),
        ra_hms=format_ra_hms(wcs.crval_ra),
        dec_dms=format_dec_dms(wcs.crval_dec),
        pixel_scale_arcsec=round(scale, 3),
        rotation_deg=round(rotation_from_cd(float(wcs.cd[0, 1]), float(wcs.cd[1, 1])), 3),
        fov_width_arcmin=round(scale * wcs.width / 60.0, 2),
        fov_height_arcmin=round(scale * wcs.height / 60.0, 2),
        image_width=wcs.width,
        image_height=wcs.height,
        cd1_1=float(wcs.cd[0, 0]),
        cd1_2=float(wcs.cd[0, 1]),
        cd2_1=float(wcs.cd[1, 0]),
        cd2_2=float(wcs.cd[1, 1]),
        crpix1=wcs.crpix[0],
        crpix2=wcs.crpix[1],
        solve_time_seconds=round(elapsed, 1),
    )


def _missing_range_detail(known_range: object | None) -> str | None:
    if known_range is None:
        return None
    return f"{known_range.name} ({known_range.id}) is not built"


def solve_image(
    image_path: str,
    hdu: int,
    *,
    ra_hint: float | None,
    dec_hint: float | None,
    fov_hint: float | None,
    scale_hint_arcsec: float | None = None,
    ignore_position: bool = False,
    ignore_scale: bool = False,
    cancel: threading.Event,
    reporter: SolveReporter,
) -> PlateSolveResult:
    """Load, extract and solve using the approved fixed search sequence."""
    started = time.perf_counter()
    overall_deadline = started + _OVERALL_SECONDS
    if installed() is None:
        return _unsolved("stars_not_installed")

    events = _RecordingReporter(reporter)
    events.start(
        SolveAttempt(
            solver="native",
            step="load",
            position_source=("request" if ra_hint is not None and dec_hint is not None else "none"),
            scale_source=(
                "request" if scale_hint_arcsec is not None or fov_hint is not None else "none"
            ),
        ),
        started_at=started,
    )

    def done(result: PlateSolveResult) -> PlateSolveResult:
        result.attempts = [attempt.model_copy(deep=True) for attempt in events.attempts]
        return result

    def read_image(call):
        try:
            return call()
        except FileNotFoundError:
            raise
        except (OSError, ValueError, xisf_io.XISFError, pxiproject_io.PxiProjectError) as exc:
            raise ImageReadError(str(exc)) from exc

    source, file_type, image_index = read_image(lambda: pixel_loader.resolve(image_path))
    from nightcrate.services.plate_solve import read_header_cards

    cards = read_image(lambda: read_header_cards(source, file_type, image_index, hdu))
    if cancel.is_set():
        events.finish("cancelled")
        return done(_unsolved("cancelled"))
    if time.perf_counter() >= overall_deadline:
        events.finish("overall_timeout")
        return done(_unsolved("time_limit"))
    data = read_image(lambda: pixel_loader.load_normalized_mono(image_path, hdu))
    height, width = np.asarray(data).shape
    hints = hints_for(
        cards,
        image_height=height,
        ra_hint=ra_hint,
        dec_hint=dec_hint,
        scale_hint_arcsec=scale_hint_arcsec,
        fov_hint=fov_hint,
        ignore_position=ignore_position,
        ignore_scale=ignore_scale,
    )
    events.set_sources(hints)
    ready_ranges = built_ranges()
    layer_names = built_layers()
    position = (
        (float(hints.ra_deg), float(hints.dec_deg))
        if hints.ra_deg is not None and hints.dec_deg is not None
        else None
    )
    field_deg = None
    known_range = None
    if hints.scale_arcsec is not None:
        field_deg = hints.scale_arcsec * max(width, height) / 3600.0
        known_range = range_for_field(field_deg)
    missing_range = (
        known_range if known_range is not None and known_range.id not in ready_ranges else None
    )

    if position is not None and hints.scale_arcsec is not None:
        planned: list[SolveStep] = [
            "near_index" if missing_range is None else "near_catalog",
            "blind_known_scale",
            "blind_unknown_scale",
        ]
    elif position is not None:
        planned = ["blind_unknown_scale", "near_catalog"]
    elif hints.scale_arcsec is not None:
        planned = ["blind_known_scale", "blind_unknown_scale"]
    else:
        planned = ["blind_unknown_scale"]
    events.plan(planned)

    def advance(step: SolveStep, *, terminal: bool = False) -> None:
        nonlocal planned
        remaining = [] if terminal else [item for item in planned if item != step]
        if remaining != planned:
            planned = remaining
            events.plan(planned)

    def deadline_result(*, detected: int = 0) -> PlateSolveResult:
        if missing_range is not None:
            return done(
                _unsolved(
                    "field_not_built",
                    detected=detected,
                    field=field_deg,
                    name=missing_range.name,
                )
            )
        return done(_unsolved("time_limit", detected=detected))

    def stopped_result(*, detected: int = 0) -> PlateSolveResult | None:
        if cancel.is_set():
            if events.current is not None:
                step = events.current.step
                events.finish("cancelled")
                advance(step, terminal=True)
            return done(_unsolved("cancelled", detected=detected))
        if time.perf_counter() < overall_deadline:
            return None
        if events.current is not None:
            step = events.current.step
            events.finish("overall_timeout")
            advance(step, terminal=True)
        return deadline_result(detected=detected)

    if result := stopped_result():
        return result
    if position is None and not layer_names:
        events.finish("skipped", detail="No field ranges are built")
        advance("load", terminal=True)
        return done(_unsolved("no_ranges"))

    bayer = _has_bayer_header(cards)
    extraction_cache: dict[
        tuple[str, float | None], tuple[DetectedStars, DetectedStars | None]
    ] = {}
    searches_ran = False
    timed_out = False
    maximum_detected = 0
    possible_minimums: list[int] = []
    extraction_stop: PlateSolveResult | None = None

    def extract(
        profile: str, scale: float | None
    ) -> tuple[DetectedStars, DetectedStars | None] | None:
        nonlocal extraction_stop, maximum_detected
        key = (profile, scale)
        if key not in extraction_cache:
            extraction_stop = stopped_result(detected=maximum_detected)
            if extraction_stop is not None:
                return None
            if profile == "near":
                detections = extract_near(
                    data,
                    bayer_mosaic=bayer,
                    pixel_scale_arcsec=scale,
                )
                value = (detections, None)
            else:
                detections, quads = extract_for_index(
                    data,
                    bayer_mosaic=bayer,
                    pixel_scale_arcsec=scale,
                )
                value = (detections, quads)
            extraction_cache[key] = value
            maximum_detected = max(maximum_detected, len(value[0]))
            extraction_stop = stopped_result(detected=maximum_detected)
            if (
                extraction_stop is None
                and events.current is not None
                and events.current.step == "load"
            ):
                events.finish("solved", detail=f"{len(value[0])} stars found")
        return extraction_cache[key]

    def start_attempt(step: SolveStep) -> None:
        events.start(
            SolveAttempt(
                solver="native",
                step=step,
                position_source=hints.position_source,
                scale_source=hints.scale_source,
            )
        )

    def outcome_name(outcome: SolveOutcome) -> AttemptOutcome:
        if outcome.solved:
            return "solved"
        if outcome.status == "ambiguous":
            return "ambiguous"
        if outcome.status == "cancelled":
            return "cancelled"
        if outcome.status == "time_limit":
            return "overall_timeout" if time.perf_counter() >= overall_deadline else "step_timeout"
        return "no_match"

    def outcome_detail() -> str | None:
        return _missing_range_detail(missing_range)

    catalog = handles.get_catalog()
    layers_by_name = dict(zip(layer_names, handles.get_layers(layer_names), strict=True))

    def run_index(
        *,
        step: SolveStep,
        scale: float | None,
        near: tuple[float, float] | None,
        seconds: float,
        names: list[str],
        path: str,
    ) -> _Attempt | None:
        nonlocal searches_ran, timed_out
        possible_minimums.append(12)
        extracted = extract("index", scale)
        if extraction_stop is not None:
            return None
        if extracted is None:
            raise RuntimeError("index extraction stopped without a result")
        detections, quads = extracted
        if quads is None:
            raise RuntimeError("index extraction did not return quad detections")
        start_attempt(step)
        if len(detections) < 12:
            events.finish("too_few_stars", detail=f"{len(detections)} stars found; 12 required")
            advance(step)
            return None
        searches_ran = True
        deadline = min(overall_deadline, time.perf_counter() + seconds)
        outcome = search_index(
            detections,
            quads,
            [layers_by_name[name] for name in names],
            catalog,
            pixel_scale_arcsec=scale,
            near=near,
            deadline=deadline,
            cancel=cancel,
            reporter=events,
        )
        timed_out = timed_out or outcome.status == "time_limit"
        recorded_outcome = outcome_name(outcome)
        terminal = recorded_outcome in {
            "solved",
            "ambiguous",
            "cancelled",
            "overall_timeout",
        }
        events.finish(recorded_outcome, detail=outcome_detail())
        advance(step, terminal=terminal)
        return _Attempt(outcome, path)

    def run_catalog() -> _Attempt | None:
        nonlocal searches_ran, timed_out
        step: SolveStep = "near_catalog"
        possible_minimums.append(10)
        extracted = extract("near", hints.scale_arcsec)
        if extraction_stop is not None:
            return None
        if extracted is None:
            raise RuntimeError("catalog extraction stopped without a result")
        detections, _ = extracted
        start_attempt(step)
        if len(detections) < 10:
            events.finish("too_few_stars", detail=f"{len(detections)} stars found; 10 required")
            advance(step)
            return None
        searches_ran = True
        outcome = search_near_catalog(
            detections,
            catalog,
            ra=float(hints.ra_deg),
            dec=float(hints.dec_deg),
            pixel_scale_arcsec=hints.scale_arcsec,
            deadline=min(overall_deadline, time.perf_counter() + _NEAR_SECONDS),
            cancel=cancel,
        )
        timed_out = timed_out or outcome.status == "time_limit"
        recorded_outcome = outcome_name(outcome)
        terminal = recorded_outcome in {
            "solved",
            "ambiguous",
            "cancelled",
            "overall_timeout",
        }
        events.finish(recorded_outcome, detail=outcome_detail())
        advance(step, terminal=terminal)
        return _Attempt(outcome, "near_catalog")

    def finish(search_attempt: _Attempt | None) -> PlateSolveResult | None:
        if extraction_stop is not None:
            return extraction_stop
        if search_attempt is None:
            return None
        outcome = search_attempt.outcome
        if outcome.solved:
            return done(_solved(outcome, search_attempt.path, time.perf_counter() - started))
        if outcome.status == "ambiguous":
            return done(_unsolved("ambiguous", detected=outcome.detected_count))
        if outcome.status == "cancelled":
            return done(_unsolved("cancelled", detected=outcome.detected_count))
        if outcome.status == "time_limit" and time.perf_counter() >= overall_deadline:
            return deadline_result(detected=outcome.detected_count)
        return None

    def skip(step: SolveStep, detail: str) -> None:
        start_attempt(step)
        events.finish("skipped", detail=detail)
        advance(step)

    if position is not None and hints.scale_arcsec is not None:
        if missing_range is None:
            result = finish(
                run_index(
                    step="near_index",
                    scale=hints.scale_arcsec,
                    near=position,
                    seconds=_NEAR_SECONDS,
                    names=layer_names,
                    path="near_index",
                )
            )
        else:
            extract("near", hints.scale_arcsec)
            if extraction_stop is not None:
                return extraction_stop
            skip("near_index", _missing_range_detail(missing_range) or "field range is not built")
            result = finish(run_catalog())
        if result is not None:
            return result

    if position is not None and hints.scale_arcsec is None:
        if layer_names:
            result = finish(
                run_index(
                    step="blind_unknown_scale",
                    scale=None,
                    near=None,
                    seconds=_BLIND_UNKNOWN_SECONDS,
                    names=layer_names,
                    path="blind",
                )
            )
            if result is not None:
                return result
        else:
            extract("near", None)
            if extraction_stop is not None:
                return extraction_stop
            skip("blind_unknown_scale", "No field ranges are built")
        result = finish(run_catalog())
        if result is not None:
            return result
    else:
        if layer_names and hints.scale_arcsec is not None:
            result = finish(
                run_index(
                    step="blind_known_scale",
                    scale=hints.scale_arcsec,
                    near=None,
                    seconds=_BLIND_KNOWN_SECONDS,
                    names=layer_names,
                    path="blind",
                )
            )
            if result is not None:
                return result
        elif hints.scale_arcsec is not None:
            extract("index", hints.scale_arcsec)
            if extraction_stop is not None:
                return extraction_stop
            skip("blind_known_scale", "No field ranges are built")
        if layer_names:
            result = finish(
                run_index(
                    step="blind_unknown_scale",
                    scale=None,
                    near=None,
                    seconds=_BLIND_UNKNOWN_SECONDS,
                    names=layer_names,
                    path="blind",
                )
            )
            if result is not None:
                return result
        else:
            if events.current is not None and events.current.step == "load":
                extract("index", None)
                if extraction_stop is not None:
                    return extraction_stop
            skip("blind_unknown_scale", "No field ranges are built")

    if cancel.is_set():
        return done(_unsolved("cancelled", detected=maximum_detected))
    if missing_range is not None:
        return done(
            _unsolved(
                "field_not_built",
                detected=maximum_detected,
                field=field_deg,
                name=missing_range.name,
            )
        )
    if timed_out or time.perf_counter() >= overall_deadline:
        return done(_unsolved("time_limit", detected=maximum_detected))
    if not searches_ran:
        return done(
            _unsolved(
                "too_few_stars",
                detected=maximum_detected,
                minimum=min(possible_minimums, default=10),
            )
        )
    return done(_unsolved("no_match", detected=maximum_detected))
