"""Guarded workspace backup, refusal, and migration tests."""

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

from nightcrate.db import durable_fs
from nightcrate.db import workspace_upgrade as upgrade


@pytest.fixture(autouse=True)
def _quiet_loaders(monkeypatch):
    monkeypatch.setattr(upgrade, "load_all", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(upgrade, "load_catalogs", lambda *_args, **_kwargs: None)


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _migration_files(folder):
    return sorted(
        path
        for path in folder.iterdir()
        if path.name[0].isdigit() and path.suffix in {".sql", ".py"}
    )


def _copy_migrations(tmp_path, name="migrations"):
    destination = tmp_path / name
    shutil.copytree(upgrade.MIGRATIONS_DIR, destination)
    return destination


def _run_python(source, *args):
    return subprocess.run(
        [sys.executable, "-c", source, *(str(arg) for arg in args)],
        check=False,
        capture_output=True,
        text=True,
    )


def _table_rows(db, table):
    with sqlite3.connect(db) as conn:
        return conn.execute(f"SELECT * FROM {table} ORDER BY id").fetchall()  # nosec B608


def test_fresh_workspace_no_backup(tmp_path):
    workspace = tmp_path / "fresh"
    result = upgrade.initialize_workspace(workspace, "Fresh", "1.2.3")
    assert result.backup_path is None
    assert result.migrations_applied == len(upgrade.known_hashes())
    applied = set(upgrade.read_applied_hashes(workspace / "nightcrate.db") or [])
    assert applied == upgrade.known_hashes()
    assert not (workspace / upgrade.BACKUP_DIR).exists()
    data = json.loads((workspace / upgrade.WORKSPACE_FILE).read_text())
    assert data == {"last_opened_by": "1.2.3", "completed_upgrade": None}


def test_upgrade_from_previous_migration_preserves_records(tmp_path, monkeypatch):
    workspace = tmp_path / "previous"
    workspace.mkdir()
    db = workspace / "nightcrate.db"
    original_migrations = upgrade.MIGRATIONS_DIR
    previous = _copy_migrations(tmp_path, "previous-migrations")
    newest = _migration_files(previous)[-1]
    newest.unlink()
    monkeypatch.setattr(upgrade, "MIGRATIONS_DIR", previous)
    upgrade.apply_migrations(db)
    upgrade.record_opened_by(workspace, "1.0")

    with sqlite3.connect(db) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        manufacturer_id = conn.execute(
            "INSERT INTO manufacturer (name) VALUES ('Preserved maker')"
        ).lastrowid
        sensor_id = conn.execute(
            "INSERT INTO sensor "
            "(manufacturer_id, model_name, sensor_type, pixel_size_um, resolution_x, resolution_y) "
            "VALUES (?, 'Preserved sensor', 'mono', 3.76, 100, 100)",
            (manufacturer_id,),
        ).lastrowid
        camera_id = conn.execute(
            "INSERT INTO camera (manufacturer_id, sensor_id, model_name) "
            "VALUES (?, ?, 'Preserved camera')",
            (manufacturer_id, sensor_id),
        ).lastrowid
        telescope_id = conn.execute(
            "INSERT INTO telescope (manufacturer_id, model_name, aperture_mm) "
            "VALUES (?, 'Preserved telescope', 80)",
            (manufacturer_id,),
        ).lastrowid
        configuration_id = conn.execute(
            "INSERT INTO telescope_configuration "
            "(telescope_id, config_name, effective_focal_length_mm, effective_focal_ratio) "
            "VALUES (?, 'Native', 400, 5)",
            (telescope_id,),
        ).lastrowid
        location_id = conn.execute(
            "INSERT INTO location (name, latitude, longitude, timezone) "
            "VALUES ('Preserved location', 33.4, -112.1, 'America/Phoenix')"
        ).lastrowid
        conn.execute(
            "INSERT INTO project (name, description, notes, location_id) "
            "VALUES ('Preserved project', 'description', 'notes', ?)",
            (location_id,),
        )
        conn.execute(
            "INSERT INTO rig (name, description, telescope_configuration_id, camera_id, notes) "
            "VALUES ('Preserved rig', 'description', ?, ?, 'notes')",
            (configuration_id, camera_id),
        )

    before = {table: _table_rows(db, table) for table in ("project", "location", "rig")}
    before_count = len(upgrade.read_applied_hashes(db) or [])
    monkeypatch.setattr(upgrade, "MIGRATIONS_DIR", original_migrations)
    result = upgrade.initialize_workspace(workspace, "Previous", "2.0")

    assert result.migrations_applied == 1
    assert result.backup_path is not None
    assert len(list((workspace / upgrade.BACKUP_DIR).glob("nightcrate-before-*.db"))) == 1
    assert {table: _table_rows(db, table) for table in before} == before
    with sqlite3.connect(db) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    backup = result.backup_path
    assert {table: _table_rows(backup, table) for table in before} == before
    assert len(upgrade.read_applied_hashes(backup) or []) == before_count
    assert not (workspace / upgrade.BACKUP_DIR / upgrade.MARKER_FILE).exists()


def test_same_version_reopen_takes_no_backup(tmp_path):
    workspace = tmp_path / "same"
    upgrade.initialize_workspace(workspace, "Same", "1.2.3")
    result = upgrade.initialize_workspace(workspace, "Same", "1.2.3")
    assert result.backup_path is None


def test_version_change_takes_one_backup(tmp_path):
    workspace = tmp_path / "changed"
    upgrade.initialize_workspace(workspace, "Changed", "1.2.3")
    result = upgrade.initialize_workspace(workspace, "Changed", "1.2.4")
    assert result.backup_path is not None
    assert result.backup_path.is_file()
    assert len(list((workspace / upgrade.BACKUP_DIR).glob("nightcrate-before-*.db"))) == 1


def test_refusal_probe_is_read_only(tmp_path):
    db = tmp_path / "plain.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE example (value TEXT)")
    before = _digest(db)
    assert upgrade.read_applied_hashes(db) == []
    assert _digest(db) == before


def test_unreadable_metadata_refused(tmp_path):
    workspace = tmp_path / "bad metadata"
    workspace.mkdir()
    db = workspace / "nightcrate.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE _yoyo_migration (wrong_column TEXT)")
    before = _digest(db)
    with pytest.raises(upgrade.WorkspaceRefused) as caught:
        upgrade.initialize_workspace(workspace, "Bad", "1.0")
    assert caught.value.problem.kind == "unreadable"
    assert _digest(db) == before


def test_newer_database_refused_untouched(tmp_path):
    workspace = tmp_path / "newer"
    upgrade.initialize_workspace(workspace, "Newer", "1.0")
    db = workspace / "nightcrate.db"
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO _yoyo_migration VALUES (?, ?, datetime('now'))",
            ("foreign-hash", "9999.future"),
        )
    upgrade.record_opened_by(workspace, "0.56.0")
    before = _digest(db)
    with pytest.raises(upgrade.WorkspaceRefused) as caught:
        upgrade.initialize_workspace(workspace, "Newer", "0.53.0")
    assert caught.value.problem.kind == "newer"
    assert caught.value.problem.last_opened_by == "0.56.0"
    assert _digest(db) == before
    assert not (workspace / upgrade.BACKUP_DIR).exists()


def test_failed_migration_restores_backup(tmp_path, monkeypatch):
    workspace = tmp_path / "failure"
    upgrade.initialize_workspace(workspace, "Failure", "1.0")
    db = workspace / "nightcrate.db"
    with sqlite3.connect(db) as conn:
        conn.execute("INSERT INTO settings (key, value_json) VALUES ('proof', '1')")
    migrations = tmp_path / "migrations"
    shutil.copytree(upgrade.MIGRATIONS_DIR, migrations)
    (migrations / "9999.fail.sql").write_text("THIS IS NOT SQL;", encoding="utf-8")
    monkeypatch.setattr(upgrade, "MIGRATIONS_DIR", migrations)
    with pytest.raises(upgrade.WorkspaceRefused) as caught:
        upgrade.initialize_workspace(
            workspace, "Failure", "2.0", now=datetime(2026, 11, 15, 12, 0, 0)
        )
    assert caught.value.problem.kind == "upgrade_failed"
    backup = Path(caught.value.problem.backup_path)
    assert db.read_bytes() == backup.read_bytes()
    assert not (workspace / upgrade.BACKUP_DIR / upgrade.MARKER_FILE).exists()
    with sqlite3.connect(db) as conn:
        row = conn.execute("SELECT value_json FROM settings WHERE key='proof'").fetchone()
        assert row == ("1",)


@pytest.mark.skipif(os.name == "nt", reason="symlink behavior requires POSIX")
def test_symlinked_database_failed_migration_restores_real_target(tmp_path, monkeypatch):
    target = tmp_path / "database-target" / "real.db"
    target.parent.mkdir()
    upgrade.apply_migrations(target)
    with sqlite3.connect(target) as conn:
        conn.execute("INSERT INTO settings (key, value_json) VALUES ('symlink-proof', '1')")

    workspace = tmp_path / "symlink-failure"
    workspace.mkdir()
    logical = workspace / "nightcrate.db"
    logical.symlink_to(target)
    upgrade.record_opened_by(workspace, "1.0")
    migrations = _copy_migrations(tmp_path, "symlink-failure-migrations")
    (migrations / "9999.fail.sql").write_text(
        "-- depends: 0073.project_ready_to_process\nTHIS IS NOT SQL;\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(upgrade, "MIGRATIONS_DIR", migrations)

    with pytest.raises(upgrade.WorkspaceRefused) as caught:
        upgrade.initialize_workspace(workspace, "Symlink", "2.0")

    assert caught.value.problem.kind == "upgrade_failed"
    backup = Path(caught.value.problem.backup_path)
    assert logical.is_symlink()
    assert logical.resolve() == target.resolve()
    assert target.read_bytes() == backup.read_bytes()
    assert all(not Path(f"{target}{suffix}").exists() for suffix in ("-journal", "-wal", "-shm"))


@pytest.mark.skipif(os.name == "nt", reason="symlink behavior requires POSIX")
def test_symlinked_database_normal_migration_preserves_rows(tmp_path, monkeypatch):
    target = tmp_path / "database-target" / "real.db"
    target.parent.mkdir()
    upgrade.apply_migrations(target)
    with sqlite3.connect(target) as conn:
        conn.execute("INSERT INTO settings (key, value_json) VALUES ('symlink-proof', '1')")

    workspace = tmp_path / "symlink-success"
    workspace.mkdir()
    logical = workspace / "nightcrate.db"
    logical.symlink_to(target)
    upgrade.record_opened_by(workspace, "1.0")
    migrations = _copy_migrations(tmp_path, "symlink-success-migrations")
    (migrations / "9998.success.sql").write_text(
        "-- depends: 0073.project_ready_to_process\n"
        "INSERT INTO settings (key, value_json) VALUES ('symlink-migration', '1');\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(upgrade, "MIGRATIONS_DIR", migrations)

    result = upgrade.initialize_workspace(workspace, "Symlink", "2.0")

    assert result.migrations_applied == 1
    assert logical.is_symlink()
    assert result.backup_path is not None
    assert result.backup_path.parent == workspace / upgrade.BACKUP_DIR
    with sqlite3.connect(target) as conn:
        assert conn.execute(
            "SELECT key, value_json FROM settings WHERE key LIKE 'symlink-%' ORDER BY key"
        ).fetchall() == [("symlink-migration", "1"), ("symlink-proof", "1")]


def test_hard_linked_database_is_refused_without_changes_or_backup(tmp_path):
    target = tmp_path / "hard-link-target.db"
    upgrade.apply_migrations(target)
    with sqlite3.connect(target) as conn:
        conn.execute("INSERT INTO settings (key, value_json) VALUES ('hard-link-proof', '1')")

    workspace = tmp_path / "hard-link-workspace"
    workspace.mkdir()
    logical = workspace / "nightcrate.db"
    os.link(target, logical)
    upgrade.record_opened_by(workspace, "1.0")
    before = target.read_bytes()

    with pytest.raises(upgrade.WorkspaceRefused) as caught:
        upgrade.initialize_workspace(workspace, "Hard link", "2.0")

    assert caught.value.problem.kind == "unreadable"
    assert caught.value.problem.error == (
        "nightcrate.db has other hard links, so NightCrate can't upgrade it safely. "
        "Copy it to a new file, then reopen the workspace."
    )
    assert target.read_bytes() == before
    assert logical.read_bytes() == before
    assert not (workspace / upgrade.BACKUP_DIR).exists()


def test_failed_migration_restores_backup_wal(tmp_path, monkeypatch):
    workspace = tmp_path / "wal-failure"
    upgrade.initialize_workspace(workspace, "WAL", "1.0")
    db = workspace / "nightcrate.db"
    crashed = _run_python(
        """import os, sqlite3, sys
conn = sqlite3.connect(sys.argv[1])
conn.execute("PRAGMA journal_mode = WAL")
conn.execute("PRAGMA wal_autocheckpoint = 0")
conn.execute("INSERT INTO settings (key, value_json) VALUES ('wal-proof', 'committed')")
conn.commit()
os._exit(7)
""",
        db,
    )
    assert crashed.returncode == 7, crashed.stderr
    wal = Path(f"{db}-wal")
    assert wal.is_file()
    assert wal.stat().st_size > 0

    migrations = _copy_migrations(tmp_path, "wal-failure-migrations")
    (migrations / "9999.fail.sql").write_text(
        "-- depends: 0073.project_ready_to_process\nTHIS IS NOT SQL;\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(upgrade, "MIGRATIONS_DIR", migrations)
    with pytest.raises(upgrade.WorkspaceRefused) as caught:
        upgrade.initialize_workspace(workspace, "WAL", "2.0")

    assert caught.value.problem.kind == "upgrade_failed"
    backup = Path(caught.value.problem.backup_path)
    assert db.read_bytes() == backup.read_bytes()
    assert all(not Path(f"{db}{suffix}").exists() for suffix in ("-wal", "-shm"))
    with sqlite3.connect(f"file:{db}?mode=ro&immutable=1", uri=True) as conn:
        assert conn.execute("SELECT value_json FROM settings WHERE key='wal-proof'").fetchone() == (
            "committed",
        )
    assert all(not Path(f"{db}{suffix}").exists() for suffix in ("-wal", "-shm"))


def test_every_connection_closed(tmp_path, monkeypatch):
    successful = tmp_path / "successful"
    failed = tmp_path / "failed"
    upgrade.initialize_workspace(successful, "Successful", "1.0")
    upgrade.initialize_workspace(failed, "Failed", "1.0")

    original_connect = sqlite3.connect
    original_replace = os.replace
    connections = []
    replace_checks = []

    class TrackingConnection(sqlite3.Connection):
        closed = False

        def close(self):
            self.closed = True
            super().close()

    def connect(*args, **kwargs):
        kwargs["factory"] = TrackingConnection
        connection = original_connect(*args, **kwargs)
        connections.append(connection)
        return connection

    def replace(source, destination):
        if Path(destination).suffix == ".db":
            assert all(connection.closed for connection in connections)
            replace_checks.append(Path(destination))
        return original_replace(source, destination)

    monkeypatch.setattr(upgrade.sqlite3, "connect", connect)
    monkeypatch.setattr(upgrade.os, "replace", replace)

    migrations = _copy_migrations(tmp_path, "connection-migrations")
    (migrations / "9998.success.sql").write_text(
        "-- depends: 0073.project_ready_to_process\n"
        "INSERT INTO settings (key, value_json) VALUES ('connection-success', '1');\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(upgrade, "MIGRATIONS_DIR", migrations)
    upgrade.initialize_workspace(successful, "Successful", "2.0")
    assert all(connection.closed for connection in connections)

    (migrations / "9999.fail.sql").write_text(
        "-- depends: 9998.success\nTHIS IS NOT SQL;\n", encoding="utf-8"
    )
    with pytest.raises(upgrade.WorkspaceRefused) as caught:
        upgrade.initialize_workspace(failed, "Failed", "2.0")
    assert caught.value.problem.kind == "upgrade_failed"
    assert all(connection.closed for connection in connections)
    assert successful / upgrade.BACKUP_DIR in {path.parent for path in replace_checks}
    assert failed / "nightcrate.db" in replace_checks


def test_backups_never_overwrite(tmp_path):
    workspace = tmp_path / "backups"
    upgrade.initialize_workspace(workspace, "Backups", "1.0")
    db = workspace / "nightcrate.db"
    now = datetime(2026, 11, 15, 12, 0, 0)
    first = upgrade.backup_database(db, "1.0", now)
    second = upgrade.backup_database(db, "1.0", now)
    assert first != second
    assert first.is_file() and second.is_file()


@pytest.mark.skipif(os.name == "nt", reason="directory fsync is POSIX-only")
def test_durable_steps_fsync_directories(tmp_path, monkeypatch):
    successful = tmp_path / "durable-success"
    failed = tmp_path / "durable-failure"
    upgrade.initialize_workspace(successful, "Success", "1.0")
    upgrade.initialize_workspace(failed, "Failure", "1.0")
    migrations = _copy_migrations(tmp_path, "durable-migrations")
    (migrations / "9998.success.sql").write_text(
        "-- depends: 0073.project_ready_to_process\n"
        "INSERT INTO settings (key, value_json) VALUES ('durable-success', '1');\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(upgrade, "MIGRATIONS_DIR", migrations)

    real_open = durable_fs.os.open
    real_fsync = durable_fs.os.fsync
    real_close = durable_fs.os.close
    directory_fds = {}
    events = []

    def open_spy(path, flags, *args, **kwargs):
        is_directory = Path(path).is_dir()
        fd = real_open(path, flags, *args, **kwargs)
        if is_directory:
            directory_fds[fd] = Path(path).resolve()
        else:
            directory_fds.pop(fd, None)
        return fd

    def fsync_spy(fd):
        if fd in directory_fds:
            events.append(directory_fds[fd])
        return real_fsync(fd)

    def close_spy(fd):
        directory_fds.pop(fd, None)
        return real_close(fd)

    monkeypatch.setattr(durable_fs.os, "open", open_spy)
    monkeypatch.setattr(durable_fs.os, "fsync", fsync_spy)
    monkeypatch.setattr(durable_fs.os, "close", close_spy)

    upgrade.initialize_workspace(successful, "Success", "2.0")
    assert events == [
        successful.resolve(),
        (successful / upgrade.BACKUP_DIR).resolve(),
        (successful / upgrade.BACKUP_DIR).resolve(),
        successful.resolve(),
        (successful / upgrade.BACKUP_DIR).resolve(),
    ]

    events.clear()
    (migrations / "9999.fail.sql").write_text(
        "-- depends: 9998.success\nTHIS IS NOT SQL;\n", encoding="utf-8"
    )
    with pytest.raises(upgrade.WorkspaceRefused) as caught:
        upgrade.initialize_workspace(failed, "Failure", "2.0")
    assert caught.value.problem.kind == "upgrade_failed"
    assert events == [
        failed.resolve(),
        (failed / upgrade.BACKUP_DIR).resolve(),
        (failed / upgrade.BACKUP_DIR).resolve(),
        failed.resolve(),
        (failed / upgrade.BACKUP_DIR).resolve(),
    ]


def test_non_ascii_workspace_path(tmp_path):
    workspace = tmp_path / "Ma Bibliothèque ✨"
    upgrade.initialize_workspace(workspace, "Bibliothèque", "1.0")
    assert (workspace / "nightcrate.db").is_file()


def _marker(backup, marker_id="abc123"):
    return {
        "id": marker_id,
        "backup": backup.name,
        "from_version": "1.0",
        "to_version": "2.0",
        "state": "upgrading",
        "started_at": "2026-11-15T12:00:00",
    }


def test_unfinished_marker_restores_before_sqlite_opens(tmp_path, monkeypatch):
    workspace = tmp_path / "interrupted"
    upgrade.initialize_workspace(workspace, "Interrupted", "1.0")
    db = workspace / "nightcrate.db"
    backup = upgrade.backup_database(db, "2.0", datetime(2026, 11, 15, 12, 0, 0))
    folder = workspace / upgrade.BACKUP_DIR
    upgrade.durable_write(folder / upgrade.MARKER_FILE, json.dumps(_marker(backup)).encode())
    db.write_bytes(b"not a sqlite database")
    Path(f"{db}-journal").write_bytes(b"stale journal")

    restored = False
    original_restore = upgrade.restore_backup
    original_connect = upgrade.sqlite3.connect

    def restore(*args):
        nonlocal restored
        original_restore(*args)
        restored = True

    def connect(database, *args, **kwargs):
        if str(db) in str(database):
            assert restored, "SQLite opened the workspace before marker recovery"
        return original_connect(database, *args, **kwargs)

    monkeypatch.setattr(upgrade, "restore_backup", restore)
    monkeypatch.setattr(upgrade.sqlite3, "connect", connect)
    upgrade.initialize_workspace(workspace, "Interrupted", "2.0")
    assert restored
    assert not (folder / upgrade.MARKER_FILE).exists()
    assert set(upgrade.read_applied_hashes(db) or []) == upgrade.known_hashes()


def test_hot_journal_recovered_before_probe(tmp_path):
    workspace = tmp_path / "hot journal"
    upgrade.initialize_workspace(workspace, "Hot journal", "1.0")
    db = workspace / "nightcrate.db"
    with sqlite3.connect(db) as conn:
        conn.execute("INSERT INTO settings (key, value_json) VALUES ('journal-proof', 'before')")
        conn.execute("PRAGMA journal_mode = DELETE")
    crashed = _run_python(
        """import os, sqlite3, sys
conn = sqlite3.connect(sys.argv[1])
conn.execute("PRAGMA journal_mode = DELETE")
conn.execute("BEGIN IMMEDIATE")
conn.execute("UPDATE settings SET value_json='uncommitted' WHERE key='journal-proof'")
os._exit(4)
""",
        db,
    )
    assert crashed.returncode == 4
    assert Path(f"{db}-journal").is_file()

    upgrade.initialize_workspace(workspace, "Hot journal", "1.0")
    with sqlite3.connect(db) as conn:
        assert conn.execute(
            "SELECT value_json FROM settings WHERE key='journal-proof'"
        ).fetchone() == ("before",)


def test_recovery_failure_is_unreadable(tmp_path):
    workspace = tmp_path / "corrupt journal"
    workspace.mkdir()
    db = workspace / "nightcrate.db"
    db.write_bytes(b"not sqlite")
    Path(f"{db}-journal").write_bytes(b"hot")
    with pytest.raises(upgrade.WorkspaceRefused) as caught:
        upgrade.initialize_workspace(workspace, "Corrupt", "1.0")
    assert caught.value.problem.kind == "unreadable"
    assert caught.value.problem.error is not None


def test_interrupted_upgrade_restores_then_upgrades(tmp_path, monkeypatch):
    workspace = tmp_path / "crash recovery"
    upgrade.initialize_workspace(workspace, "Crash recovery", "1.0")
    db = workspace / "nightcrate.db"
    migrations = _copy_migrations(tmp_path, "crash-migrations")
    (migrations / "9997.write.sql").write_text(
        "-- depends: 0073.project_ready_to_process\n"
        "INSERT INTO settings (key, value_json) VALUES ('crash-write', '1');\n",
        encoding="utf-8",
    )
    die_migration = migrations / "9998.die.py"
    die_migration.write_text(
        """import os
from yoyo import step

__depends__ = {"9997.write"}

def apply(conn):
    conn.execute("INSERT INTO settings (key, value_json) VALUES ('die-write', '1')")
    os._exit(1)

steps = [step(apply)]
""",
        encoding="utf-8",
    )
    crash = _run_python(
        """import sys
from pathlib import Path
from nightcrate.db import workspace_upgrade as upgrade
upgrade.MIGRATIONS_DIR = Path(sys.argv[2])
upgrade.initialize_workspace(Path(sys.argv[1]), "Crash recovery", "2.0")
""",
        workspace,
        migrations,
    )
    assert crash.returncode == 1, crash.stderr
    marker_path = workspace / upgrade.BACKUP_DIR / upgrade.MARKER_FILE
    assert marker_path.is_file()
    backups = list((workspace / upgrade.BACKUP_DIR).glob("nightcrate-before-*.db"))
    assert len(backups) == 1

    die_migration.unlink()
    for suffix in ("-journal", "-wal", "-shm"):
        Path(f"{db}{suffix}").write_bytes(b"discarded")
    restore_crash = _run_python(
        """import os, sys
from pathlib import Path
from nightcrate.db import workspace_upgrade as upgrade
workspace = Path(sys.argv[1])
db = workspace / "nightcrate.db"
upgrade.MIGRATIONS_DIR = Path(sys.argv[2])
real_replace = upgrade.os.replace
def die_after_journal_cleanup(source, destination):
    if Path(destination) == db and Path(source).name == f".{db.name}.restore":
        os._exit(2)
    return real_replace(source, destination)
upgrade.os.replace = die_after_journal_cleanup
upgrade.initialize_workspace(workspace, "Crash recovery", "2.0")
""",
        workspace,
        migrations,
    )
    assert restore_crash.returncode == 2, restore_crash.stderr
    assert marker_path.is_file()
    assert all(not Path(f"{db}{suffix}").exists() for suffix in ("-journal", "-wal", "-shm"))

    monkeypatch.setattr(upgrade, "MIGRATIONS_DIR", migrations)
    upgrade.initialize_workspace(workspace, "Crash recovery", "2.0")
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM settings WHERE key='crash-write'").fetchone() == (
            1,
        )
        assert conn.execute("SELECT COUNT(*) FROM settings WHERE key='die-write'").fetchone() == (
            0,
        )
        assert conn.execute("SELECT * FROM yoyo_lock").fetchall() == []
    assert set(upgrade.read_applied_hashes(db) or []) == upgrade.known_hashes()
    assert len(list((workspace / upgrade.BACKUP_DIR).glob("nightcrate-before-*.db"))) == 1
    assert not marker_path.exists()

    (migrations / "9999.later.sql").write_text(
        "-- depends: 9997.write\n"
        "INSERT INTO settings (key, value_json) VALUES ('later-write', '1');\n",
        encoding="utf-8",
    )
    upgrade.initialize_workspace(workspace, "Crash recovery", "3.0")
    with sqlite3.connect(db) as conn:
        assert conn.execute(
            "SELECT value_json FROM settings WHERE key='later-write'"
        ).fetchone() == ("1",)


def test_stale_marker_after_finished_upgrade_keeps_records(tmp_path, monkeypatch):
    workspace = tmp_path / "finished"
    upgrade.initialize_workspace(workspace, "Finished", "1.0")
    db = workspace / "nightcrate.db"
    backup = upgrade.backup_database(db, "1.0", datetime(2026, 11, 15, 12, 0, 0))
    with sqlite3.connect(db) as conn:
        conn.execute("INSERT INTO settings (key, value_json) VALUES ('after', '42')")
    marker = _marker(backup, "finished-id")
    upgrade.durable_write(
        workspace / upgrade.BACKUP_DIR / upgrade.MARKER_FILE,
        json.dumps(marker).encode(),
    )
    upgrade.durable_write(
        workspace / upgrade.WORKSPACE_FILE,
        json.dumps({"last_opened_by": "1.0", "completed_upgrade": "finished-id"}).encode(),
    )
    upgrade.initialize_workspace(workspace, "Finished", "1.0")
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT value_json FROM settings WHERE key='after'").fetchone() == (
            "42",
        )
    assert not (workspace / upgrade.BACKUP_DIR / upgrade.MARKER_FILE).exists()

    migrations = _copy_migrations(tmp_path, "later-migrations")
    (migrations / "9998.later.sql").write_text(
        "-- depends: 0073.project_ready_to_process\n"
        "INSERT INTO settings (key, value_json) VALUES ('later-version', '1');\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(upgrade, "MIGRATIONS_DIR", migrations)
    later_marker = _marker(backup, "later-finished-id")
    upgrade.durable_write(
        workspace / upgrade.BACKUP_DIR / upgrade.MARKER_FILE,
        json.dumps(later_marker).encode(),
    )
    upgrade.record_opened_by(workspace, "1.0", completed_upgrade="later-finished-id")
    result = upgrade.initialize_workspace(workspace, "Finished", "2.0")
    assert result.backup_path is not None and result.backup_path != backup
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT value_json FROM settings WHERE key='after'").fetchone() == (
            "42",
        )
        assert conn.execute(
            "SELECT value_json FROM settings WHERE key='later-version'"
        ).fetchone() == ("1",)

    hot_marker = _marker(backup, "hot-finished-id")
    upgrade.durable_write(
        workspace / upgrade.BACKUP_DIR / upgrade.MARKER_FILE,
        json.dumps(hot_marker).encode(),
    )
    upgrade.record_opened_by(workspace, "2.0", completed_upgrade="hot-finished-id")
    hot = _run_python(
        """import os, sqlite3, sys
conn = sqlite3.connect(sys.argv[1])
conn.execute("PRAGMA journal_mode = DELETE")
conn.execute("BEGIN IMMEDIATE")
conn.execute("UPDATE settings SET value_json='lost' WHERE key='after'")
conn.execute("INSERT INTO settings (key, value_json) VALUES ('hot-uncommitted', '1')")
os._exit(3)
""",
        db,
    )
    assert hot.returncode == 3
    assert Path(f"{db}-journal").is_file()
    upgrade.initialize_workspace(workspace, "Finished", "2.0")
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT value_json FROM settings WHERE key='after'").fetchone() == (
            "42",
        )
        assert conn.execute(
            "SELECT COUNT(*) FROM settings WHERE key='hot-uncommitted'"
        ).fetchone() == (0,)


def test_restore_failure_blocks_and_retries(tmp_path, monkeypatch):
    workspace = tmp_path / "restore failure"
    upgrade.initialize_workspace(workspace, "Restore", "1.0")
    migrations = _copy_migrations(tmp_path, "restore-failure-migrations")
    (migrations / "9999.fail.sql").write_text(
        "-- depends: 0073.project_ready_to_process\nTHIS IS NOT SQL;\n", encoding="utf-8"
    )
    monkeypatch.setattr(upgrade, "MIGRATIONS_DIR", migrations)
    original_restore = upgrade.restore_backup

    def fail_restore(*_args):
        raise OSError("restore blocked")

    monkeypatch.setattr(upgrade, "restore_backup", fail_restore)
    marker_path = workspace / upgrade.BACKUP_DIR / upgrade.MARKER_FILE
    with pytest.raises(upgrade.WorkspaceRefused) as caught:
        upgrade.initialize_workspace(workspace, "Restore", "2.0")
    assert caught.value.problem.kind == "restore_failed"
    assert json.loads(marker_path.read_text())["state"] == "restore_failed"

    monkeypatch.setattr(upgrade, "restore_backup", original_restore)
    steps = []
    marker_states = []
    original_write_marker = upgrade._write_marker

    def write_marker(workspace_path, marker):
        marker_states.append(marker["state"])
        original_write_marker(workspace_path, marker)

    monkeypatch.setattr(upgrade, "_write_marker", write_marker)
    with pytest.raises(upgrade.WorkspaceRefused) as retried:
        upgrade.initialize_workspace(workspace, "Restore", "2.0", on_step=steps.append)
    assert retried.value.problem.kind == "upgrade_failed"
    assert steps == ["upgrading"]
    assert marker_states == ["upgrading"]
    assert not marker_path.exists()


def test_backup_failure_migrates_nothing(tmp_path, monkeypatch):
    workspace = tmp_path / "no space"
    upgrade.initialize_workspace(workspace, "No space", "1.0")
    db = workspace / "nightcrate.db"
    before = _digest(db)
    before_hashes = upgrade.read_applied_hashes(db)
    monkeypatch.setattr(
        upgrade,
        "backup_database",
        lambda *_args: (_ for _ in ()).throw(OSError("No space left on device")),
    )
    with pytest.raises(upgrade.WorkspaceRefused) as caught:
        upgrade.initialize_workspace(workspace, "No space", "2.0")
    assert caught.value.problem.kind == "backup_failed"
    assert _digest(db) == before
    assert upgrade.read_applied_hashes(db) == before_hashes


def test_prune_keeps_three_newest_and_marker_backup(tmp_path):
    workspace = tmp_path / "prune"
    folder = workspace / upgrade.BACKUP_DIR
    folder.mkdir(parents=True)
    backups = []
    for index in range(4):
        path = folder / f"nightcrate-before-1.0-2026-11-15-12000{index}.db"
        path.write_bytes(str(index).encode())
        os.utime(path, ns=(index + 1, index + 1))
        backups.append(path)
    (folder / "notes.txt").write_text("keep me")
    upgrade.durable_write(folder / upgrade.MARKER_FILE, json.dumps(_marker(backups[0])).encode())
    upgrade.prune_backups(workspace, None)
    assert set(folder.glob("nightcrate-before-*.db")) == set(backups)
    assert (folder / "notes.txt").read_text() == "keep me"


def test_loader_error_boundary(tmp_path, monkeypatch):
    workspace = tmp_path / "loaders"
    monkeypatch.setattr(
        upgrade, "load_all", lambda *_args: (_ for _ in ()).throw(ValueError("bad"))
    )
    upgrade.initialize_workspace(workspace, "Loaders", "1.0")
    monkeypatch.setattr(upgrade, "load_all", lambda *_args: (_ for _ in ()).throw(TypeError("bug")))
    with pytest.raises(TypeError, match="bug"):
        upgrade.initialize_workspace(workspace, "Loaders", "1.0")


def test_marker_backup_cannot_escape_workspace(tmp_path):
    workspace = tmp_path / "marker traversal"
    upgrade.initialize_workspace(workspace, "Marker", "1.0")
    marker = _marker(Path("outside.db"))
    marker["backup"] = "../../outside.db"
    folder = workspace / upgrade.BACKUP_DIR
    upgrade.durable_write(folder / upgrade.MARKER_FILE, json.dumps(marker).encode())
    with pytest.raises(upgrade.WorkspaceRefused) as caught:
        upgrade.initialize_workspace(workspace, "Marker", "1.0")
    assert caught.value.problem.kind == "unreadable"


@pytest.fixture
def windows_style_fsync(monkeypatch):
    """Make ``os.fsync`` refuse read-only file handles, as Windows does.

    Windows' flush needs write access and fails with EBADF otherwise. Every
    workspace backup failed there until v0.54.0's update rehearsal caught it.
    Directories are exempt: NightCrate never syncs them on Windows.
    """
    if os.name == "nt":
        return
    import fcntl
    import stat

    real_fsync = os.fsync

    def fsync(fd):
        if not stat.S_ISDIR(os.fstat(fd).st_mode) and fcntl.fcntl(fd, fcntl.F_GETFL) & 3 == 0:
            raise OSError(9, "Bad file descriptor")
        return real_fsync(fd)

    monkeypatch.setattr(os, "fsync", fsync)


def test_backup_and_restore_flush_through_writable_handles(tmp_path, windows_style_fsync):
    workspace = tmp_path / "windows"
    upgrade.initialize_workspace(workspace, "Windows", "1.0")
    result = upgrade.initialize_workspace(workspace, "Windows", "1.1")
    assert result.backup_path is not None
    assert result.backup_path.is_file()

    db = workspace / "nightcrate.db"
    with sqlite3.connect(db) as conn:
        conn.execute("INSERT INTO settings (key, value_json) VALUES ('after', '1')")
    upgrade.restore_backup(result.backup_path, db)
    assert db.read_bytes() == result.backup_path.read_bytes()
