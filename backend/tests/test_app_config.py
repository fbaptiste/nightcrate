"""Tests for nightcrate.core.app_config."""

import pytest

from nightcrate.core.app_config import (
    AppConfig,
    DatabaseEntry,
    get_active_db_path,
    get_default_db_path,
    load_config,
    save_config,
)


@pytest.fixture(autouse=True)
def _patch_config_paths(tmp_path, monkeypatch):
    monkeypatch.setattr("nightcrate.core.app_config.APP_DIR", tmp_path)
    monkeypatch.setattr("nightcrate.core.app_config.CONFIG_PATH", tmp_path / "config.json")


def test_load_missing_config(tmp_path):
    config = load_config()
    assert config.databases == {}
    assert config.active_db is None


def test_save_and_load_roundtrip(tmp_path):
    db1 = str(tmp_path / "main.db")
    db2 = str(tmp_path / "test.db")
    config = AppConfig(
        databases={
            db1: DatabaseEntry(name="Fred's Imaging Rig"),
            db2: DatabaseEntry(name="Test Database"),
        },
        active_db=db1,
    )
    save_config(config)

    loaded = load_config()
    assert loaded.active_db == db1
    assert db1 in loaded.databases
    assert loaded.databases[db1].name == "Fred's Imaging Rig"
    assert db2 in loaded.databases
    assert loaded.databases[db2].name == "Test Database"


def test_db_configured_true(tmp_path):
    db_file = tmp_path / "test.db"
    db_file.write_text("")
    config = AppConfig(
        databases={str(db_file): DatabaseEntry(name="Test")},
        active_db=str(db_file),
    )
    assert config.db_configured is True


def test_db_configured_false_no_active():
    config = AppConfig(databases={}, active_db=None)
    assert config.db_configured is False


def test_db_configured_false_missing_file(tmp_path):
    db_path = str(tmp_path / "nonexistent.db")
    config = AppConfig(
        databases={db_path: DatabaseEntry(name="Missing")},
        active_db=db_path,
    )
    assert config.db_configured is False


def test_load_corrupt_json(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text("not valid json {{{", encoding="utf-8")
    config = load_config()
    assert config.databases == {}
    assert config.active_db is None


def test_get_active_db_path_none_when_no_config():
    result = get_active_db_path()
    assert result is None


def test_get_active_db_path_none_when_file_missing(tmp_path):
    db_path = str(tmp_path / "nonexistent.db")
    config = AppConfig(
        databases={db_path: DatabaseEntry(name="Missing")},
        active_db=db_path,
    )
    save_config(config)
    result = get_active_db_path()
    assert result is None


def test_get_active_db_path_returns_path(tmp_path):
    db_file = tmp_path / "test.db"
    db_file.write_text("")
    config = AppConfig(
        databases={str(db_file): DatabaseEntry(name="Test")},
        active_db=str(db_file),
    )
    save_config(config)
    result = get_active_db_path()
    assert result == db_file


def test_get_default_db_path(tmp_path):
    result = get_default_db_path()
    assert result == tmp_path / "nightcrate.db"
