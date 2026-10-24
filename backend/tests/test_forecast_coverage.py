"""Declared forecast coverage is independent of provider response shape."""

import json
from datetime import UTC, datetime, timedelta

import pytest

from nightcrate.services.forecast_coverage import (
    DECLARED_COVERAGE,
    ModelMeta,
    coarse_cloud_from,
    expected_until,
    last_expected_stamp,
    parse_model_meta,
    requested_range,
)


def _meta(init_utc: datetime, *, update_hours: float = 1) -> ModelMeta:
    return ModelMeta(
        domain="ecmwf_ifs025",
        init_utc=init_utc,
        available_utc=init_utc + timedelta(hours=1),
        temporal_resolution=timedelta(hours=1),
        update_interval=timedelta(hours=update_hours),
    )


def test_requested_range_from_parameters():
    fetched_at = datetime(2026, 10, 17, 23, 30, 45, 123456, tzinfo=UTC)
    first, last = requested_range(fetched_at, forecast_days=16, past_days=1)
    assert first == datetime(2026, 10, 16, tzinfo=UTC)
    assert last == datetime(2026, 11, 1, 23, tzinfo=UTC)


def test_expected_until_caps_at_request_end(monkeypatch):
    # A declared reach beyond the request (the spec's 15-day starting value) is
    # capped by the request's own last stamp; the observed constants are shorter.
    monkeypatch.setitem(DECLARED_COVERAGE, "best_match", timedelta(days=15))
    fetched_at = datetime(2026, 10, 17, 23, 30, tzinfo=UTC)
    _, last = requested_range(fetched_at, forecast_days=16, past_days=1)
    assert expected_until("best_match", fetched_at, last) == last
    assert last_expected_stamp("best_match", fetched_at, last) == last


def test_last_expected_stamp_floors_declared_reach():
    fetched_at = datetime(2026, 10, 17, 23, 30, 45, tzinfo=UTC)
    _, last = requested_range(fetched_at, forecast_days=16, past_days=1)
    assert last_expected_stamp("icon_seamless", fetched_at, last) == datetime(
        2026, 10, 24, 13, tzinfo=UTC
    )


def test_requested_range_rejects_invalid_parameters():
    fetched_at = datetime(2026, 10, 17, tzinfo=UTC)
    with pytest.raises(ValueError):
        requested_range(fetched_at, forecast_days=0, past_days=1)
    with pytest.raises(ValueError):
        requested_range(fetched_at, forecast_days=16, past_days=-1)


def test_coverage_requires_aware_timestamps():
    with pytest.raises(ValueError, match="timezone-aware"):
        requested_range(datetime(2026, 10, 17), forecast_days=16, past_days=1)


def test_coarse_cloud_from():
    init = datetime(2026, 10, 17, 18, 37, tzinfo=UTC)
    fetched_at = datetime(2026, 10, 17, 19, 15, tzinfo=UTC)
    assert coarse_cloud_from(_meta(init), fetched_at) == datetime(2026, 10, 23, 12, tzinfo=UTC)
    assert coarse_cloud_from(None, fetched_at) == fetched_at + timedelta(hours=136)


def test_parse_model_meta():
    raw = json.dumps(
        {
            "ecmwf_ifs025": {
                "last_run_initialisation_time": 1_792_220_400,
                "last_run_availability_time": 1_792_224_000,
                "temporal_resolution_seconds": 3_600,
                "update_interval_seconds": 3_600,
            }
        }
    )
    parsed = parse_model_meta(raw)["ecmwf_ifs025"]
    assert parsed == ModelMeta(
        domain="ecmwf_ifs025",
        init_utc=datetime.fromtimestamp(1_792_220_400, UTC),
        available_utc=datetime.fromtimestamp(1_792_224_000, UTC),
        temporal_resolution=timedelta(hours=1),
        update_interval=timedelta(hours=1),
    )


@pytest.mark.parametrize(
    "body",
    [
        {},
        {
            "last_run_initialisation_time": "1792220400",
            "last_run_availability_time": 1_792_224_000,
            "temporal_resolution_seconds": 3_600,
            "update_interval_seconds": 3_600,
        },
    ],
)
def test_parse_model_meta_rejects_garbage(body):
    raw = json.dumps({"ecmwf_ifs025": body})
    assert parse_model_meta(raw) == {}
    assert parse_model_meta("not json") == {}


def test_parse_model_meta_rejects_non_dict_payload():
    assert "ecmwf_ifs025" in parse_model_meta(
        json.dumps(
            {
                "ecmwf_ifs025": {
                    "last_run_initialisation_time": 1_792_220_400,
                    "last_run_availability_time": 1_792_224_000,
                    "temporal_resolution_seconds": 3_600,
                    "update_interval_seconds": 3_600,
                }
            }
        )
    )
    assert parse_model_meta(json.dumps(["not", "a", "mapping"])) == {}


def test_parse_model_meta_drops_non_dict_domain_only():
    raw = json.dumps(
        {
            "ecmwf_ifs025": {
                "last_run_initialisation_time": 1_792_220_400,
                "last_run_availability_time": 1_792_224_000,
                "temporal_resolution_seconds": 3_600,
                "update_interval_seconds": 3_600,
            },
            "gfs_seamless": [],
        }
    )
    assert set(parse_model_meta(raw)) == {"ecmwf_ifs025"}


def test_parse_model_meta_drops_non_finite_domain_only():
    raw = json.dumps(
        {
            "ecmwf_ifs025": {
                "last_run_initialisation_time": 1_792_220_400,
                "last_run_availability_time": 1_792_224_000,
                "temporal_resolution_seconds": 3_600,
                "update_interval_seconds": 3_600,
            },
            "gfs_seamless": {
                "last_run_initialisation_time": 1_792_220_400,
                "last_run_availability_time": float("nan"),
                "temporal_resolution_seconds": 3_600,
                "update_interval_seconds": 3_600,
            },
        }
    )
    assert set(parse_model_meta(raw)) == {"ecmwf_ifs025"}


def test_parse_model_meta_drops_non_positive_interval_domain_only():
    raw = json.dumps(
        {
            "ecmwf_ifs025": {
                "last_run_initialisation_time": 1_792_220_400,
                "last_run_availability_time": 1_792_224_000,
                "temporal_resolution_seconds": 3_600,
                "update_interval_seconds": 3_600,
            },
            "gfs_seamless": {
                "last_run_initialisation_time": 1_792_220_400,
                "last_run_availability_time": 1_792_224_000,
                "temporal_resolution_seconds": 0,
                "update_interval_seconds": 3_600,
            },
        }
    )
    assert set(parse_model_meta(raw)) == {"ecmwf_ifs025"}
