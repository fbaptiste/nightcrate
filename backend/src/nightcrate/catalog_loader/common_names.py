"""Parse and combine catalog and editorial common names."""

from __future__ import annotations

import csv
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlparse

from nightcrate.catalog_loader.crossref_parser import parse_other_id
from nightcrate.catalog_loader.openngc_parser import _parse_name
from nightcrate.catalog_loader.registry import CatalogSource


def split_common_names(text: str | None) -> tuple[str, ...]:
    """Split a catalog name field, preserving the first spelling of each name."""
    if text is None:
        return ()
    return merge_names(part.strip() for part in text.split(",") if part.strip())


def merge_names(*name_lists: Iterable[str]) -> tuple[str, ...]:
    """Concatenate name lists and de-duplicate them case-insensitively."""
    merged: list[str] = []
    seen: set[str] = set()
    for names in name_lists:
        for raw_name in names:
            name = raw_name.strip()
            folded = name.casefold()
            if not name or folded in seen:
                continue
            seen.add(folded)
            merged.append(name)
    return tuple(merged)


@dataclass(frozen=True, slots=True)
class ListedNames:
    designation: str
    target: Literal["object", "group"]
    names: tuple[str, ...]
    removals: frozenset[str]


@dataclass(slots=True)
class _ListedRows:
    names: list[tuple[int, str]]
    removals: set[str]


def _designation_is_parseable(designation: str) -> bool:
    catalog, identifier = _parse_name(designation)
    if catalog is not None and identifier is not None:
        return True
    return len(parse_other_id(designation)) == 1


_COUNTRY_SECOND_LEVEL_DOMAINS = frozenset({"ac", "co", "com", "edu", "gov", "net", "org"})


def _registrable_domain(hostname: str) -> str:
    labels = hostname.lower().strip(".").split(".")
    if len(labels) <= 2:
        return ".".join(labels)
    if len(labels[-1]) == 2 and labels[-2] in _COUNTRY_SECOND_LEVEL_DOMAINS:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def _source_family(source: str) -> str | None:
    source = source.strip()
    if not source:
        return None

    parsed = urlparse(source)
    if parsed.scheme.lower() in {"http", "https"} and parsed.hostname:
        hostname = parsed.hostname.lower().strip(".")
        if hostname == "wikipedia.org" or hostname.endswith(".wikipedia.org"):
            return "wikimedia"
        if hostname == "wikidata.org" or hostname.endswith(".wikidata.org"):
            return "wikimedia"
        if hostname == "nasa.gov" or hostname.endswith(".nasa.gov"):
            return "nasa"
        if hostname in {"esa.int", "esahubble.org", "esawebb.org"} or hostname.endswith(
            (".esa.int", ".esahubble.org", ".esawebb.org")
        ):
            return "esa"
        return f"domain:{_registrable_domain(hostname)}"

    prefix, separator, _identifier = source.partition(":")
    if separator:
        family = prefix.strip().casefold()
        if family in {"wikidata", "wikipedia"}:
            return "wikimedia"
        return f"prefix:{family}"
    return f"source:{source.casefold()}"


def _source_count(value: str) -> int:
    return len(
        {family for source in value.split(";") if (family := _source_family(source)) is not None}
    )


def read_common_names(source: CatalogSource | None) -> list[ListedNames]:
    """Read and validate the registered editorial common-name list."""
    if source is None or not source.file_path.exists():
        return []

    with source.file_path.open("r", encoding="utf-8", newline="") as handle:
        kept_lines = [
            (line_number, line)
            for line_number, line in enumerate(handle, start=1)
            if line.strip() and not line.lstrip().startswith("#")
        ]
    lines = [line for _line_number, line in kept_lines]
    if not lines:
        return []

    grouped: dict[tuple[str, str], _ListedRows] = {}
    designation_targets: dict[str, str] = {}
    assigned_names: dict[str, str] = {}
    reader = csv.DictReader(lines)
    for row in reader:
        line_number = kept_lines[reader.line_num - 1][0]
        values = {key: (value or "").strip() for key, value in row.items() if key is not None}
        designation = values.get("designation", "")
        target = values.get("target", "")
        name = values.get("name", "")
        action = values.get("action", "")
        rank_text = values.get("rank", "")

        if not designation or not _designation_is_parseable(designation):
            raise ValueError(
                f"unrecognized designation on common-names row {line_number}: {designation!r}"
            )
        if target not in {"object", "group"}:
            raise ValueError(f"unknown common-name target for {designation!r}: {target!r}")
        previous_target = designation_targets.setdefault(designation, target)
        if previous_target != target:
            raise ValueError(f"designation {designation!r} has more than one target type")
        if action not in {"name", "remove"}:
            raise ValueError(f"unknown common-name action for {designation!r}: {action!r}")
        if not name:
            raise ValueError(f"empty common name for {designation!r}")
        if "," in name:
            raise ValueError(f"common name for {designation!r} contains a comma: {name!r}")
        if target == "group" and action == "remove":
            raise ValueError(f"group {designation!r} cannot remove a name")

        key = (designation, target)
        bucket = grouped.setdefault(key, _ListedRows(names=[], removals=set()))
        if action == "remove":
            if rank_text:
                raise ValueError(f"remove row for {designation!r} cannot have a rank")
            bucket.removals.add(name.casefold())
            continue

        if _source_count(values.get("sources", "")) < 2:
            raise ValueError(f"common name {name!r} for {designation!r} needs two sources")
        try:
            rank = int(rank_text)
        except ValueError as exc:
            raise ValueError(f"invalid rank for {designation!r}: {rank_text!r}") from exc
        if rank < 1:
            raise ValueError(f"invalid rank for {designation!r}: {rank_text!r}")

        folded = name.casefold()
        previous_designation = assigned_names.get(folded)
        if previous_designation is not None:
            raise ValueError(
                f"common name {name!r} is assigned more than once "
                f"({previous_designation!r}, {designation!r})"
            )
        assigned_names[folded] = designation
        bucket.names.append((rank, name))

    result: list[ListedNames] = []
    for (designation, target), bucket in grouped.items():
        ranked_names = bucket.names
        ranked_names.sort(key=lambda item: item[0])
        ranks = [rank for rank, _name in ranked_names]
        if ranks != list(range(1, len(ranked_names) + 1)):
            raise ValueError(f"bad rank sequence for {designation!r}: {ranks!r}")
        if target == "group" and len(ranked_names) != 1:
            raise ValueError(f"group {designation!r} must have exactly one name")
        result.append(
            ListedNames(
                designation,
                target,  # type: ignore[arg-type]
                tuple(name for _rank, name in ranked_names),
                frozenset(bucket.removals),
            )
        )
    return result
