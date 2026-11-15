"""Guarded, recoverable workspace activation."""

from __future__ import annotations

import hashlib
import importlib.resources
import json
import logging
import os
import shutil
import sqlite3
import tempfile
import uuid
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from yoyo import get_backend, read_migrations

from nightcrate.catalog_loader import load_catalogs
from nightcrate.catalog_loader.registry import user_catalogs_root
from nightcrate.core.app_config import workspace_db_path
from nightcrate.db.durable_fs import durable_remove, durable_write, fsync_dir
from nightcrate.db.migrations import MIGRATIONS_DIR
from nightcrate.seed_loader import load_all

WORKSPACE_FILE = "nightcrate-workspace.json"
BACKUP_DIR = "backups"
KEEP_BACKUPS = 3
MARKER_FILE = "upgrade-in-progress.json"

logger = logging.getLogger("nightcrate.db.workspace_upgrade")

ProblemKind = Literal["newer", "unreadable", "backup_failed", "upgrade_failed", "restore_failed"]


@dataclass(frozen=True)
class WorkspaceProblem:
    kind: ProblemKind
    workspace_path: str
    workspace_name: str
    last_opened_by: str | None
    error: str | None
    backup_path: str | None


class WorkspaceRefused(Exception):
    def __init__(self, problem: WorkspaceProblem):
        super().__init__(problem.kind)
        self.problem = problem


class RestoreError(RuntimeError):
    pass


@dataclass(frozen=True)
class ActivationResult:
    backup_path: Path | None
    migrations_applied: int


def _error(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


def _workspace_problem(
    kind: ProblemKind,
    workspace: Path,
    name: str,
    *,
    error: str | None = None,
    backup: Path | None = None,
) -> WorkspaceProblem:
    return WorkspaceProblem(
        kind=kind,
        workspace_path=str(workspace),
        workspace_name=name,
        last_opened_by=read_last_opened_by(workspace),
        error=error,
        backup_path=str(backup) if backup is not None else None,
    )


def read_applied_hashes(db_path: Path) -> list[str] | None:
    """Read yoyo metadata without allowing yoyo to initialise the database."""
    try:
        if not db_path.is_file() or db_path.stat().st_size == 0:
            return []
        uri = f"file:{quote(db_path.resolve().as_posix(), safe='/')}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as conn:
            table = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='_yoyo_migration'"
            ).fetchone()
            if table is None:
                return []
            rows = conn.execute("SELECT migration_hash FROM _yoyo_migration").fetchall()
        if any(len(row) != 1 or not isinstance(row[0], str) for row in rows):
            return None
        return [row[0] for row in rows]
    except OSError, sqlite3.DatabaseError:
        return None


def known_hashes() -> set[str]:
    return {migration.hash for migration in read_migrations(str(MIGRATIONS_DIR))}


def _workspace_data(workspace: Path) -> dict[str, object]:
    try:
        value = json.loads((workspace / WORKSPACE_FILE).read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except OSError, json.JSONDecodeError:
        return {}


def read_last_opened_by(workspace: Path) -> str | None:
    value = _workspace_data(workspace).get("last_opened_by")
    return value if isinstance(value, str) else None


def record_opened_by(
    workspace: Path, version: str, *, completed_upgrade: str | None = None
) -> None:
    durable_write(
        workspace / WORKSPACE_FILE,
        json.dumps(
            {"last_opened_by": version, "completed_upgrade": completed_upgrade},
            separators=(",", ":"),
        ).encode(),
    )


def _ensure_backup_dir(workspace: Path) -> Path:
    folder = workspace / BACKUP_DIR
    if not folder.exists():
        folder.mkdir(parents=True)
        fsync_dir(workspace)
    return folder


def backup_database(
    db_path: Path, version: str, now: datetime, *, workspace: Path | None = None
) -> Path:
    folder = _ensure_backup_dir(workspace or db_path.parent)
    stem = f"nightcrate-before-{version}-{now.strftime('%Y-%m-%d-%H%M%S')}"
    destination = folder / f"{stem}.db"
    suffix = 2
    while destination.exists():
        destination = folder / f"{stem}-{suffix}.db"
        suffix += 1
    fd, temp_name = tempfile.mkstemp(prefix=".backup-", suffix=".db", dir=folder)
    os.close(fd)
    temp = Path(temp_name)
    try:
        with (
            closing(sqlite3.connect(db_path)) as source,
            closing(sqlite3.connect(temp)) as target,
        ):
            source.backup(target)
        with temp.open("rb") as stream:
            os.fsync(stream.fileno())
        os.replace(temp, destination)
        fsync_dir(folder)
        logger.info("[workspace] backed up %s to %s", db_path.name, destination)
        return destination
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


def prune_backups(workspace: Path, keep: Path | None) -> None:
    folder = workspace / BACKUP_DIR
    if not folder.is_dir():
        return
    protected = {keep} if keep is not None else set()
    try:
        marker = json.loads((folder / MARKER_FILE).read_text(encoding="utf-8"))
        marker_name = marker.get("backup")
        if isinstance(marker_name, str):
            protected.add(folder / marker_name)
    except OSError, json.JSONDecodeError, AttributeError:
        pass
    backups = sorted(
        folder.glob("nightcrate-before-*.db"),
        key=lambda path: (path.stat().st_mtime_ns, path.name),
        reverse=True,
    )
    retained = set(backups[:KEEP_BACKUPS])
    retained.update(protected)
    for path in backups:
        if path not in retained:
            durable_remove(path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def restore_backup(backup: Path, db_path: Path) -> None:
    # A fixed name lets a retry overwrite the exact temporary file left by a
    # process killed between the journal cleanup and atomic replace.
    temp = db_path.with_name(f".{db_path.name}.restore")
    try:
        shutil.copyfile(backup, temp)
        with temp.open("rb") as stream:
            os.fsync(stream.fileno())
        for suffix in ("-journal", "-wal", "-shm"):
            try:
                Path(f"{db_path}{suffix}").unlink()
            except FileNotFoundError:
                pass
        os.replace(temp, db_path)
        fsync_dir(db_path.parent)
        if _sha256(db_path) != _sha256(backup):
            raise RestoreError("restored database does not match its backup")
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


def _read_marker(workspace: Path) -> dict[str, object] | None:
    path = workspace / BACKUP_DIR / MARKER_FILE
    if not path.is_file():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("upgrade marker is not an object")
    required = {"id", "backup", "from_version", "to_version", "state", "started_at"}
    if not required.issubset(value):
        raise ValueError("upgrade marker is missing fields")
    if not isinstance(value["id"], str) or not value["id"]:
        raise ValueError("upgrade marker has an invalid id")
    if not isinstance(value["backup"], str) or Path(value["backup"]).name != value["backup"]:
        raise ValueError("upgrade marker has an invalid backup")
    if value["state"] not in ("upgrading", "restore_failed"):
        raise ValueError("upgrade marker has an invalid state")
    return value


def _write_marker(workspace: Path, marker: dict[str, object]) -> None:
    durable_write(
        workspace / BACKUP_DIR / MARKER_FILE,
        json.dumps(marker, separators=(",", ":")).encode(),
    )


def _remove_marker(workspace: Path) -> None:
    durable_remove(workspace / BACKUP_DIR / MARKER_FILE)


def apply_migrations(db_path: Path) -> None:
    with get_backend(f"sqlite:///{db_path}") as backend:
        migrations = read_migrations(str(MIGRATIONS_DIR))
        with backend.lock():
            backend.apply_migrations(backend.to_apply(migrations))


def _load_seed_and_catalogs(db_path: Path) -> None:
    csv_root = importlib.resources.files("nightcrate") / "data" / "seed"
    try:
        with closing(sqlite3.connect(db_path)) as conn:
            with conn:
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA foreign_keys = ON")
                load_all(conn, csv_root, "auto")
    except sqlite3.Error, OSError, ValueError:
        logger.warning("Seed loader failed", exc_info=True)
    try:
        with closing(sqlite3.connect(db_path)) as conn:
            with conn:
                conn.execute("PRAGMA foreign_keys = ON")
                load_catalogs(conn, user_catalogs_root())
    except sqlite3.Error, OSError, ValueError:
        logger.warning("DSO catalog loader failed", exc_info=True)


def initialize_workspace(
    workspace: Path,
    name: str,
    app_version: str,
    *,
    on_step: Callable[[str], None] = lambda _step: None,
    now: datetime | None = None,
) -> ActivationResult:
    """Activate a workspace in the durability order defined by the release plan."""
    workspace.mkdir(parents=True, exist_ok=True)
    logical_db_path = workspace_db_path(workspace)
    db_path = logical_db_path.resolve()
    marker_path = workspace / BACKUP_DIR / MARKER_FILE
    current_time = now or datetime.now()
    recovery_backup: Path | None = None
    marker: dict[str, object] | None = None

    # Step 0: classify the marker without touching SQLite.
    try:
        marker = _read_marker(workspace)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise WorkspaceRefused(
            _workspace_problem("unreadable", workspace, name, error=_error(exc))
        ) from exc

    try:
        has_other_hard_links = db_path.is_file() and db_path.stat().st_nlink > 1
    except OSError as exc:
        raise WorkspaceRefused(
            _workspace_problem("unreadable", workspace, name, error=_error(exc))
        ) from exc
    if has_other_hard_links:
        raise WorkspaceRefused(
            _workspace_problem(
                "unreadable",
                workspace,
                name,
                error=(
                    "nightcrate.db has other hard links, so NightCrate can't upgrade it safely. "
                    "Copy it to a new file, then reopen the workspace."
                ),
            )
        )
    if marker is not None:
        completed = _workspace_data(workspace).get("completed_upgrade")
        if completed == marker["id"]:
            _remove_marker(workspace)
            marker = None
        else:
            recovery_backup = workspace / BACKUP_DIR / str(marker["backup"])
            try:
                restore_backup(recovery_backup, db_path)
                marker["state"] = "upgrading"
                _write_marker(workspace, marker)
            except Exception as exc:
                marker["state"] = "restore_failed"
                try:
                    _write_marker(workspace, marker)
                except Exception:
                    logger.exception("Failed to record restore failure")
                raise WorkspaceRefused(
                    _workspace_problem(
                        "restore_failed",
                        workspace,
                        name,
                        error=_error(exc),
                        backup=recovery_backup,
                    )
                ) from exc

    existed = db_path.is_file()

    # Step 1: allow SQLite to recover its own journal before the read-only probe.
    if existed and any(Path(f"{db_path}{suffix}").exists() for suffix in ("-journal", "-wal")):
        try:
            with closing(sqlite3.connect(db_path)) as conn:
                conn.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchone()
        except (OSError, sqlite3.Error) as exc:
            raise WorkspaceRefused(
                _workspace_problem("unreadable", workspace, name, error=_error(exc))
            ) from exc

    # Step 2: refuse unknown or unreadable migration metadata.
    applied = read_applied_hashes(db_path)
    if applied is None:
        raise WorkspaceRefused(_workspace_problem("unreadable", workspace, name))
    known = known_hashes()
    if any(item not in known for item in applied):
        raise WorkspaceRefused(_workspace_problem("newer", workspace, name))
    pending_count = len(known.difference(applied))

    # Step 3: establish a recovery point before migrations.
    backup = recovery_backup
    if (
        backup is None
        and existed
        and (pending_count > 0 or read_last_opened_by(workspace) != app_version)
    ):
        on_step("backing_up")
        try:
            backup = backup_database(db_path, app_version, current_time, workspace=workspace)
            prune_backups(workspace, backup)
            if pending_count:
                marker = {
                    "id": uuid.uuid4().hex,
                    "backup": backup.name,
                    "from_version": read_last_opened_by(workspace),
                    "to_version": app_version,
                    "state": "upgrading",
                    "started_at": current_time.isoformat(),
                }
                _write_marker(workspace, marker)
        except Exception as exc:
            if marker_path.exists():
                try:
                    _remove_marker(workspace)
                except Exception:
                    logger.exception("Failed to remove an unpublished upgrade marker")
            raise WorkspaceRefused(
                _workspace_problem(
                    "backup_failed", workspace, name, error=_error(exc), backup=backup
                )
            ) from exc

    # Step 4: migrate, restoring the established recovery point on failure.
    if pending_count:
        on_step("upgrading")
        try:
            apply_migrations(db_path)
        except Exception as migration_exc:
            if backup is None:
                raise
            try:
                restore_backup(backup, db_path)
                _remove_marker(workspace)
            except Exception as restore_exc:
                if marker is not None:
                    marker["state"] = "restore_failed"
                    try:
                        _write_marker(workspace, marker)
                    except Exception:
                        logger.exception("Failed to record restore failure")
                combined = f"{_error(migration_exc)}; restore: {_error(restore_exc)}"
                raise WorkspaceRefused(
                    _workspace_problem(
                        "restore_failed", workspace, name, error=combined, backup=backup
                    )
                ) from restore_exc
            raise WorkspaceRefused(
                _workspace_problem(
                    "upgrade_failed",
                    workspace,
                    name,
                    error=_error(migration_exc),
                    backup=backup,
                )
            ) from migration_exc

    # Step 5: non-critical seed and catalog reconciliation.
    _load_seed_and_catalogs(db_path)

    # Step 6: publish completion before removing the recovery marker.
    marker_id = str(marker["id"]) if marker is not None else None
    record_opened_by(workspace, app_version, completed_upgrade=marker_id)
    _remove_marker(workspace)
    return ActivationResult(backup_path=backup, migrations_applied=pending_count)
