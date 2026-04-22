"""Admin API endpoints — database management, status, and app info."""

import importlib.resources
import sqlite3
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from nightcrate.core.app_config import (
    APP_DIR,
    CONFIG_PATH,
    DatabaseEntry,
    load_config,
    save_config,
)
from nightcrate.db.migrations import apply_migrations
from nightcrate.db.session import get_db_path, set_db_path
from nightcrate.seed_loader import load_all

router = APIRouter(prefix="/api/admin", tags=["Administration"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class CreateDatabaseRequest(BaseModel):
    path: str
    name: str


class ActivateDatabaseRequest(BaseModel):
    path: str


class RemoveDatabaseRequest(BaseModel):
    path: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _db_size(path: str) -> int | None:
    """Return file size in bytes, or None if the file doesn't exist."""
    p = Path(path)
    if p.is_file():
        return p.stat().st_size
    return None


def _initialize_database(db_path: Path) -> None:
    """Run migrations, the equipment seed loader, and the DSO catalog
    loader on a database.

    The catalog loader is a no-op when the user's
    ``APP_DIR/catalogs/`` tree is empty — no files, nothing to load,
    no error. When catalog files DO exist locally (a common case
    after the user creates a second database on a machine that
    already fetched OpenNGC / Sharpless / Barnard / 50 MGC for a
    prior database) the new DB gets populated automatically, no
    manual "Reload from local cache" click required.
    """
    from nightcrate.catalog_loader import load_catalogs
    from nightcrate.catalog_loader.registry import user_catalogs_root

    apply_migrations(db_path=db_path)

    csv_root = importlib.resources.files("nightcrate") / "data" / "seed"
    sync_conn = sqlite3.connect(str(db_path))
    try:
        sync_conn.row_factory = sqlite3.Row
        sync_conn.execute("PRAGMA foreign_keys = ON")
        load_all(sync_conn, csv_root, "auto")
        sync_conn.commit()
        load_catalogs(sync_conn, user_catalogs_root())
    finally:
        sync_conn.close()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/info")
async def admin_info() -> dict:
    """Return read-only application info."""
    return {
        "config_file": str(CONFIG_PATH),
        "app_data_dir": str(APP_DIR),
        "backend_root": str(Path(__file__).resolve().parents[1]),
        "seed_data_dir": str(importlib.resources.files("nightcrate") / "data" / "seed"),
        "python_version": sys.version.split()[0],
    }


@router.get("/status")
async def admin_status() -> dict:
    """Return database configuration status."""
    config = load_config()

    active_db_info = None
    if config.active_db is not None:
        size = _db_size(config.active_db)
        available = size is not None
        active_db_info = {
            "path": config.active_db,
            "name": config.databases.get(config.active_db, DatabaseEntry(name="")).name,
            "available": available,
            "size_bytes": size,
        }

    known_databases = []
    for path, entry in config.databases.items():
        size = _db_size(path)
        known_databases.append(
            {
                "path": path,
                "name": entry.name,
                "available": size is not None,
                "size_bytes": size,
            }
        )

    return {
        "db_configured": config.db_configured,
        "active_db": active_db_info,
        "known_databases": known_databases,
    }


@router.post("/database/create")
async def create_database(req: CreateDatabaseRequest) -> dict:
    """Create a new database at the given path without activating it."""
    db_path = Path(req.path)

    if db_path.exists():
        raise HTTPException(status_code=400, detail=f"Path already exists: {req.path}")

    # Ensure parent directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)

    _initialize_database(db_path)

    config = load_config()
    config.databases[req.path] = DatabaseEntry(name=req.name)
    save_config(config)

    return {
        "path": req.path,
        "name": req.name,
        "size_bytes": _db_size(req.path),
        "available": True,
    }


@router.post("/database/add")
async def add_existing_database(req: CreateDatabaseRequest) -> dict:
    """Register an existing database file in the config without creating it."""
    db_path = Path(req.path)

    if not db_path.is_file():
        raise HTTPException(status_code=400, detail=f"File does not exist: {req.path}")

    if not req.path.endswith(".db"):
        raise HTTPException(status_code=400, detail="File must have a .db extension")

    config = load_config()
    if req.path in config.databases:
        raise HTTPException(status_code=409, detail=f"Database already registered: {req.path}")

    config.databases[req.path] = DatabaseEntry(name=req.name)
    save_config(config)

    return {
        "path": req.path,
        "name": req.name,
        "size_bytes": _db_size(req.path),
        "available": True,
    }


@router.post("/database/activate")
async def activate_database(req: ActivateDatabaseRequest) -> dict:
    """Activate a known database, running migrations and seed loader first."""
    config = load_config()

    if req.path not in config.databases:
        raise HTTPException(status_code=400, detail=f"Path not in known databases: {req.path}")

    db_path = Path(req.path)
    if not db_path.is_file():
        raise HTTPException(status_code=400, detail=f"Database file does not exist: {req.path}")

    _initialize_database(db_path)

    config.active_db = req.path
    save_config(config)

    # Hot-swap the runtime database path
    set_db_path(db_path)

    entry = config.databases[req.path]
    size = _db_size(req.path)
    return {
        "path": req.path,
        "name": entry.name,
        "available": True,
        "size_bytes": size,
    }


@router.post("/database/setup")
async def setup_database(req: CreateDatabaseRequest) -> dict:
    """First-run setup: create, migrate, seed, and activate a new database.

    Returns 409 if a database is already configured.
    """
    config = load_config()
    if config.db_configured:
        raise HTTPException(
            status_code=409, detail="A database is already configured. Use activate instead."
        )

    db_path = Path(req.path)

    if db_path.exists():
        raise HTTPException(status_code=400, detail=f"Path already exists: {req.path}")

    db_path.parent.mkdir(parents=True, exist_ok=True)

    _initialize_database(db_path)

    config = load_config()
    config.databases[req.path] = DatabaseEntry(name=req.name)
    config.active_db = req.path
    save_config(config)

    # Hot-swap the runtime database path
    set_db_path(db_path)

    return {
        "path": req.path,
        "name": req.name,
        "size_bytes": _db_size(req.path),
        "available": True,
    }


@router.delete("/database")
async def remove_database(
    req: RemoveDatabaseRequest,
    delete_file: bool = Query(False, description="Also delete the database file from disk"),
) -> dict:
    """Remove a database from the known list, optionally deleting the file."""
    config = load_config()

    if config.active_db == req.path:
        raise HTTPException(
            status_code=400, detail="Cannot remove the active database. Activate another first."
        )

    if req.path not in config.databases:
        raise HTTPException(status_code=400, detail=f"Path not in known databases: {req.path}")

    del config.databases[req.path]
    save_config(config)

    if delete_file:
        db_path = Path(req.path)
        if db_path.is_file():
            db_path.unlink()

    return {"ok": True}


@router.get("/browse")
async def browse_filesystem(path: str = Query(default="~")) -> dict:
    """List directories and .db files at the given filesystem path."""
    resolved = Path(path).expanduser().resolve()

    if not resolved.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {path}")

    dirs = []
    files = []

    try:
        for entry in sorted(resolved.iterdir(), key=lambda e: e.name.lower()):
            if entry.name.startswith("."):
                continue
            if entry.is_dir():
                dirs.append({"name": entry.name, "path": str(entry)})
            elif entry.is_file() and entry.suffix.lower() == ".db":
                files.append(
                    {
                        "name": entry.name,
                        "path": str(entry),
                        "size": entry.stat().st_size,
                    }
                )
    except PermissionError:
        pass  # Return whatever we managed to collect

    return {"path": str(resolved), "dirs": dirs, "files": files}


@router.get("/shortcuts")
async def filesystem_shortcuts() -> dict:
    """Return common filesystem shortcut paths."""
    home = Path.home()
    docs = home / "Documents"
    return {
        "home": str(home),
        "documents": str(docs) if docs.is_dir() else str(home),
        "app_data": str(APP_DIR),
    }


class CreateFolderRequest(BaseModel):
    path: str


@router.post("/mkdir")
async def create_folder(req: CreateFolderRequest) -> dict:
    """Create a new directory at the given path."""
    target = Path(req.path)
    if target.exists():
        raise HTTPException(status_code=409, detail=f"Already exists: {req.path}")
    try:
        target.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"path": str(target.resolve())}


@router.post("/reseed")
async def reseed_equipment() -> dict:
    """Re-run the seed loader on the active database.

    Inserts new seed rows, updates unchanged seed rows with new CSV data,
    and skips user-modified rows. Returns a summary of what changed.
    """
    config = load_config()
    if not config.db_configured:
        raise HTTPException(status_code=400, detail="No database is configured")

    db_path = get_db_path()
    csv_root = importlib.resources.files("nightcrate") / "data" / "seed"

    sync_conn = sqlite3.connect(str(db_path))
    try:
        sync_conn.row_factory = sqlite3.Row
        sync_conn.execute("PRAGMA foreign_keys = ON")
        report = load_all(sync_conn, csv_root, "update")
        sync_conn.commit()
    finally:
        sync_conn.close()

    # Build summary
    summary = {
        "mode": report.mode,
        "ok": report.ok,
        "tables": {},
    }
    total_inserted = 0
    total_updated = 0
    total_unchanged = 0
    total_skipped = 0
    for table_name, tr in report.per_table.items():
        total_inserted += tr.inserted
        total_updated += tr.updated
        total_unchanged += tr.unchanged
        total_skipped += len(tr.skipped_user_modified)
        if tr.inserted or tr.updated or tr.skipped_user_modified or tr.orphaned:
            summary["tables"][table_name] = {
                "inserted": tr.inserted,
                "updated": tr.updated,
                "unchanged": tr.unchanged,
                "skipped_user_modified": tr.skipped_user_modified,
                "orphaned": tr.orphaned,
            }
    summary["total_inserted"] = total_inserted
    summary["total_updated"] = total_updated
    summary["total_unchanged"] = total_unchanged
    summary["total_skipped"] = total_skipped

    return summary


def _summary_to_dict(summary) -> dict:
    return {
        "total_dsos": summary.total_dsos,
        "total_designations": summary.total_designations,
        "per_source": [
            {
                "source_id": r.source_id,
                "status": r.status,
                "dso_count": r.dso_count,
                "designation_count": r.designation_count,
                "unresolved_duplicates": r.unresolved_duplicates,
                "error": r.error,
            }
            for r in summary.results
        ],
    }


def _run_loader(force: bool):
    """Shared helper: open a sync sqlite3 connection against the active DB
    and run the catalog loader against the user-writable catalogs dir.
    """
    from nightcrate.catalog_loader import load_catalogs
    from nightcrate.catalog_loader.registry import user_catalogs_root

    config = load_config()
    if not config.db_configured:
        raise HTTPException(status_code=400, detail="No database is configured")

    db_path = get_db_path()
    sync_conn = sqlite3.connect(str(db_path))
    try:
        sync_conn.execute("PRAGMA foreign_keys = ON")
        return load_catalogs(sync_conn, user_catalogs_root(), force=force)
    finally:
        sync_conn.close()


@router.post("/catalogs/reload")
async def reload_catalogs(force: bool = Query(True)) -> dict:
    """Re-parse the local catalog cache without re-downloading.

    For when the user wants the loader to re-read already-downloaded files
    (e.g., after a schema tweak). Does NOT reach out to GitHub; use
    ``POST /catalogs/fetch-from-github`` for that.
    """
    summary = _run_loader(force=force)
    return _summary_to_dict(summary)


@router.get("/catalogs/remote-version")
async def remote_catalog_version() -> dict:
    """Return the latest OpenNGC release tag available on GitHub alongside
    the locally-installed version (if any) for comparison.
    """
    from nightcrate.catalog_loader import remote
    from nightcrate.catalog_loader.registry import read_installed_version, user_catalogs_root

    installed = read_installed_version(user_catalogs_root())
    try:
        release = await remote.fetch_latest_release()
    except Exception as exc:  # noqa: BLE001 — surface as 502 with a clear reason
        raise HTTPException(
            status_code=502,
            detail=f"Could not reach GitHub: {exc}",
        ) from exc

    return {
        "latest_tag": release.tag_name,
        "latest_published_at": release.published_at,
        "release_url": release.release_url,
        "installed_version": installed,
        "has_update": installed is None or installed != release.tag_name,
    }


@router.post("/catalogs/fetch-from-github")
async def fetch_catalogs_from_github() -> dict:
    """Download the latest OpenNGC release from GitHub into the user's
    catalogs dir and then run the loader. Returns the load summary plus
    the fetched release tag.
    """
    from nightcrate.catalog_loader import remote
    from nightcrate.catalog_loader.registry import user_catalogs_root

    config = load_config()
    if not config.db_configured:
        raise HTTPException(status_code=400, detail="No database is configured")

    try:
        release = await remote.fetch_latest_release()
        await remote.download_openngc(release, user_catalogs_root())
    except Exception as exc:  # noqa: BLE001 — surface as 502 with a clear reason
        raise HTTPException(
            status_code=502,
            detail=f"Failed to download catalog from GitHub: {exc}",
        ) from exc

    summary = _run_loader(force=True)
    return {
        "fetched_version": release.tag_name,
        **_summary_to_dict(summary),
    }


# ---------------------------------------------------------------------------
# VizieR per-source fetch endpoints (v0.15.0)
# ---------------------------------------------------------------------------


_VIZIER_FETCH_SPECS: dict[str, dict] = {
    "sharpless": {
        "source_id": "vizier_sharpless",
        "catalog_id": "VII/20/catalog",
        "output_filename": "sharpless_VII_20.tsv",
        "display_name": "Sharpless 2 (VII/20)",
        "citation": "Sharpless 1959 ApJS 4, 257. Retrieved via VizieR.",
        "column_filter": None,
        # VizieR precession pseudo-columns are only emitted on explicit
        # -out.add; without this, `-out.all` returns only the original
        # epoch columns (RA1900/DE1900 for Sharpless, RA1875/DE1875 for
        # Barnard) and every row ingests with ra_deg/dec_deg = NULL.
        "additional_params": {"-out.add": "_RAJ2000,_DEJ2000"},
    },
    "barnard": {
        "source_id": "vizier_barnard",
        "catalog_id": "VII/220A/barnard",
        "output_filename": "barnard_VII_220.tsv",
        "display_name": "Barnard dark nebulae (VII/220A)",
        "citation": "Barnard 1927 (VizieR VII/220A).",
        "column_filter": None,
        "additional_params": {"-out.add": "_RAJ2000,_DEJ2000"},
    },
    # 50 MGC moved to a dedicated GitHub fetch endpoint
    # (POST /api/admin/catalogs/50mgc/fetch) — see fetch_50mgc_from_github
    # below. The data origin is still VizieR J/AJ/167/31 but the fetch
    # path is the author's GitHub mirror for reliability.
}


def _build_vizier_spec(short_id: str):
    from nightcrate.catalog_loader.vizier import VizierFetchSpec

    cfg = _VIZIER_FETCH_SPECS.get(short_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail=f"Unknown VizieR source: {short_id}")
    return VizierFetchSpec(
        source_id=cfg["source_id"],
        catalog_id=cfg["catalog_id"],
        output_filename=cfg["output_filename"],
        display_name=cfg["display_name"],
        citation=cfg["citation"],
        column_filter=cfg["column_filter"],
        additional_params=cfg["additional_params"],
    )


@router.get("/catalogs/vizier/{source_id}/remote-version")
async def vizier_remote_version(source_id: str) -> dict:
    """Return the installed version for a VizieR source plus a pointer to
    the upstream catalog. VizieR doesn't expose release tags the way GitHub
    does, so ``latest_tag`` is always the fixed catalog ID — the ``fetch_date``
    of the installed copy is what tells the user whether they might want to
    re-fetch.
    """
    from nightcrate.catalog_loader.registry import user_catalogs_root
    from nightcrate.catalog_loader.vizier import read_installed_version

    spec = _build_vizier_spec(source_id)
    installed_files = read_installed_version(user_catalogs_root())
    entry = installed_files.get(spec.output_filename)

    return {
        "source_id": spec.source_id,
        "catalog_id": spec.catalog_id,
        "display_name": spec.display_name,
        "latest_tag": spec.catalog_id,
        "installed_version": entry.get("fetch_date") if entry else None,
        "release_url": f"https://vizier.cds.unistra.fr/viz-bin/VizieR?-source={spec.catalog_id}",
        # "Update available" reduces to "has never been fetched" for VizieR —
        # the frontend can still call ``fetch`` to re-pull the latest data.
        "has_update": entry is None,
    }


@router.post("/catalogs/vizier/{source_id}/fetch")
async def vizier_fetch(source_id: str) -> dict:
    """Download a VizieR source TSV atomically and run the loader."""
    from nightcrate.catalog_loader.registry import user_catalogs_root
    from nightcrate.catalog_loader.vizier import fetch_vizier_catalog

    config = load_config()
    if not config.db_configured:
        raise HTTPException(status_code=400, detail="No database is configured")

    spec = _build_vizier_spec(source_id)
    try:
        result = await fetch_vizier_catalog(spec, user_catalogs_root())
    except Exception as exc:  # noqa: BLE001 — surface 502 with reason
        raise HTTPException(
            status_code=502,
            detail=f"Failed to download {spec.display_name} from VizieR: {exc}",
        ) from exc

    summary = _run_loader(force=True)
    return {
        "source_id": spec.source_id,
        "fetched_at": result.fetched_at,
        "size_bytes": result.size_bytes,
        **_summary_to_dict(summary),
    }


@router.post("/catalogs/nightcrate/reload")
async def reload_nightcrate_catalogs() -> dict:
    """Re-read the vendored NightCrate CSVs (augment + crossref files) and
    re-run the loader so edits to those files take effect without restarting
    the app.
    """
    summary = _run_loader(force=True)
    return _summary_to_dict(summary)


# ---------------------------------------------------------------------------
# 50 MGC (GitHub fetch, not VizieR) — v0.15.0
# ---------------------------------------------------------------------------


@router.get("/catalogs/50mgc/remote-version")
async def mgc50_remote_version() -> dict:
    """Status of the 50 MGC fetch: whether the file has been downloaded
    and when.

    GitHub raw-content endpoints don't expose a meaningful "latest tag"
    for the 50 MGC repo (it's a single ``main`` branch with an
    occasionally-updated ``catalog.fits``). So the UI just reports an
    installed timestamp if present; clicking Fetch re-downloads.
    """
    from nightcrate.catalog_loader.mgc50_fetch import (
        MGC50_RAW_URL,
        MGC50_REPO_URL,
        read_installed_fetch,
    )
    from nightcrate.catalog_loader.registry import user_catalogs_root

    installed = read_installed_fetch(user_catalogs_root())
    return {
        "source_id": "github_50mgc",
        "display_name": "50 Mpc Galaxy Catalog (Ohlson+ 2024)",
        "repository_url": MGC50_REPO_URL,
        "raw_url": MGC50_RAW_URL,
        "installed_fetched_at": installed.get("fetched_at"),
        "installed_sha256": installed.get("sha256"),
        # There's no "update available" semantic here — GitHub raw URLs don't
        # carry tag metadata for this repo. The user re-fetches when they
        # feel like it.
        "has_update": installed.get("fetched_at") is None,
    }


@router.post("/catalogs/50mgc/fetch")
async def mgc50_fetch() -> dict:
    """Download ``catalog.fits`` from the 50 MGC GitHub mirror atomically
    and run the loader.
    """
    from nightcrate.catalog_loader.mgc50_fetch import fetch_50mgc_from_github
    from nightcrate.catalog_loader.registry import user_catalogs_root

    config = load_config()
    if not config.db_configured:
        raise HTTPException(status_code=400, detail="No database is configured")

    try:
        result = await fetch_50mgc_from_github(user_catalogs_root())
    except Exception as exc:  # noqa: BLE001 — surface 502 with reason
        raise HTTPException(
            status_code=502,
            detail=f"Failed to download 50 MGC from GitHub: {exc}",
        ) from exc

    summary = _run_loader(force=True)
    return {
        "source_id": "github_50mgc",
        "fetched_at": result.fetched_at,
        "size_bytes": result.size_bytes,
        "sha256": result.sha256,
        **_summary_to_dict(summary),
    }
