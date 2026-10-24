"""Weather cache administration, retention, and schema checks."""

import asyncio
import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import aiosqlite
import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from yoyo import get_backend, read_migrations

from nightcrate.api.weather import (
    _cloud_cache_rows,
    _cloud_complete,
    _fetch_or_cached,
    _fetch_or_cached_cloud_models,
    _fetch_or_cached_supplementary,
    _paired_meta_raw,
    _weather_from_raw,
    _write_cache,
    _write_cloud_cache,
)
from nightcrate.db.migrations import MIGRATIONS_DIR, apply_migrations
from nightcrate.db.session import get_db_path
from nightcrate.main import app, purge_weather_cache
from nightcrate.services.forecast_coverage import last_expected_stamp, requested_range
from nightcrate.services.weather import (
    CLOUD_SPREAD_MODELS,
    FORECAST_DAYS,
    CloudModelData,
    HourlyWeather,
    WeatherData,
    parse_cloud_models,
)


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as value:
        yield value


async def _location(client: AsyncClient) -> int:
    response = await client.post(
        "/api/locations",
        json={
            "name": "Cache Test",
            "latitude": 34.05,
            "longitude": -118.25,
            "elevation_m": 300,
            "timezone": "America/Los_Angeles",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


async def _row(location_id: int, source: str, age: str = "0 hours") -> None:
    async with aiosqlite.connect(get_db_path()) as conn:
        await conn.execute(
            """INSERT INTO weather_cache
               (location_id, source, start_date, end_date, response_json, fetched_at)
               VALUES (?, ?, '', '', ?, datetime('now', ?))""",
            (location_id, source, json.dumps({"hourly": {"time": []}}), age),
        )
        await conn.commit()


def _cloud_json(
    fetched_at: datetime,
    *,
    cutoffs: dict[str, datetime] | None = None,
    legacy: bool = False,
    empty_axis: bool = False,
) -> str:
    first, last = requested_range(fetched_at, forecast_days=FORECAST_DAYS, past_days=1)
    times: list[datetime] = []
    current = first
    while current <= last:
        times.append(current)
        current += timedelta(hours=1)
    if empty_axis:
        times = []
    hourly: dict[str, list[int | float | None]] = {
        "time": [int(stamp.timestamp()) for stamp in times]
    }
    variables = ["cloud_cover", "cloud_cover_low", "cloud_cover_mid", "cloud_cover_high"]
    if not legacy:
        variables.append("precipitation")
    for model in CLOUD_SPREAD_MODELS:
        cutoff = (cutoffs or {}).get(model)
        for variable in variables:
            hourly[f"{variable}_{model}"] = [
                0.0 if cutoff is None or stamp <= cutoff else None for stamp in times
            ]
    return json.dumps({"utc_offset_seconds": 0, "hourly": hourly})


def _weather_json(fetched_at: datetime, *, cutoff: datetime | None = None) -> str:
    first, last = requested_range(fetched_at, forecast_days=FORECAST_DAYS, past_days=1)
    times: list[datetime] = []
    current = first
    while current <= last:
        times.append(current)
        current += timedelta(hours=1)

    def values(value: float) -> list[float | None]:
        return [value if cutoff is None or stamp <= cutoff else None for stamp in times]

    return json.dumps(
        {
            "latitude": 34.05,
            "longitude": -118.25,
            "utc_offset_seconds": 0,
            "hourly": {
                "time": [int(stamp.timestamp()) for stamp in times],
                "temperature_2m": values(12.0),
                "dew_point_2m": values(4.0),
                "relative_humidity_2m": values(40.0),
                "cloud_cover": values(0.0),
                "cloud_cover_low": values(0.0),
                "cloud_cover_mid": values(0.0),
                "cloud_cover_high": values(0.0),
                "wind_speed_10m": values(5.0),
                "wind_direction_10m": values(180.0),
                "wind_gusts_10m": values(10.0),
                "visibility": values(25000.0),
                "precipitation": values(0.0),
                "precipitation_probability": values(0.0),
            },
        }
    )


def _cloud_data(raw_json: str) -> CloudModelData:
    raw = json.loads(raw_json)
    return CloudModelData(
        models=parse_cloud_models(raw["hourly"], CLOUD_SPREAD_MODELS), raw_json=raw_json
    )


def _meta_raw(marker: str = "one") -> str:
    return json.dumps({"ecmwf_ifs025": {"marker": marker}})


async def test_cache_stats_and_clear(client: AsyncClient):
    location_id = await _location(client)
    await _row(location_id, "forecast")
    await _row(location_id, "ecmwf_pwv")
    stats = await client.get("/api/weather/cache/stats")
    assert stats.status_code == 200
    assert stats.json()["rows"] == 2
    assert stats.json()["bytes"] > 0

    cleared = await client.delete("/api/weather/cache")
    assert cleared.json() == {"ok": True, "deleted": 2}
    assert (await client.get("/api/weather/cache/stats")).json()["rows"] == 0


async def test_purge_keeps_week_old_rows(client: AsyncClient):
    location_id = await _location(client)
    await _row(location_id, "forecast", "-2 days")
    await _row(location_id, "cloud_models", "-9 days")
    now = datetime.now(UTC)
    payload = json.dumps({"hourly": {"time": []}})
    await _write_cache(
        location_id,
        "ecmwf_pwv",
        payload,
        now - timedelta(days=7, hours=23),
    )
    await _write_cache(
        location_id,
        "openmeteo_aq",
        payload,
        now - timedelta(days=8, hours=1),
    )
    async with aiosqlite.connect(get_db_path()) as conn:
        deleted = await purge_weather_cache(conn)
        assert deleted == 2
        cursor = await conn.execute("SELECT source FROM weather_cache ORDER BY source")
        assert [row[0] for row in await cursor.fetchall()] == ["ecmwf_pwv", "forecast"]


async def test_cloud_models_source_check_constraint(client: AsyncClient):
    """Migration 0057 accepts the cloud_models cache source."""
    location_id = await _location(client)
    await _row(location_id, "cloud_models")
    async with aiosqlite.connect(get_db_path()) as conn:
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM weather_cache WHERE source = 'cloud_models'"
        )
        assert (await cursor.fetchone())[0] == 1


def test_migration_0060_adds_model_meta_fresh(tmp_path):
    path = tmp_path / "fresh.db"
    apply_migrations(path)
    with closing(sqlite3.connect(path)) as conn:
        location_id = conn.execute(
            "INSERT INTO location (name, latitude, longitude, timezone) VALUES (?, ?, ?, ?)",
            ("Fresh Migration Site", 33.4484, -112.0740, "America/Phoenix"),
        ).lastrowid
        conn.execute(
            """INSERT INTO weather_cache
               (location_id, source, start_date, end_date, response_json)
               VALUES (?, 'model_meta', '', '', '{}')""",
            (location_id,),
        )
        conn.commit()
        assert conn.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_migration_0060_preserves_prior_rows_and_ids(tmp_path):
    path = tmp_path / "upgrade.db"
    with get_backend(f"sqlite:///{path}") as backend:
        migrations = read_migrations(str(MIGRATIONS_DIR))
        through_0059 = backend.to_apply(migrations).filter(
            lambda migration: migration.id <= "0059.imaging_rules_precipitation"
        )
        with backend.lock():
            backend.apply_migrations(through_0059)

    with closing(sqlite3.connect(path)) as conn:
        location_id = conn.execute(
            "INSERT INTO location (name, latitude, longitude, timezone) VALUES (?, ?, ?, ?)",
            ("Upgrade Migration Site", 33.4484, -112.0740, "America/Phoenix"),
        ).lastrowid
        conn.execute(
            """INSERT INTO weather_cache
               (id, location_id, source, start_date, end_date, response_json)
               VALUES (42, ?, 'forecast', '', '', '{}')""",
            (location_id,),
        )
        conn.commit()

    apply_migrations(path)
    with closing(sqlite3.connect(path)) as conn:
        assert conn.execute(
            "SELECT id, response_json FROM weather_cache WHERE source = 'forecast'"
        ).fetchone() == (42, "{}")
        conn.execute(
            """INSERT INTO weather_cache
               (location_id, source, start_date, end_date, response_json)
               VALUES (?, 'model_meta', '', '', '{}')""",
            (location_id,),
        )
        conn.commit()
        assert conn.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


async def test_model_meta_written_with_cloud_row(client: AsyncClient):
    location_id = await _location(client)
    fetched_at = datetime(2026, 10, 17, 23, 30, 45, 123456, tzinfo=UTC)
    cloud_raw = _cloud_json(fetched_at)
    await _write_cloud_cache(location_id, cloud_raw, _meta_raw(), fetched_at)

    rows = await _cloud_cache_rows(location_id)
    assert rows["cloud_models"]["fetched_at"] == rows["model_meta"]["fetched_at"]
    assert rows["cloud_models"]["fetched_at"].endswith(".123456")
    stored = json.loads(rows["model_meta"]["response_json"])
    assert stored["cloud_sha256"] == hashlib.sha256(cloud_raw.encode()).hexdigest()
    assert stored["domains"] == json.loads(_meta_raw())

    refresh_at = fetched_at + timedelta(hours=7)
    replacement = _cloud_data(_cloud_json(refresh_at))
    with (
        patch("nightcrate.api.weather._now", return_value=refresh_at),
        patch("nightcrate.api.weather.fetch_cloud_models", new=AsyncMock(return_value=replacement)),
        patch(
            "nightcrate.api.weather.fetch_model_meta",
            new=AsyncMock(side_effect=RuntimeError("metadata unavailable")),
        ),
    ):
        result = await _fetch_or_cached_cloud_models(
            location_id, 34.05, -118.25, "America/Los_Angeles", ttl_hours=6
        )
    assert result.data is replacement
    assert result.meta_raw is None
    assert "model_meta" not in await _cloud_cache_rows(location_id)


async def test_meta_from_other_snapshot_not_attached(client: AsyncClient):
    location_id = await _location(client)
    fetched_at = datetime(2026, 10, 17, 23, 30, tzinfo=UTC)
    await _write_cloud_cache(location_id, _cloud_json(fetched_at), _meta_raw(), fetched_at)
    async with aiosqlite.connect(get_db_path()) as conn:
        payload = json.loads(
            (
                await (
                    await conn.execute(
                        "SELECT response_json FROM weather_cache WHERE source = 'model_meta'"
                    )
                ).fetchone()
            )[0]
        )
        payload["cloud_sha256"] = hashlib.sha256(b"another payload").hexdigest()
        await conn.execute(
            "UPDATE weather_cache SET response_json = ? WHERE source = 'model_meta'",
            (json.dumps(payload),),
        )
        await conn.commit()
    rows = await _cloud_cache_rows(location_id)
    assert _paired_meta_raw(rows["cloud_models"], rows["model_meta"]) is None


async def test_identical_payloads_pair_by_refresh(client: AsyncClient):
    location_id = await _location(client)
    fetched_at = datetime(2026, 10, 17, 23, 30, tzinfo=UTC)
    cloud_raw = _cloud_json(fetched_at)
    await _write_cloud_cache(location_id, cloud_raw, _meta_raw("first"), fetched_at)
    first = await _cloud_cache_rows(location_id)
    assert (
        json.loads(_paired_meta_raw(first["cloud_models"], first["model_meta"]))["ecmwf_ifs025"][
            "marker"
        ]
        == "first"
    )

    await _write_cloud_cache(
        location_id, cloud_raw, _meta_raw("second"), fetched_at + timedelta(microseconds=1)
    )
    second = await _cloud_cache_rows(location_id)
    assert (
        json.loads(_paired_meta_raw(second["cloud_models"], second["model_meta"]))["ecmwf_ifs025"][
            "marker"
        ]
        == "second"
    )


def test_truncated_axis_does_not_shrink_coverage():
    fetched_at = datetime(2026, 10, 17, 23, 30, tzinfo=UTC)
    cutoff = fetched_at + timedelta(days=9)
    truncated = _cloud_data(
        _cloud_json(fetched_at, cutoffs={model: cutoff for model in CLOUD_SPREAD_MODELS})
    )
    empty = _cloud_data(_cloud_json(fetched_at, empty_axis=True))
    assert not _cloud_complete(truncated, fetched_at)
    assert not _cloud_complete(empty, fetched_at)


def test_union_axis_does_not_hide_truncation():
    fetched_at = datetime(2026, 10, 17, 23, 30, tzinfo=UTC)
    _, last = requested_range(fetched_at, forecast_days=FORECAST_DAYS, past_days=1)
    cutoffs = {
        "ecmwf_ifs025": fetched_at + timedelta(days=10),
        "gfs_seamless": last_expected_stamp("gfs_seamless", fetched_at, last),
    }
    assert not _cloud_complete(_cloud_data(_cloud_json(fetched_at, cutoffs=cutoffs)), fetched_at)


async def test_incomplete_within_ttl_not_stale(client: AsyncClient):
    location_id = await _location(client)
    now = datetime(2026, 10, 17, 23, 30, tzinfo=UTC)
    fetched_at = now - timedelta(minutes=30)
    await _write_cache(
        location_id,
        "forecast",
        _weather_json(fetched_at, cutoff=fetched_at + timedelta(days=5)),
        fetched_at,
    )
    cloud_raw = _cloud_json(fetched_at, cutoffs={"icon_seamless": fetched_at + timedelta(days=5)})
    await _write_cloud_cache(location_id, cloud_raw, _meta_raw(), fetched_at)

    with (
        patch("nightcrate.api.weather._now", return_value=now),
        patch(
            "nightcrate.api.weather.fetch_weather",
            new=AsyncMock(side_effect=RuntimeError("offline")),
        ),
        patch(
            "nightcrate.api.weather.fetch_cloud_models",
            new=AsyncMock(side_effect=RuntimeError("offline")),
        ),
        patch(
            "nightcrate.api.weather.fetch_model_meta",
            new=AsyncMock(side_effect=RuntimeError("offline")),
        ),
    ):
        forecast_result = await _fetch_or_cached(
            location_id, 34.05, -118.25, "America/Los_Angeles", ttl_hours=6
        )
        cloud_result = await _fetch_or_cached_cloud_models(
            location_id, 34.05, -118.25, "America/Los_Angeles", ttl_hours=6
        )

    assert forecast_result.stale_minutes is None
    assert cloud_result.stale_minutes is None
    assert cloud_result.data is not None


async def test_missing_meta_within_ttl_not_stale(client: AsyncClient):
    location_id = await _location(client)
    now = datetime(2026, 10, 17, 23, 30, tzinfo=UTC)
    fetched_at = now - timedelta(minutes=30)
    await _write_cloud_cache(location_id, _cloud_json(fetched_at), None, fetched_at)

    with (
        patch("nightcrate.api.weather._now", return_value=now),
        patch(
            "nightcrate.api.weather.fetch_cloud_models",
            new=AsyncMock(side_effect=RuntimeError("offline")),
        ),
        patch(
            "nightcrate.api.weather.fetch_model_meta",
            new=AsyncMock(side_effect=RuntimeError("offline")),
        ),
    ):
        result = await _fetch_or_cached_cloud_models(
            location_id, 34.05, -118.25, "America/Los_Angeles", ttl_hours=6
        )

    assert result.data is not None
    assert result.meta_raw is None
    assert result.stale_minutes is None


async def test_past_ttl_refresh_failure_is_stale(client: AsyncClient):
    location_id = await _location(client)
    now = datetime(2026, 10, 17, 23, 30, tzinfo=UTC)
    fetched_at = now - timedelta(hours=7)
    await _write_cache(location_id, "forecast", _weather_json(fetched_at), fetched_at)
    await _write_cloud_cache(location_id, _cloud_json(fetched_at), _meta_raw(), fetched_at)

    with (
        patch("nightcrate.api.weather._now", return_value=now),
        patch(
            "nightcrate.api.weather.fetch_weather",
            new=AsyncMock(side_effect=RuntimeError("offline")),
        ),
        patch(
            "nightcrate.api.weather.fetch_cloud_models",
            new=AsyncMock(side_effect=RuntimeError("offline")),
        ),
        patch(
            "nightcrate.api.weather.fetch_model_meta",
            new=AsyncMock(side_effect=RuntimeError("offline")),
        ),
    ):
        forecast_result = await _fetch_or_cached(
            location_id, 34.05, -118.25, "America/Los_Angeles", ttl_hours=6
        )
        cloud_result = await _fetch_or_cached_cloud_models(
            location_id, 34.05, -118.25, "America/Los_Angeles", ttl_hours=6
        )

    assert forecast_result.stale_minutes == 420
    assert cloud_result.stale_minutes == 420


async def test_failed_refresh_cooldown_sequential_polls(client: AsyncClient):
    location_id = await _location(client)
    now = datetime(2026, 10, 17, 23, 30, tzinfo=UTC)
    fetched_at = now - timedelta(hours=7)
    await _write_cache(location_id, "forecast", _weather_json(fetched_at), fetched_at)
    weather_fetch = AsyncMock(side_effect=RuntimeError("offline"))

    with patch("nightcrate.api.weather.fetch_weather", new=weather_fetch):
        for minute in range(10):
            with patch("nightcrate.api.weather._now", return_value=now + timedelta(minutes=minute)):
                result = await _fetch_or_cached(
                    location_id, 34.05, -118.25, "America/Los_Angeles", ttl_hours=6
                )
                assert result.stale_minutes == 420 + minute
        weather_fetch.assert_awaited_once()

        with patch("nightcrate.api.weather._now", return_value=now + timedelta(minutes=10)):
            result = await _fetch_or_cached(
                location_id, 34.05, -118.25, "America/Los_Angeles", ttl_hours=6
            )

    assert result.stale_minutes == 430
    assert weather_fetch.await_count == 2


async def test_concurrent_failed_refreshes_share_attempt(client: AsyncClient):
    location_id = await _location(client)
    now = datetime(2026, 10, 17, 23, 30, tzinfo=UTC)
    fetched_at = now - timedelta(hours=7)
    await _write_cache(location_id, "forecast", _weather_json(fetched_at), fetched_at)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def slow_failure(*_args, **_kwargs):
        entered.set()
        await release.wait()
        raise RuntimeError("offline")

    weather_fetch = AsyncMock(side_effect=slow_failure)
    with (
        patch("nightcrate.api.weather._now", return_value=now),
        patch("nightcrate.api.weather.fetch_weather", new=weather_fetch),
    ):
        first = asyncio.create_task(
            _fetch_or_cached(location_id, 34.05, -118.25, "America/Los_Angeles", ttl_hours=6)
        )
        await entered.wait()
        second = asyncio.create_task(
            _fetch_or_cached(location_id, 34.05, -118.25, "America/Los_Angeles", ttl_hours=6)
        )
        await asyncio.sleep(0)
        release.set()
        results = await asyncio.gather(first, second)

    weather_fetch.assert_awaited_once()
    assert [result.stale_minutes for result in results] == [420, 420]


async def test_supplementary_failure_cooldown(client: AsyncClient):
    location_id = await _location(client)
    now = datetime(2026, 10, 17, 23, 30, tzinfo=UTC)
    supplementary_fetch = AsyncMock(side_effect=RuntimeError("offline"))

    for minute in (0, 1, 9):
        with patch("nightcrate.api.weather._now", return_value=now + timedelta(minutes=minute)):
            result = await _fetch_or_cached_supplementary(
                location_id,
                34.05,
                -118.25,
                "America/Los_Angeles",
                "ecmwf_pwv",
                supplementary_fetch,
                ttl_hours=6,
            )
            assert result == {}
    supplementary_fetch.assert_awaited_once()

    with patch("nightcrate.api.weather._now", return_value=now + timedelta(minutes=10)):
        await _fetch_or_cached_supplementary(
            location_id,
            34.05,
            -118.25,
            "America/Los_Angeles",
            "ecmwf_pwv",
            supplementary_fetch,
            ttl_hours=6,
        )
    assert supplementary_fetch.await_count == 2


async def test_no_cache_failure_cooldown_still_503(client: AsyncClient):
    location_id = await _location(client)
    now = datetime(2026, 10, 17, 23, 30, tzinfo=UTC)
    weather_fetch = AsyncMock(side_effect=RuntimeError("offline"))

    with patch("nightcrate.api.weather.fetch_weather", new=weather_fetch):
        for minute in (0, 1, 9):
            with patch("nightcrate.api.weather._now", return_value=now + timedelta(minutes=minute)):
                with pytest.raises(HTTPException) as raised:
                    await _fetch_or_cached(
                        location_id, 34.05, -118.25, "America/Los_Angeles", ttl_hours=6
                    )
                assert raised.value.status_code == 503

    weather_fetch.assert_awaited_once()


async def test_legacy_cloud_row_refetched_within_ttl(client: AsyncClient):
    location_id = await _location(client)
    now = datetime(2026, 10, 17, 23, 30, tzinfo=UTC)
    await _write_cloud_cache(
        location_id,
        _cloud_json(now - timedelta(minutes=30), legacy=True),
        _meta_raw(),
        now - timedelta(minutes=30),
    )
    replacement = _cloud_data(_cloud_json(now))
    cloud_fetch = AsyncMock(return_value=replacement)
    with (
        patch("nightcrate.api.weather._now", return_value=now),
        patch("nightcrate.api.weather.fetch_cloud_models", new=cloud_fetch),
        patch("nightcrate.api.weather.fetch_model_meta", new=AsyncMock(return_value=_meta_raw())),
    ):
        result = await _fetch_or_cached_cloud_models(
            location_id, 34.05, -118.25, "America/Los_Angeles", ttl_hours=6
        )
    cloud_fetch.assert_awaited_once()
    assert result.data is replacement


async def test_old_nbm_keys_do_not_obsolete_cloud_cache(client: AsyncClient):
    location_id = await _location(client)
    now = datetime(2026, 10, 17, 23, 30, tzinfo=UTC)
    payload = json.loads(_cloud_json(now - timedelta(minutes=30)))
    times = payload["hourly"]["time"]
    payload["hourly"]["cloud_cover_ncep_nbm_conus"] = [0.0] * len(times)
    payload["hourly"]["precipitation_probability_ncep_nbm_conus"] = [10.0] * len(times)
    await _write_cloud_cache(
        location_id,
        json.dumps(payload),
        _meta_raw(),
        now - timedelta(minutes=30),
    )
    cloud_fetch = AsyncMock(side_effect=AssertionError("current cache must not refetch"))
    with (
        patch("nightcrate.api.weather._now", return_value=now),
        patch("nightcrate.api.weather.fetch_cloud_models", new=cloud_fetch),
    ):
        result = await _fetch_or_cached_cloud_models(
            location_id, 34.05, -118.25, "America/Los_Angeles", ttl_hours=6
        )

    cloud_fetch.assert_not_awaited()
    assert result.data is not None
    assert "ncep_nbm_conus" not in result.data.models


async def test_truncated_model_refetched_once(client: AsyncClient):
    location_id = await _location(client)
    now = datetime(2026, 10, 17, 23, 30, tzinfo=UTC)
    _, last = requested_range(now, forecast_days=FORECAST_DAYS, past_days=1)
    icon_expected = last_expected_stamp("icon_seamless", now, last)
    truncated_raw = _cloud_json(now, cutoffs={"icon_seamless": icon_expected - timedelta(hours=20)})
    await _write_cloud_cache(location_id, truncated_raw, _meta_raw(), now)
    truncated = _cloud_data(truncated_raw)
    cloud_fetch = AsyncMock(return_value=truncated)
    with (
        patch("nightcrate.api.weather._now", return_value=now + timedelta(minutes=10)),
        patch("nightcrate.api.weather.fetch_cloud_models", new=cloud_fetch),
        patch("nightcrate.api.weather.fetch_model_meta", new=AsyncMock(return_value=_meta_raw())),
    ):
        await _fetch_or_cached_cloud_models(
            location_id, 34.05, -118.25, "America/Los_Angeles", ttl_hours=6
        )
        await _fetch_or_cached_cloud_models(
            location_id, 34.05, -118.25, "America/Los_Angeles", ttl_hours=6
        )
    cloud_fetch.assert_awaited_once()


async def test_repair_refetch_at_most_hourly(client: AsyncClient):
    location_id = await _location(client)
    fetched_at = datetime(2026, 10, 17, 23, 30, tzinfo=UTC)
    truncated_raw = _cloud_json(
        fetched_at,
        cutoffs={"icon_seamless": fetched_at + timedelta(days=5)},
    )
    await _write_cloud_cache(location_id, truncated_raw, _meta_raw(), fetched_at)
    truncated = _cloud_data(truncated_raw)
    cloud_fetch = AsyncMock(return_value=truncated)
    meta_fetch = AsyncMock(return_value=_meta_raw())
    with (
        patch("nightcrate.api.weather.fetch_cloud_models", new=cloud_fetch),
        patch("nightcrate.api.weather.fetch_model_meta", new=meta_fetch),
    ):
        with patch("nightcrate.api.weather._now", return_value=fetched_at + timedelta(minutes=10)):
            await _fetch_or_cached_cloud_models(
                location_id, 34.05, -118.25, "America/Los_Angeles", ttl_hours=6
            )
        with patch("nightcrate.api.weather._now", return_value=fetched_at + timedelta(minutes=69)):
            await _fetch_or_cached_cloud_models(
                location_id, 34.05, -118.25, "America/Los_Angeles", ttl_hours=6
            )
        cloud_fetch.assert_awaited_once()
        with patch("nightcrate.api.weather._now", return_value=fetched_at + timedelta(minutes=70)):
            await _fetch_or_cached_cloud_models(
                location_id, 34.05, -118.25, "America/Los_Angeles", ttl_hours=6
            )
    assert cloud_fetch.await_count == 2


async def test_concurrent_repairs_coalesce(client: AsyncClient):
    location_id = await _location(client)
    now = datetime(2026, 10, 17, 23, 30, tzinfo=UTC)
    truncated_raw = _cloud_json(now, cutoffs={"ecmwf_ifs025": now + timedelta(days=10)})
    await _write_cloud_cache(location_id, truncated_raw, _meta_raw(), now)
    complete = _cloud_data(_cloud_json(now))
    entered = asyncio.Event()
    release = asyncio.Event()

    async def slow_fetch(*_args, **_kwargs):
        entered.set()
        await release.wait()
        return complete

    cloud_fetch = AsyncMock(side_effect=slow_fetch)
    with (
        patch("nightcrate.api.weather._now", return_value=now + timedelta(minutes=10)),
        patch("nightcrate.api.weather.fetch_cloud_models", new=cloud_fetch),
        patch("nightcrate.api.weather.fetch_model_meta", new=AsyncMock(return_value=_meta_raw())),
    ):
        first = asyncio.create_task(
            _fetch_or_cached_cloud_models(
                location_id, 34.05, -118.25, "America/Los_Angeles", ttl_hours=6
            )
        )
        await entered.wait()
        second = asyncio.create_task(
            _fetch_or_cached_cloud_models(
                location_id, 34.05, -118.25, "America/Los_Angeles", ttl_hours=6
            )
        )
        await asyncio.sleep(0)
        release.set()
        results = await asyncio.gather(first, second)
    cloud_fetch.assert_awaited_once()
    assert all(result.data is not None for result in results)


async def test_concurrent_expired_refreshes_coalesce(client: AsyncClient):
    location_id = await _location(client)
    now = datetime(2026, 10, 17, 23, 30, tzinfo=UTC)
    fetched_at = now - timedelta(hours=7)
    await _write_cache(location_id, "forecast", _weather_json(fetched_at), fetched_at)
    replacement_weather = _weather_from_raw(_weather_json(now), "forecast")
    weather_entered = asyncio.Event()
    weather_release = asyncio.Event()

    async def slow_weather(*_args, **_kwargs):
        weather_entered.set()
        await weather_release.wait()
        return replacement_weather

    weather_fetch = AsyncMock(side_effect=slow_weather)
    with (
        patch("nightcrate.api.weather._now", return_value=now),
        patch("nightcrate.api.weather.fetch_weather", new=weather_fetch),
    ):
        first_weather = asyncio.create_task(
            _fetch_or_cached(location_id, 34.05, -118.25, "America/Los_Angeles", ttl_hours=6)
        )
        await weather_entered.wait()
        second_weather = asyncio.create_task(
            _fetch_or_cached(location_id, 34.05, -118.25, "America/Los_Angeles", ttl_hours=6)
        )
        await asyncio.sleep(0)
        weather_release.set()
        await asyncio.gather(first_weather, second_weather)
    weather_fetch.assert_awaited_once()

    await _write_cloud_cache(location_id, _cloud_json(fetched_at), _meta_raw(), fetched_at)
    replacement_cloud = _cloud_data(_cloud_json(now))
    cloud_entered = asyncio.Event()
    cloud_release = asyncio.Event()

    async def slow_cloud(*_args, **_kwargs):
        cloud_entered.set()
        await cloud_release.wait()
        return replacement_cloud

    cloud_fetch = AsyncMock(side_effect=slow_cloud)
    with (
        patch("nightcrate.api.weather._now", return_value=now),
        patch("nightcrate.api.weather.fetch_cloud_models", new=cloud_fetch),
        patch("nightcrate.api.weather.fetch_model_meta", new=AsyncMock(return_value=_meta_raw())),
    ):
        first_cloud = asyncio.create_task(
            _fetch_or_cached_cloud_models(
                location_id, 34.05, -118.25, "America/Los_Angeles", ttl_hours=6
            )
        )
        await cloud_entered.wait()
        second_cloud = asyncio.create_task(
            _fetch_or_cached_cloud_models(
                location_id, 34.05, -118.25, "America/Los_Angeles", ttl_hours=6
            )
        )
        await asyncio.sleep(0)
        cloud_release.set()
        await asyncio.gather(first_cloud, second_cloud)
    cloud_fetch.assert_awaited_once()


async def test_legacy_cache_off_grid_is_ignored(client: AsyncClient):
    location_id = await _location(client)
    payload = {
        "latitude": 34.05,
        "longitude": -118.25,
        "utc_offset_seconds": 19800,
        "hourly": {"time": ["2026-10-17T20:00"]},
    }
    async with aiosqlite.connect(get_db_path()) as conn:
        await conn.execute(
            """INSERT INTO weather_cache
               (location_id, source, start_date, end_date, response_json, fetched_at)
               VALUES (?, 'forecast', '', '', ?, datetime('now'))""",
            (location_id, json.dumps(payload)),
        )
        await conn.commit()
    fetched = WeatherData(
        latitude=34.05,
        longitude=-118.25,
        source="forecast",
        hourly=[
            HourlyWeather(
                time_utc=datetime(2026, 10, 17, 20, tzinfo=UTC),
                temperature_c=None,
                dew_point_c=None,
                humidity_pct=None,
                cloud_cover_pct=None,
                cloud_cover_low_pct=None,
                cloud_cover_mid_pct=None,
                cloud_cover_high_pct=None,
                wind_speed_kmh=None,
                wind_direction_deg=None,
                wind_gusts_kmh=None,
                visibility_m=None,
                precipitation_mm=None,
                precipitation_probability_pct=None,
            )
        ],
        raw_json=json.dumps({"latitude": 34.05, "longitude": -118.25, "hourly": {"time": []}}),
    )
    with patch(
        "nightcrate.api.weather.fetch_weather", new=AsyncMock(return_value=fetched)
    ) as fetch:
        from nightcrate.api.weather import _fetch_or_cached

        result = await _fetch_or_cached(location_id, 34.05, -118.25, "Asia/Kolkata", ttl_hours=6)
    fetch.assert_awaited_once()
    assert result.data is fetched


async def test_forecast_unavailable_without_cache_is_503(client: AsyncClient):
    location_id = await _location(client)
    with patch(
        "nightcrate.api.weather.fetch_weather",
        new=AsyncMock(side_effect=RuntimeError("offline")),
    ):
        from nightcrate.api.weather import _fetch_or_cached

        with pytest.raises(HTTPException) as raised:
            await _fetch_or_cached(location_id, 34.05, -118.25, "America/Los_Angeles", ttl_hours=6)
    assert raised.value.status_code == 503
    assert raised.value.detail == (
        "Forecast unavailable — Open-Meteo could not be reached and nothing is cached"
    )
