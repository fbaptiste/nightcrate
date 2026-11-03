"""App-wide optional-catalog choice file tests."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from nightcrate.catalog_loader import registry
from nightcrate.catalog_loader.catalog_choice import (
    CatalogChoice,
    effective_state,
    read_choice,
    with_added,
    with_removed,
    write_choice,
)


def _new_catalog(catalog_id: str = "new") -> registry.OptionalCatalog:
    return registry.OptionalCatalog(
        catalog_id=catalog_id,
        display_name="New",
        source_ids=("new_source",),
        kind="nightcrate",
        fetch_specs=(),
        designation_catalogs=frozenset({catalog_id}),
        legacy_default=False,
        credit="test",
    )


def test_no_choice_file_is_todays_behaviour(tmp_path: Path):
    assert read_choice(tmp_path) is None
    sharpless = registry.optional_catalog("sharpless")
    assert sharpless is not None
    assert effective_state(None, sharpless, None) == "on"


def test_invalid_choice_file_is_ignored_and_kept(tmp_path: Path, caplog):
    path = tmp_path / "choice.json"
    path.write_text("not json", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        assert read_choice(tmp_path) is None
    assert path.read_text(encoding="utf-8") == "not json"
    assert "ignoring invalid" in caplog.text


def test_unknown_ids_dropped(tmp_path: Path, monkeypatch):
    catalog = _new_catalog()
    monkeypatch.setattr(registry, "OPTIONAL_CATALOGS", (catalog,))
    (tmp_path / "choice.json").write_text(
        json.dumps({"version": 1, "chosen": ["new", "unknown"], "removed": ["gone", "new"]}),
        encoding="utf-8",
    )
    assert read_choice(tmp_path) == CatalogChoice(frozenset({"new"}), frozenset())


def test_write_failure_keeps_previous_file(tmp_path: Path, monkeypatch):
    old = CatalogChoice(frozenset({"sharpless"}), frozenset())
    write_choice(tmp_path, old)

    def fail_replace(_source, _destination):
        raise OSError("replace failed")

    monkeypatch.setattr("nightcrate.catalog_loader.catalog_choice.os.replace", fail_replace)
    with pytest.raises(OSError, match="replace failed"):
        write_choice(tmp_path, with_removed(old, "sharpless"))
    assert read_choice(tmp_path) == old


@pytest.mark.parametrize("legacy_default", [False, True])
def test_effective_state(legacy_default: bool):
    catalog = _new_catalog()
    catalog = registry.OptionalCatalog(
        **{
            field: getattr(catalog, field)
            for field in (
                "catalog_id",
                "display_name",
                "source_ids",
                "kind",
                "fetch_specs",
                "designation_catalogs",
                "credit",
            )
        },
        legacy_default=legacy_default,
    )
    neither = CatalogChoice(frozenset(), frozenset())
    chosen = with_added(neither, catalog.catalog_id)
    removed = with_removed(neither, catalog.catalog_id)

    assert effective_state(None, catalog, None) == ("on" if legacy_default else "off")
    assert effective_state(neither, catalog, None) == ("on" if legacy_default else "off")
    assert effective_state(chosen, catalog, None) == "on"
    assert effective_state(removed, catalog, None) == "removed"
    assert effective_state(None, catalog, "on") == "on"
    assert effective_state(None, catalog, "removed") == "removed"
    assert effective_state(neither, catalog, "on") == "on"
    assert effective_state(neither, catalog, "removed") == "removed"
    assert effective_state(chosen, catalog, "removed") == "on"
    assert effective_state(removed, catalog, "on") == "removed"
