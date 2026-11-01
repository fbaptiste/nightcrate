from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from .store import star_root


@dataclass(frozen=True)
class LayerSpec:
    name: str
    min_diameter_deg: float
    max_diameter_deg: float
    healpix_level: int
    stars_per_cell: int = 5
    quads_per_star: int = 2
    magnitude_limit: float = 99.0
    estimated_bytes: int = 0

    @property
    def nominal_diameter_deg(self) -> float:
        return 0.5 * (self.min_diameter_deg / 0.7 + self.max_diameter_deg / 1.4)


LAYERS = {
    spec.name: spec
    for spec in (
        LayerSpec("q004", 4 / 60 * 0.7, 4 / 60 * 1.4, 10, 5, 2, 15.4, 1_387_419_120),
        LayerSpec("q008", 8 / 60 * 0.7, 8 / 60 * 1.4, 9, 5, 2, 13.6, 383_025_280),
        LayerSpec("q016", 16 / 60 * 0.7, 16 / 60 * 1.4, 8, 5, 2, 12.0, 106_247_728),
        LayerSpec("q032", 32 / 60 * 0.7, 32 / 60 * 1.4, 7, 5, 2, 10.5, 28_957_176),
        LayerSpec("q064", 64 / 60 * 0.7, 64 / 60 * 1.4, 6, 5, 2, 9.1, 7_757_912),
        LayerSpec("q128", 128 / 60 * 0.7, 128 / 60 * 1.4, 5, 5, 2, 8.0, 2_358_712),
        LayerSpec("q256", 256 / 60 * 0.7, 256 / 60 * 1.4, 4, 5, 2, 8.0, 780_872),
    )
}


@dataclass(frozen=True)
class FieldRange:
    id: str
    name: str
    recommended: bool
    min_deg: float
    max_deg: float
    layers: tuple[str, ...]
    estimated_bytes: int
    build_memory_bytes: int


def _field_range(
    id: str,
    name: str,
    recommended: bool,
    min_deg: float,
    max_deg: float,
    layers: tuple[str, ...],
    build_memory_bytes: int,
) -> FieldRange:
    return FieldRange(
        id=id,
        name=name,
        recommended=recommended,
        min_deg=min_deg,
        max_deg=max_deg,
        layers=layers,
        estimated_bytes=sum(LAYERS[name].estimated_bytes for name in layers),
        build_memory_bytes=build_memory_bytes,
    )


FIELD_RANGES = (
    _field_range(
        "0.4-10",
        "Standard",
        True,
        0.4,
        10.0,
        ("q008", "q016", "q032", "q064", "q128", "q256"),
        3_200_000_000,
    ),
    _field_range("0.2-0.4", "Narrow fields", False, 0.2, 0.4, ("q004",), 5_400_000_000),
)


def range_for_field(field_deg: float) -> FieldRange | None:
    overall_max = max(field_range.max_deg for field_range in FIELD_RANGES)
    for field_range in FIELD_RANGES:
        if field_range.min_deg <= field_deg < field_range.max_deg:
            return field_range
        if field_range.max_deg == overall_max and field_deg == overall_max:
            return field_range
    return None


def indexes_dir() -> Path:
    return star_root() / "indexes"


def layer_path(name: str) -> Path:
    return indexes_dir() / f"{name}.ncidx"


def manifest_path() -> Path:
    return indexes_dir() / "ranges.json"


def read_manifest() -> set[str]:
    try:
        data = json.loads(manifest_path().read_text(encoding="utf-8"))
        valid = {item.id for item in FIELD_RANGES}
        return {str(item) for item in data.get("ranges", []) if item in valid}
    except OSError, TypeError, ValueError, json.JSONDecodeError:
        return set()


def write_manifest(ids: set[str]) -> None:
    directory = indexes_dir()
    directory.mkdir(parents=True, exist_ok=True)
    destination = manifest_path()
    temporary = destination.with_suffix(".tmp")
    try:
        temporary.write_text(json.dumps({"ranges": sorted(ids)}, indent=2), encoding="utf-8")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def built_ranges() -> set[str]:
    from .index import layer_state

    manifest = read_manifest()
    return {
        item.id
        for item in FIELD_RANGES
        if item.id in manifest and all(layer_state(name) == "ready" for name in item.layers)
    }


def built_layers() -> list[str]:
    ready = built_ranges()
    return sorted({name for item in FIELD_RANGES if item.id in ready for name in item.layers})
