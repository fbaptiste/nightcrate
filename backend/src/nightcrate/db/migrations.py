"""Apply yoyo migrations on startup."""

from pathlib import Path

from yoyo import get_backend, read_migrations

from nightcrate.db.session import _ensure_app_dir, get_db_path

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


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
    backend = get_backend(f"sqlite:///{path}")
    migrations = read_migrations(str(MIGRATIONS_DIR))
    with backend.lock():
        backend.apply_migrations(backend.to_apply(migrations))
