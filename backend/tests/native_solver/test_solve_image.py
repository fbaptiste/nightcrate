from __future__ import annotations

import dataclasses
import json
import threading
from types import SimpleNamespace

import numpy as np
import pytest
from astropy.io import fits
from PIL import Image

from nightcrate.core import app_config
from nightcrate.services import plate_solve
from nightcrate.services.native_solver import solve_image as subject
from nightcrate.services.native_solver.geometry import pixel_to_world, world_to_pixel
from nightcrate.services.native_solver.models import (
    DetectedStars,
    NullSolveReporter,
    SolveOutcome,
    TanWCS,
)
from nightcrate.services.plate_solve_models import ImageReadError
from nightcrate.services.star_catalog import handles, ranges, store
from nightcrate.services.star_catalog import index as catalog_index
from nightcrate.services.star_catalog.index import BandSpec, write_band
from nightcrate.services.star_catalog.ranges import FIELD_RANGES
from tests.native_solver.synthetic import make_case
from tests.star_catalog.conftest import SyntheticStar, write_siril_catalog


class _Reporter:
    def __init__(self):
        self.plans = []
        self.attempts = []
        self.sources = []

    def plan(self, steps):
        self.plans.append(list(steps))

    def start(self, attempt):
        self.attempts.append(attempt)

    def searched(self, layers, ranges):
        del layers, ranges

    def set_sources(self, position_source, scale_source):
        self.sources.append((position_source, scale_source))

    def finish(self, outcome, *, detail=None):
        del outcome, detail


def _detections(count: int, width: int = 2400, height: int = 1600) -> DetectedStars:
    values = np.arange(count, dtype=np.float64)
    return DetectedStars(values + 10, values + 20, values + 1, np.full(count, 3.0), width, height)


def _outcome(
    status: str,
    *,
    detections: int = 20,
    scale_stage: str | None = None,
) -> SolveOutcome:
    solved = status == "solved"
    wcs = (
        TanWCS(
            83.82,
            -5.39,
            np.array([[0.00036, -0.000208], [0.000208, 0.00036]]),
            2400,
            1600,
        )
        if solved
        else None
    )
    return SolveOutcome(
        status,
        "verified" if solved else status,
        wcs=wcs,
        log_odds=50.0 if solved else float("-inf"),
        matched_count=15 if solved else 0,
        detected_count=detections,
        rms_px=0.2 if solved else None,
        rms_arcsec=0.3 if solved else None,
        scale_stage=scale_stage,
    )


def _write_empty_layer(path, name: str, source_hash: str) -> None:
    metadata = {
        "format": catalog_index.INDEX_FORMAT,
        "version": catalog_index.INDEX_FORMAT_VERSION,
        "epoch": 2026.0,
        "source": {"uncompressed_sha256": source_hash},
        "band": ranges.LAYERS[name].__dict__,
        "counts": {"tiles": 0, "stars": 0, "quads": 0},
        "layout": {
            "tile_offset": catalog_index.HEADER_SIZE,
            "star_offset": catalog_index.HEADER_SIZE,
            "quad_offset": catalog_index.HEADER_SIZE,
        },
    }
    encoded = json.dumps(metadata).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        catalog_index.MAGIC
        + len(encoded).to_bytes(4, "little")
        + encoded
        + b"\0" * (catalog_index.HEADER_SIZE - 12 - len(encoded))
    )


def _setup(monkeypatch, *, ready: set[str], count: int = 20, mock_image: bool = True):
    layer_names = sorted(
        {name for item in FIELD_RANGES if item.id in ready for name in item.layers}
    )
    detections = _detections(count)
    monkeypatch.setattr(subject, "installed", lambda: SimpleNamespace(version="1.0.0"))
    monkeypatch.setattr(subject, "built_ranges", lambda: set(ready))
    monkeypatch.setattr(subject, "built_layers", lambda: list(layer_names))
    monkeypatch.setattr(subject.handles, "get_catalog", lambda: object())
    monkeypatch.setattr(
        subject.handles,
        "get_layers",
        lambda names: [SimpleNamespace(name=name) for name in names],
    )
    if mock_image:
        monkeypatch.setattr(subject.pixel_loader, "resolve", lambda _path: (object(), "fits", 0))
        monkeypatch.setattr(
            subject.pixel_loader,
            "load_normalized_mono",
            lambda _path, _hdu: np.zeros((1600, 2400), dtype=np.float32),
        )
        monkeypatch.setattr(plate_solve, "read_header_cards", lambda *_args: [])
    monkeypatch.setattr(subject, "extract_near", lambda *_args, **_kwargs: detections)
    monkeypatch.setattr(
        subject,
        "extract_for_index",
        lambda *_args, **_kwargs: (detections, detections),
    )
    return detections


def _solve_mock(
    image_path: str,
    *,
    ra: float | None = None,
    dec: float | None = None,
    scale: float | None = None,
    reporter=None,
    cancel=None,
):
    return subject.solve_image(
        image_path,
        0,
        ra_hint=ra,
        dec_hint=dec,
        fov_hint=scale * 1600.0 / 3600.0 if scale is not None else None,
        cancel=cancel or threading.Event(),
        reporter=reporter or NullSolveReporter(),
    )


@pytest.mark.parametrize("site", ["resolve", "header", "pixels"])
def test_image_read_sites_raise_domain_error(monkeypatch, site):
    _setup(monkeypatch, ready={"0.4-10"})
    if site == "resolve":
        monkeypatch.setattr(
            subject.pixel_loader,
            "resolve",
            lambda _path: (_ for _ in ()).throw(OSError("resolve failed")),
        )
    elif site == "header":
        monkeypatch.setattr(
            plate_solve,
            "read_header_cards",
            lambda *_args: (_ for _ in ()).throw(OSError("header failed")),
        )
    else:
        monkeypatch.setattr(
            subject.pixel_loader,
            "load_normalized_mono",
            lambda *_args: (_ for _ in ()).throw(OSError("pixels failed")),
        )

    with pytest.raises(ImageReadError, match=f"{site} failed"):
        _solve_mock("broken.fits")


def test_real_garbage_fits_raises_image_read_error(tmp_path, monkeypatch):
    _setup(monkeypatch, ready={"0.4-10"}, mock_image=False)
    path = tmp_path / "garbage.fits"
    path.write_bytes(b"not a FITS file")

    with pytest.raises(ImageReadError):
        _solve_mock(str(path))


def test_real_missing_file_raises_file_not_found(tmp_path, monkeypatch):
    _setup(monkeypatch, ready={"0.4-10"}, mock_image=False)

    with pytest.raises(FileNotFoundError):
        _solve_mock(str(tmp_path / "missing.fits"))


def _install_real_assets(tmp_path, monkeypatch, *, seed: int):
    handles.close_all()
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path / "app")
    case = make_case(
        seed,
        ra=83.82,
        dec=-5.39,
        width=800,
        height=600,
        scale_arcsec=3.0,
        rotation_deg=30.0,
        parity=1,
        star_count=75,
    )
    path = write_siril_catalog(
        store.catalog_path(),
        [
            SyntheticStar(float(ra), float(dec), g=float(g))
            for ra, dec, g in zip(case.catalog.ra, case.catalog.dec, case.catalog.g, strict=True)
        ],
    )
    source = dataclasses.replace(
        store.SIRIL_SOURCE,
        uncompressed_size=path.stat().st_size,
        uncompressed_sha256="synthetic-catalog",
    )
    monkeypatch.setattr(store, "SIRIL_SOURCE", source)
    monkeypatch.setattr(catalog_index, "SIRIL_SOURCE", source)
    monkeypatch.setattr(subject, "SIRIL_SOURCE", source)
    (path.parent / "version.json").write_text(
        json.dumps(
            {
                "version": source.version,
                "source": "import",
                "installed_at": "2026-10-29T00:00:00+00:00",
                "uncompressed_sha256": source.uncompressed_sha256,
            }
        ),
        encoding="utf-8",
    )
    import astropy.units as u
    from astropy_healpix import HEALPix

    hp = HEALPix(nside=2**8, order="nested", frame="icrs")
    tile = int(hp.lonlat_to_healpix(case.truth.crval_ra * u.deg, case.truth.crval_dec * u.deg))
    write_band(
        ranges.layer_path("q008"),
        BandSpec("q008", 0.01, 1.0, 8, 100, 12),
        [(tile, case.catalog)],
        source_identity={"uncompressed_sha256": source.uncompressed_sha256},
    )
    for name in ("q016", "q032", "q064", "q128", "q256"):
        _write_empty_layer(ranges.layer_path(name), name, source.uncompressed_sha256)
    ranges.write_manifest({"0.4-10"})
    return case


def test_solve_fits_end_to_end(tmp_path, monkeypatch):
    case = _install_real_assets(tmp_path, monkeypatch, seed=810)
    path = tmp_path / "synthetic.fits"
    hdu = fits.PrimaryHDU(case.image.astype(np.float32))
    hdu.header["RA"] = case.truth.crval_ra
    hdu.header["DEC"] = case.truth.crval_dec
    hdu.header["XPIXSZ"] = 3.76
    hdu.header["FOCALLEN"] = 206.265 * 3.76 / case.truth.scale_arcsec
    hdu.writeto(path)
    messages: list[str] = []
    try:
        result = subject.solve_image(
            str(path),
            0,
            ra_hint=None,
            dec_hint=None,
            fov_hint=None,
            cancel=threading.Event(),
            reporter=plate_solve._NativeProgressReporter(messages.append),
        )
        assert result.solved, result.error_message
        assert result.solver == "native"
        assert result.solve_path == "near_index"
        near_attempt = next(attempt for attempt in result.attempts if attempt.step == "near_index")
        assert near_attempt.layers
        assert set(near_attempt.layers) < {"q008", "q016", "q032", "q064", "q128", "q256"}
        assert result.crpix1 == (case.truth.width + 1) / 2
        assert result.crpix2 == (case.truth.height + 1) / 2
        assert result.cd1_1 is not None
        solved = TanWCS(
            result.ra_deg,
            result.dec_deg,
            np.array([[result.cd1_1, result.cd1_2], [result.cd2_1, result.cd2_2]]),
            result.image_width,
            result.image_height,
        )
        ra, dec = pixel_to_world(case.truth, np.array([[200.0, 300.0]]))
        recovered, valid = world_to_pixel(solved, ra, dec)
        assert valid.all()
        assert np.linalg.norm(recovered[0] - [200.0, 300.0]) < 0.3
    finally:
        handles.close_all()


def test_headerless_png_solves_blind(tmp_path, monkeypatch):
    case = _install_real_assets(tmp_path, monkeypatch, seed=811)
    path = tmp_path / "headerless.png"
    Image.fromarray(np.round(case.image * 255).astype(np.uint8)).save(path)
    try:
        result = subject.solve_image(
            str(path),
            0,
            ra_hint=None,
            dec_hint=None,
            fov_hint=None,
            cancel=threading.Event(),
            reporter=NullSolveReporter(),
        )
        assert result.solved, result.error_message
        assert result.solve_path == "blind"
        assert result.scale_stage == "unknown"
    finally:
        handles.close_all()


def test_binned_header_scale_recovered_by_blind(monkeypatch):
    _setup(monkeypatch, ready={"0.4-10"})
    scales: list[float | None] = []
    original_extract = subject.extract_for_index

    def extract(data, *, bayer_mosaic, pixel_scale_arcsec):
        scales.append(pixel_scale_arcsec)
        return original_extract(
            data, bayer_mosaic=bayer_mosaic, pixel_scale_arcsec=pixel_scale_arcsec
        )

    monkeypatch.setattr(subject, "extract_for_index", extract)
    calls = 0

    def search(*_args, **kwargs):
        nonlocal calls
        calls += 1
        if calls < 3:
            return _outcome("not_solved")
        return _outcome("solved", scale_stage="unknown")

    monkeypatch.setattr(subject, "search_index", search)
    monkeypatch.setattr(
        subject, "search_near_catalog", lambda *_args, **_kwargs: _outcome("not_solved")
    )
    result = _solve_mock("binned.fits", ra=83.82, dec=-5.39, scale=3.0)
    assert result.solve_path == "blind"
    assert result.scale_stage == "unknown"
    assert scales[-1] is None


def test_position_3_degrees_off_falls_back_to_blind(monkeypatch):
    _setup(monkeypatch, ready={"0.4-10"})
    calls = 0

    def search(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return _outcome("not_solved") if calls == 1 else _outcome("solved", scale_stage="known")

    monkeypatch.setattr(subject, "search_index", search)
    result = _solve_mock("offset.fits", ra=86.82, dec=-5.39, scale=1.5)
    assert result.solve_path == "blind"


def test_position_no_scale_unaffected_by_unrelated_range(monkeypatch):
    for ready in (set(), {"0.2-0.4"}):
        _setup(monkeypatch, ready=ready, count=11)
        monkeypatch.setattr(
            subject,
            "search_near_catalog",
            lambda *_args, **_kwargs: _outcome("solved", detections=11, scale_stage="unknown"),
        )
        result = _solve_mock("target.fits", ra=83.82, dec=-5.39)
        assert result.solve_path == "near_catalog"


def test_near_budget_leaves_time_for_blind(monkeypatch):
    _setup(monkeypatch, ready={"0.4-10"})
    calls: list[float | None] = []

    def search(*_args, **kwargs):
        calls.append(kwargs["pixel_scale_arcsec"])
        return (
            _outcome("time_limit") if len(calls) == 1 else _outcome("solved", scale_stage="known")
        )

    monkeypatch.setattr(subject, "search_index", search)
    result = _solve_mock("budget.fits", ra=83.82, dec=-5.39, scale=1.5)
    assert result.solved
    assert len(calls) >= 2


def test_scale_known_exhaustion_leaves_time_for_unknown(monkeypatch):
    _setup(monkeypatch, ready={"0.4-10"})
    calls: list[float | None] = []

    def search(*_args, **kwargs):
        calls.append(kwargs["pixel_scale_arcsec"])
        return (
            _outcome("time_limit")
            if kwargs["pixel_scale_arcsec"] is not None
            else _outcome("solved", scale_stage="unknown")
        )

    monkeypatch.setattr(subject, "search_index", search)
    result = _solve_mock("budget.fits", scale=1.5)
    assert result.solved
    assert calls == [1.5, None]


def test_cancel_during_pixel_load_stops_before_search(monkeypatch):
    _setup(monkeypatch, ready={"0.4-10"})
    cancel = threading.Event()

    def load(_path, _hdu):
        cancel.set()
        return np.zeros((1600, 2400), dtype=np.float32)

    monkeypatch.setattr(subject.pixel_loader, "load_normalized_mono", load)
    monkeypatch.setattr(
        subject,
        "search_index",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("search ran")),
    )

    result = subject.solve_image(
        "cancel.fits",
        0,
        ra_hint=None,
        dec_hint=None,
        fov_hint=None,
        cancel=cancel,
        reporter=NullSolveReporter(),
    )

    assert result.failure_reason == "cancelled"


def test_overall_deadline_during_pixel_load_stops_before_search(monkeypatch):
    _setup(monkeypatch, ready={"0.4-10"})
    times = iter((0.0, 0.0, 61.0, 61.0))
    monkeypatch.setattr(subject.time, "perf_counter", lambda: next(times))
    monkeypatch.setattr(
        subject,
        "search_index",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("search ran")),
    )

    result = _solve_mock("timeout.fits")

    assert result.failure_reason == "time_limit"


def test_field_not_built_precedes_deadline_during_pixel_load(monkeypatch):
    _setup(monkeypatch, ready={"0.2-0.4"})
    times = iter((0.0, 0.0, 61.0, 61.0))
    monkeypatch.setattr(subject.time, "perf_counter", lambda: next(times))
    monkeypatch.setattr(
        subject,
        "search_index",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("search ran")),
    )

    result = _solve_mock("timeout.fits", scale=1.5)

    assert result.failure_reason == "field_not_built"


def test_deadline_during_header_read_stops_before_pixel_load(monkeypatch):
    _setup(monkeypatch, ready={"0.4-10"})
    now = [0.0]

    def read_header(*_args):
        now[0] = 61.0
        return []

    monkeypatch.setattr(subject.time, "perf_counter", lambda: now[0])
    monkeypatch.setattr(plate_solve, "read_header_cards", read_header)
    monkeypatch.setattr(
        subject.pixel_loader,
        "load_normalized_mono",
        lambda *_args: (_ for _ in ()).throw(AssertionError("pixels loaded")),
    )

    result = _solve_mock("timeout.fits")

    assert result.failure_reason == "time_limit"


def test_deadline_before_next_step_skips_new_extraction(monkeypatch):
    detections = _setup(monkeypatch, ready={"0.4-10"})
    now = [0.0]
    extracted_scales: list[float | None] = []

    def extract(*_args, pixel_scale_arcsec, **_kwargs):
        extracted_scales.append(pixel_scale_arcsec)
        return detections, detections

    def search(*_args, **_kwargs):
        now[0] = 61.0
        return _outcome("not_solved")

    monkeypatch.setattr(subject.time, "perf_counter", lambda: now[0])
    monkeypatch.setattr(subject, "extract_for_index", extract)
    monkeypatch.setattr(subject, "search_index", search)

    result = _solve_mock("timeout.fits", scale=1.5)

    assert result.failure_reason == "time_limit"
    assert extracted_scales == [1.5]


def test_catalogue_timeout_reports_time_limit(monkeypatch):
    _setup(monkeypatch, ready=set())
    monkeypatch.setattr(
        subject, "search_near_catalog", lambda *_args, **_kwargs: _outcome("time_limit")
    )
    result = _solve_mock("timeout.fits", ra=83.82, dec=-5.39)
    assert result.failure_reason == "time_limit"


def test_blind_timeout_then_catalogue_miss_reports_time_limit(monkeypatch):
    _setup(monkeypatch, ready={"0.4-10"})
    monkeypatch.setattr(subject, "search_index", lambda *_args, **_kwargs: _outcome("time_limit"))
    monkeypatch.setattr(
        subject, "search_near_catalog", lambda *_args, **_kwargs: _outcome("not_solved")
    )
    result = _solve_mock("timeout.fits", ra=83.82, dec=-5.39)
    assert result.failure_reason == "time_limit"


def test_field_not_built_wins_over_time_limit(monkeypatch):
    _setup(monkeypatch, ready={"0.2-0.4"})
    monkeypatch.setattr(
        subject, "search_near_catalog", lambda *_args, **_kwargs: _outcome("time_limit")
    )
    monkeypatch.setattr(subject, "search_index", lambda *_args, **_kwargs: _outcome("time_limit"))
    result = _solve_mock("field.fits", ra=83.82, dec=-5.39, scale=1.5)
    assert result.failure_reason == "field_not_built"


def test_field_not_built_wins_when_catalog_reaches_overall_deadline(monkeypatch):
    _setup(monkeypatch, ready={"0.4-10"})
    now = [0.0]
    monkeypatch.setattr(subject.time, "perf_counter", lambda: now[0])

    def timeout(*_args, **_kwargs):
        now[0] = 61.0
        return _outcome("time_limit")

    monkeypatch.setattr(subject, "search_near_catalog", timeout)
    result = _solve_mock("field.fits", ra=83.82, dec=-5.39, scale=0.45)

    assert result.failure_reason == "field_not_built"


def test_field_not_built_message(monkeypatch):
    _setup(monkeypatch, ready={"0.4-10"})
    monkeypatch.setattr(
        subject, "search_near_catalog", lambda *_args, **_kwargs: _outcome("not_solved")
    )
    monkeypatch.setattr(subject, "search_index", lambda *_args, **_kwargs: _outcome("not_solved"))
    result = _solve_mock("field.fits", ra=83.82, dec=-5.39, scale=0.45)
    assert result.error_message == (
        "This image's field (0.30°) needs “Narrow fields” in Admin → Plate-solving stars, "
        "which isn't built yet. Build it to blind solve this image."
    )


def test_field_not_built_without_position(monkeypatch):
    _setup(monkeypatch, ready={"0.2-0.4"})
    monkeypatch.setattr(
        plate_solve,
        "read_header_cards",
        lambda *_args: [
            {"key": "FOCALLEN", "value": 206.265 * 3.76 / 1.5},
            {"key": "XPIXSZ", "value": 3.76},
        ],
    )
    monkeypatch.setattr(subject, "search_index", lambda *_args, **_kwargs: _outcome("not_solved"))

    result = _solve_mock("field.fits")

    assert result.error_message == (
        "This image's field (1.00°) needs “Standard” in Admin → Plate-solving stars, "
        "which isn't built yet. Build it to blind solve this image."
    )


def test_near_index_uses_all_built_layers(monkeypatch):
    _setup(monkeypatch, ready={"0.4-10"})
    received: list[str] = []

    def search(_detections, _quads, layers, *_args, **_kwargs):
        received.extend(layer.name for layer in layers)
        return _outcome("solved", scale_stage="known")

    monkeypatch.setattr(subject, "search_index", search)

    result = _solve_mock("near.fits", ra=83.82, dec=-5.39, scale=1.5)

    assert result.solved
    assert received == ["q008", "q016", "q032", "q064", "q128", "q256"]


def test_stars_not_installed(monkeypatch):
    monkeypatch.setattr(subject, "installed", lambda: None)
    result = subject.solve_image(
        "x.fits",
        0,
        ra_hint=None,
        dec_hint=None,
        fov_hint=None,
        cancel=threading.Event(),
        reporter=NullSolveReporter(),
    )
    assert result.failure_reason == "stars_not_installed"


def test_no_ranges_without_position(monkeypatch):
    _setup(monkeypatch, ready=set())
    monkeypatch.setattr(
        subject,
        "extract_for_index",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("index extraction ran")),
    )
    monkeypatch.setattr(
        subject,
        "extract_near",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("near extraction ran")),
    )
    result = _solve_mock("x.fits")
    assert result.failure_reason == "no_ranges"
    assert len(result.attempts) == 1
    assert result.attempts[0].step == "load"
    assert result.attempts[0].outcome == "skipped"
    assert result.attempts[0].detail == "No field ranges are built"


def test_no_gpu_during_solve(monkeypatch):
    _setup(monkeypatch, ready={"0.4-10"})
    monkeypatch.setattr(subject, "search_index", lambda *_args, **_kwargs: _outcome("solved"))
    import nightcrate.core.compute as compute
    import nightcrate.services.imaging as imaging

    before = compute._gpu_enabled

    def fail(*_args, **_kwargs):
        raise AssertionError("GPU called")

    monkeypatch.setattr(compute, "get_array_module", fail)
    monkeypatch.setattr(compute, "set_gpu_enabled", fail)
    monkeypatch.setattr(imaging, "get_array_module", fail)
    result = _solve_mock("cpu.fits", ra=83.82, dec=-5.39, scale=1.5)
    assert result.solved
    assert compute._gpu_enabled == before


def test_progress_messages(monkeypatch):
    _setup(monkeypatch, ready={"0.4-10"})
    monkeypatch.setattr(subject, "search_index", lambda *_args, **_kwargs: _outcome("solved"))
    messages: list[str] = []
    _solve_mock(
        "progress.fits",
        reporter=plate_solve._NativeProgressReporter(messages.append),
    )
    assert messages[0] == "Loading image"
    assert any(message.endswith("stars detected") for message in messages)
    assert "Blind solve" in messages


def test_attempt_order_plans_and_visited_layers(monkeypatch):
    _setup(monkeypatch, ready={"0.4-10"})
    reporter = _Reporter()

    def miss(_detections, _quads, _layers, *_args, reporter, **_kwargs):
        reporter.searched(["q032"], ["0.4-10"])
        return _outcome("not_solved")

    monkeypatch.setattr(subject, "search_index", miss)
    result = _solve_mock(
        "attempts.fits",
        ra=83.82,
        dec=-5.39,
        scale=1.5,
        reporter=reporter,
    )

    assert [attempt.step for attempt in result.attempts] == [
        "load",
        "near_index",
        "blind_known_scale",
        "blind_unknown_scale",
    ]
    assert [attempt.outcome for attempt in result.attempts[1:]] == [
        "no_match",
        "no_match",
        "no_match",
    ]
    assert all(attempt.layers == ["q032"] for attempt in result.attempts[1:])
    assert all(attempt.ranges == ["0.4-10"] for attempt in result.attempts[1:])
    assert all(attempt.detail is None for attempt in result.attempts[1:])
    assert result.attempts[0].detail == "20 stars found"
    assert reporter.sources == [("request", "request")]
    assert reporter.plans == [
        ["near_index", "blind_known_scale", "blind_unknown_scale"],
        ["blind_known_scale", "blind_unknown_scale"],
        ["blind_unknown_scale"],
        [],
    ]


def test_solved_attempt_clears_planned_steps(monkeypatch):
    _setup(monkeypatch, ready={"0.4-10"})
    reporter = _Reporter()
    monkeypatch.setattr(subject, "search_index", lambda *_args, **_kwargs: _outcome("solved"))

    result = _solve_mock("solved.fits", scale=1.5, reporter=reporter)

    assert result.solved
    assert reporter.plans[-1] == []
    assert result.attempts[-1].outcome == "solved"


def test_without_position_near_steps_are_absent(monkeypatch):
    _setup(monkeypatch, ready={"0.4-10"})
    monkeypatch.setattr(subject, "search_index", lambda *_args, **_kwargs: _outcome("not_solved"))

    result = _solve_mock("blind.fits", scale=1.5)

    assert all(not attempt.step.startswith("near_") for attempt in result.attempts)


def test_cancelled_search_records_cancelled_and_stops(monkeypatch):
    _setup(monkeypatch, ready={"0.4-10"})
    cancel = threading.Event()
    calls = 0

    def search(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        cancel.set()
        return _outcome("cancelled")

    monkeypatch.setattr(subject, "search_index", search)
    result = _solve_mock("cancel.fits", scale=1.5, cancel=cancel)

    assert result.failure_reason == "cancelled"
    assert calls == 1
    assert result.attempts[-1].outcome == "cancelled"


def test_missing_field_range_is_recorded_in_skipped_attempt(monkeypatch):
    _setup(monkeypatch, ready={"0.4-10"})
    monkeypatch.setattr(
        subject, "search_near_catalog", lambda *_args, **_kwargs: _outcome("not_solved")
    )
    monkeypatch.setattr(subject, "search_index", lambda *_args, **_kwargs: _outcome("not_solved"))

    result = _solve_mock("narrow.fits", ra=83.82, dec=-5.39, scale=0.45)

    assert result.failure_reason == "field_not_built"
    skipped = [attempt for attempt in result.attempts if attempt.outcome == "skipped"]
    assert skipped
    assert any("Narrow fields (0.2-0.4) is not built" in attempt.detail for attempt in skipped)


@pytest.mark.parametrize("with_position", (False, True))
def test_known_scale_runs_on_built_neighbouring_layers(monkeypatch, with_position):
    _setup(monkeypatch, ready={"0.4-10"})
    reporter = _Reporter()
    monkeypatch.setattr(
        subject, "search_near_catalog", lambda *_args, **_kwargs: _outcome("not_solved")
    )

    def miss(_detections, _quads, layers, *_args, reporter, **_kwargs):
        reporter.searched([layers[0].name], ["0.4-10"])
        return _outcome("not_solved")

    monkeypatch.setattr(subject, "search_index", miss)
    position = {"ra": 83.82, "dec": -5.39} if with_position else {}
    result = _solve_mock("boundary.fits", scale=0.45, reporter=reporter, **position)

    assert result.failure_reason == "field_not_built"
    assert "blind_known_scale" in reporter.plans[0]
    known = next(attempt for attempt in result.attempts if attempt.step == "blind_known_scale")
    assert known.outcome == "no_match"
    assert known.layers == ["q008"]
    assert known.ranges == ["0.4-10"]


def test_native_result_uses_astap_scale_for_nonconformal_cd():
    wcs = TanWCS(
        83.82,
        -5.39,
        np.array([[-1.0 / 3600.0, 0.0], [3.0 / 3600.0, 4.0 / 3600.0]]),
        120,
        60,
    )
    outcome = dataclasses.replace(_outcome("solved"), wcs=wcs)

    result = subject._solved(outcome, "blind", 1.0)

    assert result.pixel_scale_arcsec == 5.0
    assert result.fov_width_arcmin == 10.0
    assert result.fov_height_arcmin == 5.0
    assert wcs.scale_arcsec == pytest.approx(2.0)
