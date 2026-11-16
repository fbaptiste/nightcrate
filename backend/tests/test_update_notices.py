from datetime import UTC, datetime, timedelta

import pytest

from nightcrate.core.updates_state import LatestApp, UpdatesState
from nightcrate.services.update_notices import (
    CatalogInstall,
    compute_notices,
    is_check_due,
    parse_notes,
)

NOW = datetime(2026, 11, 20, 21, tzinfo=UTC)


def _state(**changes):
    state = UpdatesState(
        latest_app=LatestApp(
            version="0.55.0",
            release_version="0.55.0",
            release_url="https://example.test",
            platforms=["darwin-aarch64"],
        )
    )
    return state.model_copy(update=changes)


def _notices(state, catalogs=CatalogInstall(), *, kind="source", platform=None):
    return compute_notices(
        state,
        catalogs,
        current_version="0.54.0",
        install_kind=kind,
        platform_key=platform,
        now=NOW,
    )


def test_age_boundary_and_later_boundary():
    assert (
        compute_notices(
            _state(app_later_until=NOW + timedelta(minutes=1)),
            CatalogInstall(mgc50_fetched_at=NOW - timedelta(days=182)),
            current_version="0.54.0",
            install_kind="source",
            platform_key=None,
            now=NOW,
        )
        == []
    )
    notices = compute_notices(
        _state(app_later_until=NOW),
        CatalogInstall(mgc50_fetched_at=NOW - timedelta(days=183)),
        current_version="0.54.0",
        install_kind="source",
        platform_key=None,
        now=NOW,
    )
    assert [item.id for item in notices] == ["app", "mgc50_age"]


def test_platform_skip_version_mismatch_and_source_rules():
    assert (
        compute_notices(
            _state(),
            CatalogInstall(),
            current_version="0.54.0",
            install_kind="installed",
            platform_key="linux-x86_64",
            now=NOW,
        )
        == []
    )


def test_later_skip_newer_version_and_release_mismatch():
    assert _notices(_state(app_later_until=NOW + timedelta(minutes=1))) == []
    assert [item.id for item in _notices(_state(app_later_until=NOW))] == ["app"]
    assert _notices(_state(skipped_app_version="0.55.0")) == []
    newer = LatestApp(
        version="0.56.0",
        release_version="0.56.0",
        release_url="https://example.test",
        platforms=["darwin-aarch64"],
    )
    assert [item.id for item in _notices(_state(latest_app=newer))] == ["app"]
    mismatch = newer.model_copy(update={"release_version": "0.55.0"})
    notice = _notices(_state(latest_app=mismatch), kind="installed", platform="darwin-aarch64")[0]
    assert notice.installable is False


@pytest.mark.parametrize("version", ["0.55", "v0.55.0-rc1"])
def test_invalid_latest_versions_do_not_create_notice(version):
    latest = LatestApp(
        version=version,
        release_version=version,
        release_url="https://example.test",
        platforms=[],
    )
    assert _notices(_state(latest_app=latest)) == []


def test_openngc_skip_only_hides_that_release():
    catalogs = CatalogInstall(openngc_tag="2023-12-03")
    skipped = _state(
        latest_openngc_tag="2026-11-02",
        skipped_openngc_release="2026-11-02",
        app_later_until=NOW + timedelta(days=1),
    )
    assert _notices(skipped, catalogs) == []
    newer = skipped.model_copy(update={"latest_openngc_tag": "2026-12-01"})
    assert [item.id for item in _notices(newer, catalogs)] == ["openngc"]
    source = compute_notices(
        _state(),
        CatalogInstall(),
        current_version="0.54.0",
        install_kind="source",
        platform_key=None,
        now=NOW,
    )
    assert source[0].installable is False
    assert (
        compute_notices(
            _state(skipped_app_version="0.55.0"),
            CatalogInstall(),
            current_version="0.54.0",
            install_kind="source",
            platform_key=None,
            now=NOW,
        )
        == []
    )


def test_due_and_notes():
    assert not is_check_due(UpdatesState(), NOW)
    assert not is_check_due(UpdatesState(check_automatically=False), NOW)
    assert not is_check_due(
        UpdatesState(check_automatically=True, last_attempt_at=NOW - timedelta(hours=23)), NOW
    )
    assert is_check_due(
        UpdatesState(check_automatically=True, last_attempt_at=NOW - timedelta(hours=24)), NOW
    )
    assert parse_notes("\n".join(f"- **item {i}**" for i in range(6))) == [
        f"item {i}" for i in range(4)
    ]
