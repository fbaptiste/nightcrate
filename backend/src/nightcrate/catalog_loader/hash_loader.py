"""Planetary-nebula collectors for the VizieR HASH catalog (V/163)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import TYPE_CHECKING

from nightcrate.catalog_loader._common import clean_tex_name, maybe_float, maybe_str
from nightcrate.catalog_loader.designations import canonical_identifier
from nightcrate.catalog_loader.hash import file_sha256, row_sha256
from nightcrate.catalog_loader.registry import CatalogSource
from nightcrate.catalog_loader.vizier_tsv import parse_vizier_tsv

if TYPE_CHECKING:
    from nightcrate.catalog_loader.reconcile import CollectorBatch

_PNG_STATUSES = frozenset({"T", "L", "P"})
_ABELL_RE = re.compile(r"^Abell\s+(\d+)$", re.IGNORECASE)
_NGC_IC_RE = re.compile(r"^(NGC|IC)\s+(\d+)(?P<compound>[/\-]\d+)?$", re.IGNORECASE)
_SHARPLESS2_RE = re.compile(r"^Sh\s*2-(\d+)$", re.IGNORECASE)
_STATUS_DESCRIPTIONS = {
    "T": "True PN",
    "L": "Likely PN",
    "P": "Possible PN",
    "agb": "AGB Star",
    "agb?": "AGB Star candidate",
    "q": "artefact",
    "Be*": "Be Star",
    "CV*": "Cataclysmic Variable Star",
    "cir": "CircumStellar Matter",
    "Cl*": "Cluster of Stars",
    "CGb": "Cometary Globule",
    "Em*": "Emission Line Star",
    "EmO": "Emission Object",
    "G": "Galaxy",
    "HH": "Herbig-Haro Object",
    "HII": "HII Region",
    "o": "Interesting Object",
    "iISM": "Ionized ISM",
    "c": "New Candidates",
    "X": "Not PN",
    "N": "Not PN (check)",
    "ooun": "Object of unknown nature",
    "s": "Objects to check",
    "a": "PAGB/Pre-PN",
    "?Em*": "Possible Emission Line Star",
    "G?": "Possible Galaxy",
    "HH?": "Possible Herbig-Haro Object",
    "b": "Possible PrePN",
    "e": "RCrB/eHe/LTP",
    "RNe": "Reflection Nebula",
}


def _arcmin(value: str | None) -> float | None:
    arcsec = maybe_float(value)
    return arcsec / 60.0 if arcsec is not None else None


def _abell_number(name: str | None) -> str | None:
    if name is None or (match := _ABELL_RE.fullmatch(name)) is None:
        return None
    return str(int(match.group(1)))


def _cross_identifications(name: str | None) -> tuple[tuple[str, str], ...]:
    if name is None:
        return ()
    if match := _NGC_IC_RE.fullmatch(name):
        return ((match.group(1).lower(), str(int(match.group(2)))),)
    if match := _SHARPLESS2_RE.fullmatch(name):
        return (("sharpless2", str(int(match.group(1)))),)
    return ()


def _notes(name: str | None, status: str, *, is_abell: bool) -> str | None:
    parts: list[str] = []
    if status not in _PNG_STATUSES:
        description = _STATUS_DESCRIPTIONS.get(status, status)
        parts.append(f"HASH classifies this as {description}, not a planetary nebula.")
    if name is not None and not is_abell:
        ngc_ic_match = _NGC_IC_RE.fullmatch(name)
        is_compound_ngc_ic = ngc_ic_match is not None and ngc_ic_match.group("compound") is not None
        if not _cross_identifications(name) or is_compound_ngc_ic:
            parts.append(f"Also {name}")
    return " · ".join(parts) or None


def _object_type(status: str) -> str:
    if status in _PNG_STATUSES:
        return "PN"
    if status == "iISM":
        return "Neb"
    if status in {"G", "G?"}:
        return "G"
    return "Other"


def _columns(
    primary_designation: str,
    row: dict[str, str | None],
    status: str,
    *,
    is_abell: bool,
) -> dict[str, object]:
    ra_deg = maybe_float(row.get("RAJ2000"))
    dec_deg = maybe_float(row.get("DEJ2000"))
    return {
        "primary_designation": primary_designation,
        "obj_type": _object_type(status),
        "raw_obj_type": None,
        "ra_deg": ra_deg,
        "dec_deg": dec_deg,
        "constellation": None,
        "maj_axis_arcmin": _arcmin(row.get("MajDiam")),
        "min_axis_arcmin": _arcmin(row.get("MinDiam")),
        "position_angle_deg": None,
        "mag_b": None,
        "mag_v": None,
        "mag_j": None,
        "mag_h": None,
        "mag_k": None,
        "surface_brightness": None,
        "hubble_type": None,
        "pm_ra": None,
        "pm_dec": None,
        "radial_velocity": None,
        "redshift": None,
        "cstar_mag_u": None,
        "cstar_mag_b": None,
        "cstar_mag_v": None,
        "cstar_id": None,
        "common_name": None,
        "ned_notes": None,
        "openngc_notes": _notes(clean_tex_name(row.get("Name")), status, is_abell=is_abell),
        "raw_other_id": None,
        "source_row_hash": row_sha256(
            {key: value for key, value in row.items() if value is not None}
        ),
    }


def collect_hash(
    sources: Mapping[str, CatalogSource], on_catalogs: frozenset[str]
) -> CollectorBatch:
    """Return the selected PN G and Abell-PN views over one HASH table."""
    from nightcrate.catalog_loader.reconcile import CollectedObject, CollectorBatch

    source_hashes = {
        source_id: file_sha256(source.file_path) for source_id, source in sources.items()
    }
    source = sources.get("vizier_hash")
    objects: list[CollectedObject] = []
    if source is None:
        return CollectorBatch((), (), source_hashes)

    png_on = "png" in on_catalogs
    abell_on = "abell_pn" in on_catalogs
    for row in parse_vizier_tsv(source.file_path):
        if maybe_str(row.get("Domain")) != "Galaxy":
            continue
        raw_hash_id = maybe_str(row.get("HASH"))
        status = maybe_str(row.get("PNstat"))
        raw_png = maybe_str(row.get("PNG"))
        if raw_hash_id is None or status is None:
            continue
        try:
            source_key = str(int(raw_hash_id))
        except ValueError:
            continue
        name = clean_tex_name(row.get("Name"))
        abell_number = _abell_number(name)
        in_png = png_on and status in _PNG_STATUSES and raw_png is not None
        in_abell = abell_on and abell_number is not None
        if not in_png and not in_abell:
            continue

        if in_png:
            identifier = canonical_identifier("png", raw_png)
            catalog_id = "png"
            catalog = "png"
            extra_designations = (("abell", abell_number),) if in_abell else ()
            also_catalog_ids = ("abell_pn",) if in_abell else ()
            primary_designation = f"PN G{identifier}"
        else:
            if abell_number is None:
                continue
            identifier = abell_number
            catalog_id = "abell_pn"
            catalog = "abell"
            extra_designations = ()
            also_catalog_ids = ()
            primary_designation = f"Abell {identifier}"

        objects.append(
            CollectedObject(
                source_id=source.source_id,
                source_key=source_key,
                catalog_id=catalog_id,
                also_catalog_ids=also_catalog_ids,
                catalog=catalog,
                identifier=identifier,
                columns=_columns(
                    primary_designation,
                    row,
                    status,
                    is_abell=abell_number is not None,
                ),
                extra_designations=extra_designations,
                cross_identifications=_cross_identifications(name),
            )
        )
    return CollectorBatch(tuple(objects), (), source_hashes)
