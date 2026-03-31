"""Apply yoyo migrations on startup."""

from pathlib import Path

from yoyo import get_backend, read_migrations

from nightcrate.db.session import DB_PATH, _ensure_app_dir

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def apply_migrations() -> None:
    """Run any pending migrations synchronously (called once at startup)."""
    _ensure_app_dir()
    backend = get_backend(f"sqlite:///{DB_PATH}")
    migrations = read_migrations(str(MIGRATIONS_DIR))
    with backend.lock():
        backend.apply_migrations(backend.to_apply(migrations))
