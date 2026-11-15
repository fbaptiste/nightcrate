import json
from datetime import UTC, datetime

from nightcrate.core import app_config
from nightcrate.core.updates_state import UpdatesState, load_updates_state, save_updates_state


def test_missing_and_truncated_files_are_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path)
    assert load_updates_state() == UpdatesState()
    assert not (tmp_path / "updates.json").exists()
    (tmp_path / "updates.json").write_text('{"check_auto', encoding="utf-8")
    assert load_updates_state() == UpdatesState()


def test_round_trip_and_one_bad_field_falls_back(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path)
    state = UpdatesState(
        check_automatically=True, last_attempt_at=datetime(2026, 11, 20, tzinfo=UTC)
    )
    save_updates_state(state)
    assert load_updates_state() == state
    data = json.loads((tmp_path / "updates.json").read_text())
    data["app_later_until"] = "soon"
    (tmp_path / "updates.json").write_text(json.dumps(data), encoding="utf-8")
    loaded = load_updates_state()
    assert loaded.check_automatically is True
    assert loaded.app_later_until is None
