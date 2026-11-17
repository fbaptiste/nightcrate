"""NightCrate's yoyo backend: no network hostname lookup while logging."""

from __future__ import annotations

import socket
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from yoyo.backends import SQLiteBackend

from nightcrate.db.migrations import MigrationSQLiteBackend, apply_migrations, migration_backend


def test_applying_migrations_never_resolves_the_hostname(tmp_path: Path, monkeypatch):
    # conftest replaces yoyo's own socket reference; undo that here so the real
    # module, and this test's trap, are what yoyo would see in production.
    monkeypatch.setattr("yoyo.backends.base.socket", socket)

    def unexpected_lookup(*_args, **_kwargs):
        raise AssertionError("a network hostname lookup was made")

    monkeypatch.setattr(socket, "getfqdn", unexpected_lookup)
    db = tmp_path / "fresh.db"
    apply_migrations(db)

    with closing(sqlite3.connect(db)) as conn:
        hostnames = {row[0] for row in conn.execute("SELECT hostname FROM _yoyo_log")}
        logged = conn.execute("SELECT COUNT(*) FROM _yoyo_log").fetchone()[0]
    assert hostnames == {socket.gethostname()}
    assert logged > 0


def test_log_row_has_the_same_fields_as_yoyos(tmp_path: Path, monkeypatch):
    # A yoyo upgrade that changes its log row must not be silently ignored.
    monkeypatch.setattr("yoyo.backends.base.socket", socket)
    monkeypatch.setattr(socket, "getfqdn", lambda *a, **k: "host")
    with migration_backend(tmp_path / "fields.db") as backend:
        ours = backend.get_log_data(None, "apply")
        theirs = SQLiteBackend.get_log_data(backend, None, "apply")
    assert set(ours) == set(theirs)
    assert ours["hostname"] == socket.gethostname()


def test_unknown_log_operation_is_refused(tmp_path: Path):
    with migration_backend(tmp_path / "op.db") as backend:
        with pytest.raises(ValueError, match="unknown migration log operation"):
            MigrationSQLiteBackend.get_log_data(backend, None, "bogus")
