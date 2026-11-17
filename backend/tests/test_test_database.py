"""Regression tests for the shared test-database template."""

import csv
import hashlib
import importlib.resources
import os
import shutil
import socket
import sqlite3
from contextlib import closing
from pathlib import Path

import yoyo.backends.base
from yoyo import get_backend, read_migrations

from nightcrate.core import app_config
from nightcrate.db.migrations import MIGRATIONS_DIR
from nightcrate.db.session import get_db_path


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_each_test_gets_its_own_file(tmp_path):
    assert get_db_path() == tmp_path / "test.db"
    assert os.stat(get_db_path()).st_nlink == 1
    assert app_config.APP_DIR == tmp_path


def test_database_is_fully_migrated_and_seeded():
    migrations_dir = importlib.resources.files("nightcrate") / "db" / "migrations"
    migration_count = sum(
        path.name[0].isdigit() and path.suffix in {".sql", ".py"}
        for path in migrations_dir.iterdir()
    )
    seed_csv = importlib.resources.files("nightcrate") / "data" / "seed" / "filter_type.csv"
    with seed_csv.open(newline="") as handle:
        seed_count = sum(1 for _row in csv.DictReader(handle))

    with closing(sqlite3.connect(get_db_path())) as conn:
        assert conn.execute("SELECT COUNT(*) FROM _yoyo_migration").fetchone()[0] == migration_count
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert conn.execute("SELECT COUNT(*) FROM filter_type").fetchone()[0] == seed_count


def test_copies_are_independent(tmp_path, _template_db):
    template_digest = _digest(_template_db)
    with closing(sqlite3.connect(get_db_path())) as conn:
        conn.execute("INSERT INTO recent_files (path) VALUES ('marker')")
        conn.commit()

    assert _digest(_template_db) == template_digest
    with closing(sqlite3.connect(_template_db)) as conn:
        assert (
            conn.execute("SELECT COUNT(*) FROM recent_files WHERE path = 'marker'").fetchone()[0]
            == 0
        )

    other_db = tmp_path / "other.db"
    shutil.copyfile(_template_db, other_db)
    with closing(sqlite3.connect(other_db)) as conn:
        assert (
            conn.execute("SELECT COUNT(*) FROM recent_files WHERE path = 'marker'").fetchone()[0]
            == 0
        )


def test_next_test_gets_a_pristine_copy():
    with closing(sqlite3.connect(get_db_path())) as conn:
        assert (
            conn.execute("SELECT COUNT(*) FROM recent_files WHERE path = 'marker'").fetchone()[0]
            == 0
        )


def test_yoyo_logging_never_resolves_the_hostname(tmp_path, monkeypatch):
    # Tests that open yoyo directly (the template, the migration tests) rely
    # on the conftest patch; the app's own backend never looks the name up
    # (tests/test_migrations_backend.py).
    def unexpected_lookup(*_args, **_kwargs):
        raise AssertionError("yoyo attempted a hostname lookup")

    monkeypatch.setattr(socket, "getfqdn", unexpected_lookup)
    fresh_db = tmp_path / "fresh.db"
    with get_backend(f"sqlite:///{fresh_db}") as backend:
        backend.apply_migrations(backend.to_apply(read_migrations(str(MIGRATIONS_DIR))))

    with closing(sqlite3.connect(fresh_db)) as conn:
        hostnames = conn.execute("SELECT DISTINCT hostname FROM _yoyo_log").fetchall()
    assert hostnames == [("nightcrate-tests",)]


def test_socket_module_is_untouched():
    assert socket.getfqdn.__module__ == "socket"
    assert yoyo.backends.base.socket is not socket
