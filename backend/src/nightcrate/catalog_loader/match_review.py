"""Review stated catalog matches before applying a new object catalog."""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from nightcrate.catalog_loader.designations import normalize_designation
from nightcrate.catalog_loader.loader import _build_display_form
from nightcrate.catalog_loader.reconcile import ObjectSet, build_object_set
from nightcrate.catalog_loader.registry import OPTIONAL_CATALOGS, get_sources


@dataclass(frozen=True, slots=True)
class MatchFlag:
    designation: str
    target_designation: str
    reason: Literal["size_ratio", "target_is_part"]
    entry_size_arcmin: float | None
    target_size_arcmin: float | None
    evidence: str


def flag_stated_matches(
    new: ObjectSet,
    parts: set[tuple[str, str]],
) -> list[MatchFlag]:
    """Return stated matches needing a human size or membership review."""
    part_keys = {normalize_designation(part) for _whole, part in parts}
    flags: list[MatchFlag] = []
    for match in new.stated_matches:
        designation = _build_display_form(match.catalog, match.identifier)
        target_designation = str(new.objects[match.target_index].columns["primary_designation"])
        if (
            match.entry_size_arcmin is not None
            and match.target_size_arcmin is not None
            and min(match.entry_size_arcmin, match.target_size_arcmin) > 0
            and max(match.entry_size_arcmin, match.target_size_arcmin)
            / min(match.entry_size_arcmin, match.target_size_arcmin)
            > 3
        ):
            flags.append(
                MatchFlag(
                    designation,
                    target_designation,
                    "size_ratio",
                    match.entry_size_arcmin,
                    match.target_size_arcmin,
                    match.evidence,
                )
            )
        if normalize_designation(target_designation) in part_keys:
            flags.append(
                MatchFlag(
                    designation,
                    target_designation,
                    "target_is_part",
                    match.entry_size_arcmin,
                    match.target_size_arcmin,
                    match.evidence,
                )
            )
    return flags


def _parts(path: Path) -> set[tuple[str, str]]:
    if not path.exists():
        return set()
    with path.open("r", encoding="utf-8", newline="") as handle:
        lines = [line for line in handle if line.strip() and not line.lstrip().startswith("#")]
    return {
        (row["whole_designation"].strip(), row["part_designation"].strip())
        for row in csv.DictReader(lines)
        if row.get("whole_designation") and row.get("part_designation")
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalogs_root", type=Path)
    args = parser.parse_args(argv)

    sources = {source.source_id: source for source in get_sources(args.catalogs_root)}
    crossref = sources.get("nightcrate_sharpless_crossref")
    new = build_object_set(
        sources,
        crossref.file_path if crossref is not None else None,
        frozenset(catalog.catalog_id for catalog in OPTIONAL_CATALOGS),
    )
    part_source = sources.get("nightcrate_parts")
    flags = flag_stated_matches(
        new,
        _parts(part_source.file_path) if part_source is not None else set(),
    )
    writer = csv.DictWriter(
        sys.stdout,
        fieldnames=[
            "designation",
            "target_designation",
            "reason",
            "entry_size_arcmin",
            "target_size_arcmin",
            "evidence",
        ],
    )
    writer.writeheader()
    writer.writerows(asdict(flag) for flag in flags)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
