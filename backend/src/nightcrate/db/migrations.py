"""Apply yoyo migrations on startup."""

import getpass
import socket
import uuid
from datetime import UTC, datetime
from pathlib import Path

from yoyo import read_migrations
from yoyo.backends import SQLiteBackend
from yoyo.connections import parse_uri
from yoyo.migrations import default_migration_table

from nightcrate.db.session import _ensure_app_dir, get_db_path

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


class MigrationSQLiteBackend(SQLiteBackend):
    """Yoyo backend that makes parent-table rebuilds independent of SQLite defaults."""

    def init_connection(self, connection) -> None:
        super().init_connection(connection)
        connection.execute("PRAGMA foreign_keys = OFF")
        row = connection.execute("PRAGMA foreign_keys").fetchone()
        if row is None or row[0] != 0:
            raise RuntimeError("SQLite foreign keys must be disabled while applying migrations")

    def get_log_data(self, migration=None, operation="apply"):
        """yoyo's ``_yoyo_log`` row, without its network hostname lookup.

        yoyo calls ``socket.getfqdn()`` for every row it logs: 74 on a new
        workspace. On a Mac whose hostname doesn't resolve, one call took 70 s
        on GitHub's runner (v0.54.1), so creating a workspace could take an
        hour. The plain host name is local. The fields match yoyo 9.0's
        (``tests/test_migrations_backend.py`` checks they still do).
        """
        if operation not in {"apply", "rollback", "mark", "unmark"}:
            raise ValueError(f"unknown migration log operation: {operation}")
        return {
            "id": str(uuid.uuid1()),
            "migration_id": migration.id if migration else None,
            "migration_hash": migration.hash if migration else None,
            "username": getpass.getuser(),
            "hostname": socket.gethostname(),
            "created_at_utc": datetime.now(UTC).replace(tzinfo=None),
            "operation": operation,
        }


def migration_backend(db_path: Path) -> MigrationSQLiteBackend:
    """Open a yoyo backend whose root and copied connections are migration-safe."""
    uri = parse_uri(f"sqlite:///{db_path}")
    backend = MigrationSQLiteBackend(uri, default_migration_table)
    backend.init_database()
    return backend


def apply_migrations(db_path: Path | None = None) -> None:
    """Run any pending migrations synchronously (called once at startup).

    Parameters
    ----------
    db_path:
        Path to the SQLite database. If None, uses the current active path
        from ``get_db_path()``. Pass an explicit path to run migrations on a
        newly created database before it becomes active.
    """
    _ensure_app_dir()
    path = db_path or get_db_path()
    with migration_backend(path) as backend:
        migrations = read_migrations(str(MIGRATIONS_DIR))
        with backend.lock():
            backend.apply_migrations(backend.to_apply(migrations))
