"""App-wide optional-catalog selection stored beside downloaded catalogs."""

from __future__ import annotations

import json
import logging
import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from nightcrate.catalog_loader import registry

logger = logging.getLogger("nightcrate.catalog_loader.catalog_choice")


@dataclass(frozen=True, slots=True)
class CatalogChoice:
    chosen: frozenset[str]
    removed: frozenset[str]


def read_choice(catalogs_root: Path) -> CatalogChoice | None:
    """Read ``choice.json``; invalid or missing files leave the choice unknown."""
    path = catalogs_root / "choice.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("version") != 1:
            raise ValueError("unsupported choice format")
        chosen_raw = payload.get("chosen")
        removed_raw = payload.get("removed")
        if not isinstance(chosen_raw, list) or not all(
            isinstance(item, str) for item in chosen_raw
        ):
            raise ValueError("chosen must be a list of strings")
        if not isinstance(removed_raw, list) or not all(
            isinstance(item, str) for item in removed_raw
        ):
            raise ValueError("removed must be a list of strings")
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        logger.warning("[catalog_choice] ignoring invalid %s: %s", path, exc)
        return None

    known = {catalog.catalog_id for catalog in registry.OPTIONAL_CATALOGS}
    chosen = frozenset(chosen_raw) & known
    removed = (frozenset(removed_raw) & known) - chosen
    return CatalogChoice(chosen=chosen, removed=removed)


def write_choice(catalogs_root: Path, choice: CatalogChoice) -> None:
    """Atomically replace ``choice.json`` without risking its prior contents."""
    catalogs_root.mkdir(parents=True, exist_ok=True)
    path = catalogs_root / "choice.json"
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o644
    payload = {
        "version": 1,
        "chosen": sorted(choice.chosen),
        "removed": sorted(choice.removed - choice.chosen),
    }
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=catalogs_root, prefix=".choice-", delete=False
        ) as stream:
            temporary = Path(stream.name)
            json.dump(payload, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def with_added(choice: CatalogChoice | None, catalog_id: str) -> CatalogChoice:
    """Return a choice that explicitly enables *catalog_id*."""
    current = choice or CatalogChoice(frozenset(), frozenset())
    return CatalogChoice(
        chosen=current.chosen | {catalog_id},
        removed=current.removed - {catalog_id},
    )


def with_removed(choice: CatalogChoice | None, catalog_id: str) -> CatalogChoice:
    """Return a choice that explicitly removes *catalog_id*."""
    current = choice or CatalogChoice(frozenset(), frozenset())
    return CatalogChoice(
        chosen=current.chosen - {catalog_id},
        removed=current.removed | {catalog_id},
    )


def effective_state(
    choice: CatalogChoice | None,
    catalog: registry.OptionalCatalog,
    applied: str | None,
) -> Literal["on", "off", "removed"]:
    """Resolve one database's safe effective state for an optional catalog."""
    if choice is not None and catalog.catalog_id in choice.chosen:
        return "on"
    if choice is not None and catalog.catalog_id in choice.removed:
        return "removed"
    if applied in {"on", "removed"}:
        return applied
    return "on" if catalog.legacy_default else "off"
