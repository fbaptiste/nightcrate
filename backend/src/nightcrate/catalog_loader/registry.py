"""Static registry of DSO catalog sources known to the loader.

v0.14.0 shipped two sources (OpenNGC + addendum, fetched from GitHub).
v0.15.0 adds VizieR-sourced catalogs (Sharpless, Barnard), a GitHub-
sourced 50 MGC catalog, and vendored NightCrate editorial CSVs
(augmentation + Sharpless crossref, plus the intentionally-empty Barnard
crossref for symmetry).

Most entries return regardless of whether the backing file exists on
disk — the loader emits ``status="missing"`` for absent files and the
UI surfaces a "Load" CTA in Admin → Catalogs. The two NightCrate
sources live in the Python package itself (``data/catalogs/nightcrate``)
so they're always available.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Literal

from nightcrate.catalog_loader.hash import file_sha256
from nightcrate.catalog_loader.vizier import VizierFetchSpec
from nightcrate.core import app_config

_VERSION_JSON_ERRS: tuple[type[BaseException], ...] = (
    json.JSONDecodeError,
    OSError,
    ValueError,
)

OPENNGC_SOURCE_URL = "https://github.com/mattiaverga/OpenNGC"
OPENNGC_LICENSE = "CC-BY-SA-4.0"
OPENNGC_CITATION = (
    "Verga, Mattia. OpenNGC — Database of NGC and IC objects. "
    "https://github.com/mattiaverga/OpenNGC"
)

VIZIER_BASE_URL = "https://vizier.cds.unistra.fr"
VIZIER_LICENSE = "CDS public"
CDS_CITATION = (
    "This research has made use of the VizieR catalogue access tool, "
    "CDS, Strasbourg, France (DOI: 10.26093/cds/vizier)."
)
WR_CITATION = (
    "van der Hucht, K.A. 2001 — The Seventh Catalogue of Galactic Wolf-Rayet "
    "stars, New Astronomy Reviews 45, 135 (VizieR III/215). " + CDS_CITATION
)
HH_CITATION = (
    "Reipurth, B.: 1999, A general catalogue of Herbig-Haro objects, 2. edition, "
    "http://casa.colorado.edu/hhcat (VizieR V/104). " + CDS_CITATION
)
HASH_CITATION = (
    "Parker, Q.A., Bojičić, I.S. & Frew, D.J. 2016 — HASH: the Hong "
    "Kong/AAO/Strasbourg Hα planetary nebula database, Journal of Physics: "
    "Conference Series 728, 032008. This research has made use of the HASH PN "
    "database at hashpn.space (VizieR V/163). " + CDS_CITATION
)
ABELL_PN_COVERAGE = " Covers 85 of the 86 Abell numbers; Abell 85 (CTB 1) is a supernova remnant."
LBN_CITATION = (
    "Lynds, B.T. 1965 — Catalogue of Bright Nebulae, Astrophysical Journal "
    "Supplement Series 12, 163 (VizieR VII/9). " + CDS_CITATION
)
LDN_CITATION = (
    "Lynds, B.T. 1962 — Catalogue of Dark Nebulae, Astrophysical Journal "
    "Supplement Series 7, 1 (VizieR VII/7A). " + CDS_CITATION
)
MELOTTE_CITATION = (
    "Melotte 1915, MmRAS 60, 175 (A Catalogue of Star Clusters shown on "
    "Franklin-Adams Chart Plates), transcribed and checked by NightCrate. "
    "Positions and sizes of clusters without an NGC or IC number: Hunt & "
    "Reffert 2023, A&A 673, A114, or SIMBAD."
)
ACO_CITATION = (
    "Abell, G.O., Corwin, H.G. Jr. & Olowin, R.P. 1989 — A Catalogue of Rich "
    "Clusters of Galaxies, Astrophysical Journal Supplement Series 70, 1 "
    "(VizieR VII/110A). " + CDS_CITATION
)
MCG_CITATION = (
    "Vorontsov-Velyaminov, B.A., Krasnogorskaya, A.A. & Arkhipova, V.P. "
    "1962–1974 — Morphological Catalogue of Galaxies, volumes 1–5 "
    "(VizieR VII/62A, VII/100). " + CDS_CITATION
)
ARP_CITATION = (
    "Arp, H. 1966 — Atlas of Peculiar Galaxies; Webb, D. 1996 — Arp's "
    "Peculiar Galaxies index (VizieR VII/192). " + CDS_CITATION
)

WIKIDATA_SOURCE_URL = "https://query.wikidata.org/sparql"
WIKIDATA_LICENSE = "CC0-1.0"
NIGHTCRATE_LICENSE = "GPL-3.0-or-later"
WIKIDATA_CITATION = (
    "Wikidata contributors. Wikidata: the free knowledge base. "
    "Retrieved via the Wikidata Query Service (query.wikidata.org). "
    "Data licensed under CC0 1.0 Universal (Public Domain Dedication). "
    "Wikipedia article links are provided via Wikidata sitelinks; "
    "article content is not bundled (CC BY-SA 4.0 applies to the linked content). "
    "SIMBAD cross-reference links are provided courtesy of the Centre "
    "de Données astronomiques de Strasbourg (CDS), Université de "
    "Strasbourg / CNRS. NED cross-reference links are provided by the "
    "NASA/IPAC Extragalactic Database (NED), operated by the Jet "
    "Propulsion Laboratory, California Institute of Technology, under "
    "contract with NASA."
)


@dataclass(frozen=True, slots=True)
class CatalogSource:
    source_id: str
    category: str  # 'openngc' | 'vizier' | 'nightcrate' | 'wikidata'
    display_name: str
    file_path: Path
    version: str | None
    source_url: str | None
    license: str | None
    attribution: str
    # Parser strategy identifier — dispatches to the right loader in
    # loader.py. One of: 'openngc', 'sharpless', 'barnard', 'mgc50',
    # 'augment', 'common_names', 'sharpless_crossref', 'barnard_crossref',
    # 'wikidata_external_refs', 'external_refs'.
    parser: str


@dataclass(frozen=True, slots=True)
class OptionalCatalog:
    catalog_id: str
    display_name: str
    source_ids: tuple[str, ...]
    kind: Literal["vizier", "nightcrate"]
    fetch_specs: tuple[VizierFetchSpec, ...]
    designation_catalogs: frozenset[str]
    legacy_default: bool
    credit: str


OPTIONAL_CATALOGS: tuple[OptionalCatalog, ...] = (
    OptionalCatalog(
        catalog_id="sharpless",
        display_name="Sharpless 2",
        source_ids=("vizier_sharpless",),
        kind="vizier",
        fetch_specs=(
            VizierFetchSpec(
                source_id="vizier_sharpless",
                catalog_id="VII/20/catalog",
                output_filename="sharpless_VII_20.tsv",
                display_name="Sharpless 2 (VII/20)",
                citation="Sharpless 1959 ApJS 4, 257. Retrieved via VizieR.",
                additional_params={"-out.add": "_RAJ2000,_DEJ2000"},
            ),
        ),
        designation_catalogs=frozenset({"sharpless2"}),
        legacy_default=True,
        credit="Sharpless 1959 ApJS 4, 257. Retrieved via VizieR.",
    ),
    OptionalCatalog(
        catalog_id="barnard",
        display_name="Barnard",
        source_ids=("vizier_barnard",),
        kind="vizier",
        fetch_specs=(
            VizierFetchSpec(
                source_id="vizier_barnard",
                catalog_id="VII/220A/barnard",
                output_filename="barnard_VII_220.tsv",
                display_name="Barnard dark nebulae (VII/220A)",
                citation="Barnard 1927 (VizieR VII/220A).",
                additional_params={"-out.add": "_RAJ2000,_DEJ2000"},
            ),
        ),
        designation_catalogs=frozenset({"barnard"}),
        legacy_default=True,
        credit="Barnard 1927. Retrieved via VizieR VII/220A.",
    ),
    OptionalCatalog(
        catalog_id="wr",
        display_name="Wolf-Rayet stars",
        source_ids=("vizier_wr", "vizier_wr_phot"),
        kind="vizier",
        fetch_specs=(
            VizierFetchSpec(
                source_id="vizier_wr",
                catalog_id="III/215/table13",
                output_filename="wr_III_215_table13.tsv",
                display_name="Wolf-Rayet positions (III/215 table13)",
                citation=WR_CITATION,
                column_filter="WR,Name",
                additional_params={"-out.add": "_RAJ2000,_DEJ2000"},
                required_columns=("_RAJ2000", "_DEJ2000", "WR", "Name"),
            ),
            VizierFetchSpec(
                source_id="vizier_wr_phot",
                catalog_id="III/215/table15",
                output_filename="wr_III_215_table15.tsv",
                display_name="Wolf-Rayet photometry (III/215 table15)",
                citation=WR_CITATION,
                column_filter="WR,vmag,SpType",
                required_columns=("WR", "vmag", "SpType"),
            ),
        ),
        designation_catalogs=frozenset({"wr"}),
        legacy_default=False,
        credit="van der Hucht 2001. Retrieved via VizieR III/215.",
    ),
    OptionalCatalog(
        catalog_id="hh",
        display_name="Herbig-Haro objects",
        source_ids=("vizier_hh",),
        kind="vizier",
        fetch_specs=(
            VizierFetchSpec(
                source_id="vizier_hh",
                catalog_id="V/104/catalog",
                output_filename="hh_V_104.tsv",
                display_name="Herbig-Haro objects (V/104)",
                citation=HH_CITATION,
                column_filter="HH,Name,Region",
                additional_params={"-out.add": "_RAJ2000,_DEJ2000"},
                required_columns=("_RAJ2000", "_DEJ2000", "HH", "Name", "Region"),
            ),
        ),
        designation_catalogs=frozenset({"hh"}),
        legacy_default=False,
        credit="Reipurth 1999. Retrieved via VizieR V/104.",
    ),
    OptionalCatalog(
        catalog_id="png",
        display_name="Planetary nebulae (HASH)",
        source_ids=("vizier_hash",),
        kind="vizier",
        fetch_specs=(
            VizierFetchSpec(
                source_id="vizier_hash",
                catalog_id="V/163/pnmain",
                output_filename="hash_V_163_pnmain.tsv",
                display_name="Planetary nebulae (HASH; V/163)",
                citation=HASH_CITATION,
                column_filter=("HASH,PNG,RAJ2000,DEJ2000,Name,PNstat,Domain,MajDiam,MinDiam"),
                required_columns=(
                    "HASH",
                    "PNG",
                    "RAJ2000",
                    "DEJ2000",
                    "Name",
                    "PNstat",
                    "Domain",
                    "MajDiam",
                    "MinDiam",
                ),
            ),
        ),
        designation_catalogs=frozenset({"png"}),
        legacy_default=False,
        credit="Parker, Bojičić & Frew 2016 (HASH). Retrieved via VizieR V/163.",
    ),
    OptionalCatalog(
        catalog_id="abell_pn",
        display_name="Abell planetary nebulae",
        source_ids=("vizier_hash",),
        kind="vizier",
        fetch_specs=(
            VizierFetchSpec(
                source_id="vizier_hash",
                catalog_id="V/163/pnmain",
                output_filename="hash_V_163_pnmain.tsv",
                display_name="Abell planetary nebulae (HASH; V/163)",
                citation=HASH_CITATION,
                column_filter=("HASH,PNG,RAJ2000,DEJ2000,Name,PNstat,Domain,MajDiam,MinDiam"),
                required_columns=(
                    "HASH",
                    "PNG",
                    "RAJ2000",
                    "DEJ2000",
                    "Name",
                    "PNstat",
                    "Domain",
                    "MajDiam",
                    "MinDiam",
                ),
            ),
        ),
        designation_catalogs=frozenset({"abell"}),
        legacy_default=False,
        credit=(
            "Parker, Bojičić & Frew 2016 (HASH). Retrieved via VizieR V/163." + ABELL_PN_COVERAGE
        ),
    ),
    OptionalCatalog(
        catalog_id="lbn",
        display_name="LBN (Lynds bright nebulae)",
        source_ids=("vizier_lbn",),
        kind="vizier",
        fetch_specs=(
            VizierFetchSpec(
                source_id="vizier_lbn",
                catalog_id="VII/9/catalog",
                output_filename="lbn_VII_9.tsv",
                display_name="LBN (Lynds bright nebulae)",
                citation=LBN_CITATION,
                column_filter="Seq,Diam1,Diam2,Bright,Name",
                additional_params={"-out.add": "_RAJ2000,_DEJ2000"},
                required_columns=(
                    "_RAJ2000",
                    "_DEJ2000",
                    "Seq",
                    "Diam1",
                    "Diam2",
                    "Bright",
                    "Name",
                ),
            ),
        ),
        designation_catalogs=frozenset({"lbn"}),
        legacy_default=False,
        credit="Lynds 1965. Retrieved via VizieR VII/9.",
    ),
    OptionalCatalog(
        catalog_id="ldn",
        display_name="LDN (Lynds dark nebulae)",
        source_ids=("vizier_ldn",),
        kind="vizier",
        fetch_specs=(
            VizierFetchSpec(
                source_id="vizier_ldn",
                catalog_id="VII/7A/ldn",
                output_filename="ldn_VII_7A.tsv",
                display_name="LDN (Lynds dark nebulae)",
                citation=LDN_CITATION,
                column_filter="LDN,Area,Opacity,Barn",
                additional_params={"-out.add": "_RAJ2000,_DEJ2000"},
                required_columns=(
                    "_RAJ2000",
                    "_DEJ2000",
                    "LDN",
                    "Area",
                    "Opacity",
                    "Barn",
                ),
            ),
        ),
        designation_catalogs=frozenset({"ldn"}),
        legacy_default=False,
        credit="Lynds 1962. Retrieved via VizieR VII/7A.",
    ),
    OptionalCatalog(
        catalog_id="melotte",
        display_name="Melotte star clusters",
        source_ids=("nightcrate_melotte",),
        kind="nightcrate",
        fetch_specs=(),
        designation_catalogs=frozenset({"mel"}),
        legacy_default=False,
        credit=(
            "Melotte 1915, checked by NightCrate. Positions for five clusters from "
            "Hunt & Reffert 2023 or SIMBAD."
        ),
    ),
    OptionalCatalog(
        catalog_id="aco",
        display_name="ACO (Abell galaxy clusters)",
        source_ids=("vizier_aco_north", "vizier_aco_south", "vizier_aco_s"),
        kind="vizier",
        fetch_specs=(
            VizierFetchSpec(
                source_id="vizier_aco_north",
                catalog_id="VII/110A/table3",
                output_filename="aco_VII_110A_table3.tsv",
                display_name="ACO northern clusters (VII/110A table3)",
                citation=ACO_CITATION,
                column_filter="ACO,BMtype,z,Rich,Dclass,m10",
                additional_params={"-out.add": "_RAJ2000,_DEJ2000"},
                required_columns=(
                    "_RAJ2000",
                    "_DEJ2000",
                    "ACO",
                    "BMtype",
                    "z",
                    "Rich",
                    "Dclass",
                    "m10",
                ),
            ),
            VizierFetchSpec(
                source_id="vizier_aco_south",
                catalog_id="VII/110A/table4",
                output_filename="aco_VII_110A_table4.tsv",
                display_name="ACO southern clusters (VII/110A table4)",
                citation=ACO_CITATION,
                column_filter="ACO,BMtype,z,Rich,Dclass,m10",
                additional_params={"-out.add": "_RAJ2000,_DEJ2000"},
                required_columns=(
                    "_RAJ2000",
                    "_DEJ2000",
                    "ACO",
                    "BMtype",
                    "z",
                    "Rich",
                    "Dclass",
                    "m10",
                ),
            ),
            VizierFetchSpec(
                source_id="vizier_aco_s",
                catalog_id="VII/110A/table5",
                output_filename="aco_VII_110A_table5.tsv",
                display_name="ACO supplementary southern clusters (VII/110A table5)",
                citation=ACO_CITATION,
                column_filter="ACOS,BMtype,z,Rich,Dclass,m10",
                additional_params={"-out.add": "_RAJ2000,_DEJ2000"},
                required_columns=(
                    "_RAJ2000",
                    "_DEJ2000",
                    "ACOS",
                    "BMtype",
                    "z",
                    "Rich",
                    "Dclass",
                    "m10",
                ),
            ),
        ),
        designation_catalogs=frozenset({"aco"}),
        legacy_default=False,
        credit="Abell, Corwin & Olowin 1989. Retrieved via VizieR VII/110A.",
    ),
    OptionalCatalog(
        catalog_id="mcg",
        display_name="MCG (Morphological Catalogue of Galaxies)",
        source_ids=("vizier_mcg", "vizier_mcg_v5"),
        kind="vizier",
        fetch_specs=(
            VizierFetchSpec(
                source_id="vizier_mcg",
                catalog_id="VII/62A/mcg",
                output_filename="mcg_VII_62A.tsv",
                display_name="MCG volumes 1–4 (VII/62A)",
                citation=MCG_CITATION,
                column_filter="MCG,OtherName,Mag,MajAxis,MinAxis",
                additional_params={"-out.add": "_RAJ2000,_DEJ2000"},
                required_columns=(
                    "_RAJ2000",
                    "_DEJ2000",
                    "MCG",
                    "OtherName",
                    "Mag",
                    "MajAxis",
                    "MinAxis",
                ),
            ),
            VizierFetchSpec(
                source_id="vizier_mcg_v5",
                catalog_id="VII/100/catalog",
                output_filename="mcg_VII_100.tsv",
                display_name="MCG volume 5 (VII/100)",
                citation=MCG_CITATION,
                column_filter="MCG,Name,mag,MajAxis,MinAxis",
                additional_params={"-out.add": "_RAJ2000,_DEJ2000"},
                required_columns=(
                    "_RAJ2000",
                    "_DEJ2000",
                    "MCG",
                    "Name",
                    "mag",
                    "MajAxis",
                    "MinAxis",
                ),
            ),
        ),
        designation_catalogs=frozenset({"mcg"}),
        legacy_default=False,
        credit=("Vorontsov-Velyaminov et al. 1962–1974. Retrieved via VizieR VII/62A and VII/100."),
    ),
    OptionalCatalog(
        catalog_id="arp",
        display_name="Arp peculiar galaxies",
        source_ids=("vizier_arp", "nightcrate_arp_members"),
        kind="vizier",
        fetch_specs=(
            VizierFetchSpec(
                source_id="vizier_arp",
                catalog_id="VII/192/arplist",
                output_filename="arp_VII_192.tsv",
                display_name="Arp peculiar-galaxy members (VII/192)",
                citation=ARP_CITATION,
                column_filter="Arp,Name,VT,dim1,dim2,MType,RAJ2000,DEJ2000",
                additional_params={"-out.add": "_RAJ2000,_DEJ2000"},
                required_columns=(
                    "_RAJ2000",
                    "_DEJ2000",
                    "Arp",
                    "Name",
                    "VT",
                    "dim1",
                    "dim2",
                    "MType",
                    "RAJ2000",
                    "DEJ2000",
                ),
            ),
        ),
        designation_catalogs=frozenset({"arp"}),
        legacy_default=False,
        credit="Arp 1966, from Webb's index. Retrieved via VizieR VII/192.",
    ),
)


def optional_catalog(catalog_id: str) -> OptionalCatalog | None:
    """Return optional-catalog metadata for *catalog_id*."""
    return next(
        (catalog for catalog in reversed(OPTIONAL_CATALOGS) if catalog.catalog_id == catalog_id),
        None,
    )


def catalogs_for_source(source_id: str) -> tuple[OptionalCatalog, ...]:
    """Return every logical catalog backed by *source_id*."""
    return tuple(catalog for catalog in OPTIONAL_CATALOGS if source_id in catalog.source_ids)


def _publishing_state(catalogs_root: Path) -> tuple[set[str], set[str]]:
    """Return catalog ids and filenames covered by unfinished publications."""
    publishing = catalogs_root / "vizier" / "publishing"
    catalog_ids: set[str] = set()
    filenames: set[str] = set()
    if not publishing.is_dir():
        return catalog_ids, filenames
    for marker in publishing.glob("*.json"):
        catalog_ids.add(marker.stem)
        try:
            payload = json.loads(marker.read_text(encoding="utf-8"))
            files = payload.get("files", [])
            if isinstance(files, list):
                filenames.update(item for item in files if isinstance(item, str))
        except _VERSION_JSON_ERRS:
            continue
    return catalog_ids, filenames


def optional_catalog_install(
    catalog: OptionalCatalog, catalogs_root: Path
) -> tuple[bool, str | None]:
    """Return whether *catalog* is complete and its installed version/date."""
    if catalog.kind == "nightcrate":
        info = _load_version_json(_nightcrate_dir() / "version.json")
        version = info.get("version")
        return True, str(version) if version else None

    own_markers, publishing_files = _publishing_state(catalogs_root)
    filenames = {spec.output_filename for spec in catalog.fetch_specs}
    if catalog.catalog_id in own_markers or filenames & publishing_files:
        return False, None

    vizier_dir = catalogs_root / "vizier"
    entries = _load_version_json(vizier_dir / "version.json").get("files", {})
    if not isinstance(entries, dict):
        entries = {}
    fetch_dates: list[str] = []
    for spec in catalog.fetch_specs:
        path = vizier_dir / spec.output_filename
        if not path.is_file():
            return False, None
        entry = entries.get(spec.output_filename)
        if entry is None and catalog.legacy_default:
            continue
        if not isinstance(entry, dict):
            return False, None
        digest = file_sha256(path)
        if entry.get("sha256") != digest:
            return False, None
        fetch_date = entry.get("fetch_date")
        if fetch_date:
            fetch_dates.append(str(fetch_date))
    return True, max(fetch_dates, default=None)


def _load_version_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except _VERSION_JSON_ERRS:
        return {}


def read_installed_version(catalogs_root: Path) -> str | None:
    """Return the installed OpenNGC tag (e.g. ``"v20260307"``) or None."""
    info = _load_version_json(catalogs_root / "openngc" / "version.json")
    value = info.get("version")
    return str(value) if value else None


def _nightcrate_dir() -> Path:
    """Return the path to the vendored ``data/catalogs/nightcrate/`` folder.

    These files ship inside the Python package — no user-dir fallback,
    no GitHub fetch, no VizieR download. Use ``importlib.resources`` so
    the path resolves correctly both in source checkouts and installed
    wheels.
    """
    return Path(str(resources.files("nightcrate") / "data" / "catalogs" / "nightcrate"))


def _openngc_sources(catalogs_root: Path) -> list[CatalogSource]:
    openngc_dir = catalogs_root / "openngc"
    info = _load_version_json(openngc_dir / "version.json")
    version = info.get("version")
    return [
        CatalogSource(
            source_id="openngc",
            category="openngc",
            display_name="OpenNGC (NGC / IC / Messier)",
            file_path=openngc_dir / "NGC.csv",
            version=version,
            source_url=OPENNGC_SOURCE_URL,
            license=OPENNGC_LICENSE,
            attribution=OPENNGC_CITATION,
            parser="openngc",
        ),
        CatalogSource(
            source_id="openngc_addendum",
            category="openngc",
            display_name="OpenNGC addendum (non-NGC/IC objects)",
            file_path=openngc_dir / "addendum.csv",
            version=version,
            source_url=OPENNGC_SOURCE_URL,
            license=OPENNGC_LICENSE,
            attribution=OPENNGC_CITATION,
            parser="openngc",
        ),
    ]


def _vizier_sources(catalogs_root: Path) -> list[CatalogSource]:
    vizier_dir = catalogs_root / "vizier"
    version_info = _load_version_json(vizier_dir / "version.json").get("files", {})

    def _version(filename: str) -> str | None:
        entry = version_info.get(filename) or {}
        return entry.get("fetch_date")

    return [
        CatalogSource(
            source_id="vizier_sharpless",
            category="vizier",
            display_name="Sharpless 2 (VizieR VII/20)",
            file_path=vizier_dir / "sharpless_VII_20.tsv",
            version=_version("sharpless_VII_20.tsv"),
            source_url=VIZIER_BASE_URL,
            license=VIZIER_LICENSE,
            attribution=(
                "Sharpless, S. 1959, ApJS, 4, 257 — A Catalogue of HII Regions. "
                "Retrieved via VizieR. " + CDS_CITATION
            ),
            parser="sharpless",
        ),
        CatalogSource(
            source_id="vizier_barnard",
            category="vizier",
            display_name="Barnard (VizieR VII/220)",
            file_path=vizier_dir / "barnard_VII_220.tsv",
            version=_version("barnard_VII_220.tsv"),
            source_url=VIZIER_BASE_URL,
            license=VIZIER_LICENSE,
            attribution=(
                "Barnard, E. E. 1927, A Photographic Atlas of Selected Regions of the "
                "Milky Way. Retrieved via VizieR. " + CDS_CITATION
            ),
            parser="barnard",
        ),
        CatalogSource(
            source_id="vizier_wr",
            category="vizier",
            display_name="Wolf-Rayet positions (VizieR III/215 table13)",
            file_path=vizier_dir / "wr_III_215_table13.tsv",
            version=_version("wr_III_215_table13.tsv"),
            source_url=VIZIER_BASE_URL,
            license=VIZIER_LICENSE,
            attribution=WR_CITATION,
            parser="wr",
        ),
        CatalogSource(
            source_id="vizier_wr_phot",
            category="vizier",
            display_name="Wolf-Rayet photometry (VizieR III/215 table15)",
            file_path=vizier_dir / "wr_III_215_table15.tsv",
            version=_version("wr_III_215_table15.tsv"),
            source_url=VIZIER_BASE_URL,
            license=VIZIER_LICENSE,
            attribution=WR_CITATION,
            parser="wr",
        ),
        CatalogSource(
            source_id="vizier_hh",
            category="vizier",
            display_name="Herbig-Haro objects (VizieR V/104)",
            file_path=vizier_dir / "hh_V_104.tsv",
            version=_version("hh_V_104.tsv"),
            source_url=VIZIER_BASE_URL,
            license=VIZIER_LICENSE,
            attribution=HH_CITATION,
            parser="hh",
        ),
        CatalogSource(
            source_id="vizier_hash",
            category="vizier",
            display_name="Planetary nebulae (HASH; VizieR V/163)",
            file_path=vizier_dir / "hash_V_163_pnmain.tsv",
            version=_version("hash_V_163_pnmain.tsv"),
            source_url=VIZIER_BASE_URL,
            license=VIZIER_LICENSE,
            attribution=HASH_CITATION,
            parser="png",
        ),
        CatalogSource(
            source_id="vizier_lbn",
            category="vizier",
            display_name="LBN (Lynds bright nebulae)",
            file_path=vizier_dir / "lbn_VII_9.tsv",
            version=_version("lbn_VII_9.tsv"),
            source_url=VIZIER_BASE_URL,
            license=VIZIER_LICENSE,
            attribution=LBN_CITATION,
            parser="lbn",
        ),
        CatalogSource(
            source_id="vizier_ldn",
            category="vizier",
            display_name="LDN (Lynds dark nebulae)",
            file_path=vizier_dir / "ldn_VII_7A.tsv",
            version=_version("ldn_VII_7A.tsv"),
            source_url=VIZIER_BASE_URL,
            license=VIZIER_LICENSE,
            attribution=LDN_CITATION,
            parser="ldn",
        ),
        CatalogSource(
            source_id="vizier_aco_north",
            category="vizier",
            display_name="ACO northern clusters (VizieR VII/110A table3)",
            file_path=vizier_dir / "aco_VII_110A_table3.tsv",
            version=_version("aco_VII_110A_table3.tsv"),
            source_url=VIZIER_BASE_URL,
            license=VIZIER_LICENSE,
            attribution=ACO_CITATION,
            parser="aco",
        ),
        CatalogSource(
            source_id="vizier_aco_south",
            category="vizier",
            display_name="ACO southern clusters (VizieR VII/110A table4)",
            file_path=vizier_dir / "aco_VII_110A_table4.tsv",
            version=_version("aco_VII_110A_table4.tsv"),
            source_url=VIZIER_BASE_URL,
            license=VIZIER_LICENSE,
            attribution=ACO_CITATION,
            parser="aco",
        ),
        CatalogSource(
            source_id="vizier_aco_s",
            category="vizier",
            display_name="ACO supplementary southern clusters (VizieR VII/110A table5)",
            file_path=vizier_dir / "aco_VII_110A_table5.tsv",
            version=_version("aco_VII_110A_table5.tsv"),
            source_url=VIZIER_BASE_URL,
            license=VIZIER_LICENSE,
            attribution=ACO_CITATION,
            parser="aco",
        ),
        CatalogSource(
            source_id="vizier_mcg",
            category="vizier",
            display_name="MCG volumes 1–4 (VizieR VII/62A)",
            file_path=vizier_dir / "mcg_VII_62A.tsv",
            version=_version("mcg_VII_62A.tsv"),
            source_url=VIZIER_BASE_URL,
            license=VIZIER_LICENSE,
            attribution=MCG_CITATION,
            parser="mcg",
        ),
        CatalogSource(
            source_id="vizier_mcg_v5",
            category="vizier",
            display_name="MCG volume 5 (VizieR VII/100)",
            file_path=vizier_dir / "mcg_VII_100.tsv",
            version=_version("mcg_VII_100.tsv"),
            source_url=VIZIER_BASE_URL,
            license=VIZIER_LICENSE,
            attribution=MCG_CITATION,
            parser="mcg",
        ),
        CatalogSource(
            source_id="vizier_arp",
            category="vizier",
            display_name="Arp peculiar-galaxy members (VizieR VII/192)",
            file_path=vizier_dir / "arp_VII_192.tsv",
            version=_version("arp_VII_192.tsv"),
            source_url=VIZIER_BASE_URL,
            license=VIZIER_LICENSE,
            attribution=ARP_CITATION,
            parser="arp",
        ),
    ]


def _github_sources(catalogs_root: Path) -> list[CatalogSource]:
    """Sources fetched from GitHub raw-file URLs (not VizieR).

    Only 50 MGC lives here for v0.15.0 — OpenNGC has its own top-level
    entry in ``_openngc_sources`` since it's the flagship and predates
    this split.
    """
    mgc50_dir = catalogs_root / "github" / "50mgc"
    # The 50 MGC fetcher writes its own ``version.json`` in the mgc50 dir.
    info: dict = {}
    version_file = mgc50_dir / "version.json"
    if version_file.exists():
        try:
            info = json.loads(version_file.read_text(encoding="utf-8"))
        except _VERSION_JSON_ERRS:
            info = {}
    return [
        CatalogSource(
            source_id="github_50mgc",
            # Keep VizieR category — data origin is still VizieR; GitHub is
            # just the fetch path we found to be more reliable.
            category="vizier",
            display_name="50 Mpc Galaxy Catalog (Ohlson+ 2024, GitHub mirror)",
            file_path=mgc50_dir / "catalog.fits",
            version=info.get("fetched_at"),
            source_url="https://github.com/davidohlson/50MGC",
            license=VIZIER_LICENSE,
            attribution=(
                "Ohlson, D. et al. 2024, AJ, 167, 31 — The 50 Mpc Galaxy Catalog. "
                "Originally from VizieR J/AJ/167/31; fetched via the author's "
                "GitHub mirror for reliability. " + CDS_CITATION
            ),
            parser="mgc50",
        ),
    ]


def _nightcrate_sources() -> list[CatalogSource]:
    nightcrate_dir = _nightcrate_dir()
    return [
        CatalogSource(
            source_id="nightcrate_melotte",
            category="nightcrate",
            display_name="NightCrate Melotte star clusters",
            file_path=nightcrate_dir / "melotte.csv",
            version=None,
            source_url=None,
            license=NIGHTCRATE_LICENSE,
            attribution=MELOTTE_CITATION,
            parser="melotte",
        ),
        CatalogSource(
            source_id="nightcrate_arp_members",
            category="nightcrate",
            display_name="NightCrate reviewed Arp members",
            file_path=nightcrate_dir / "arp_members.csv",
            version=None,
            source_url=None,
            license=NIGHTCRATE_LICENSE,
            attribution=(
                "NightCrate reviewed Arp member identities. GPL-3.0-or-later. "
                "Distributed as part of NightCrate."
            ),
            parser="arp_members",
        ),
        CatalogSource(
            source_id="nightcrate_parts",
            category="nightcrate",
            display_name="NightCrate DSO part relationships",
            file_path=nightcrate_dir / "dso_parts.csv",
            version=None,
            source_url=None,
            license=NIGHTCRATE_LICENSE,
            attribution=(
                "NightCrate editorial DSO part relationships. GPL-3.0-or-later. "
                "Distributed as part of NightCrate."
            ),
            parser="parts",
        ),
        CatalogSource(
            source_id="nightcrate_match_overrides",
            category="nightcrate",
            display_name="NightCrate DSO match overrides",
            file_path=nightcrate_dir / "dso_match_overrides.csv",
            version=None,
            source_url=None,
            license=NIGHTCRATE_LICENSE,
            attribution=(
                "NightCrate editorial DSO match overrides. GPL-3.0-or-later. "
                "Distributed as part of NightCrate."
            ),
            parser="overrides",
        ),
        CatalogSource(
            source_id="nightcrate_common_names",
            category="nightcrate",
            display_name="NightCrate reviewed common names",
            file_path=nightcrate_dir / "common_names.csv",
            version=None,
            source_url=None,
            license=NIGHTCRATE_LICENSE,
            attribution=(
                "NightCrate reviewed DSO common names. GPL-3.0-or-later. "
                "Distributed as part of NightCrate."
            ),
            parser="common_names",
        ),
        CatalogSource(
            source_id="nightcrate_augment",
            category="nightcrate",
            display_name="NightCrate DSO augmentation",
            file_path=nightcrate_dir / "dso_augment.csv",
            version=None,
            source_url=None,
            license=NIGHTCRATE_LICENSE,
            attribution=(
                "NightCrate editorial augmentation data. GPL-3.0-or-later. "
                "Distributed as part of NightCrate."
            ),
            parser="augment",
        ),
        CatalogSource(
            source_id="nightcrate_sharpless_crossref",
            category="nightcrate",
            display_name="NightCrate Sharpless crossref",
            file_path=nightcrate_dir / "sharpless_crossref.csv",
            version=None,
            source_url=None,
            license=NIGHTCRATE_LICENSE,
            attribution=(
                "NightCrate editorial crossref between Sharpless 2 and NGC/IC/Messier "
                "designations. GPL-3.0-or-later."
            ),
            # Side-input consumed by the Sharpless loader itself; no DSOs
            # are created by this source directly.
            parser="sharpless_crossref",
        ),
        CatalogSource(
            source_id="nightcrate_barnard_crossref",
            category="nightcrate",
            display_name="NightCrate Barnard crossref (empty in v0.15.0)",
            file_path=nightcrate_dir / "barnard_crossref.csv",
            version=None,
            source_url=None,
            license=NIGHTCRATE_LICENSE,
            attribution=(
                "NightCrate editorial crossref for Barnard dark nebulae. Empty in "
                "v0.15.0 — dark nebulae and emission regions at the same line of "
                "sight are physically distinct and are not merged."
            ),
            parser="barnard_crossref",
        ),
        CatalogSource(
            source_id="nightcrate_external_refs",
            category="nightcrate",
            display_name="NightCrate external refs (editorial overrides)",
            file_path=nightcrate_dir / "dso_external_refs.csv",
            version=None,
            source_url=None,
            license=NIGHTCRATE_LICENSE,
            attribution=(
                "NightCrate editorial overrides for DSO external references "
                "(Wikipedia/Wikidata). GPL-3.0-or-later."
            ),
            parser="external_refs",
        ),
    ]


def _wikidata_sources(catalogs_root: Path) -> list[CatalogSource]:
    """Wikidata SPARQL-fetched external-refs source.

    Category is ``'wikidata'`` (distinct from ``'vizier'`` — this is
    a SPARQL-sourced knowledge graph, not a VizieR astronomical catalog).
    """
    from nightcrate.catalog_loader import wikidata

    wikidata_dir = catalogs_root / "wikidata"
    info = wikidata.read_installed_version(catalogs_root)
    return [
        CatalogSource(
            source_id="wikidata_external_refs",
            category="wikidata",
            display_name="Wikidata (external references)",
            file_path=wikidata_dir / "dso_external_refs.tsv",
            version=info.get("fetched_at"),
            source_url=WIKIDATA_SOURCE_URL,
            license=WIKIDATA_LICENSE,
            attribution=WIKIDATA_CITATION,
            parser="wikidata_external_refs",
        ),
    ]


def get_sources(catalogs_root: Path) -> list[CatalogSource]:
    """Return the full list of catalog sources in load order."""
    return [
        *_openngc_sources(catalogs_root),
        *_vizier_sources(catalogs_root),
        *_github_sources(catalogs_root),
        *_wikidata_sources(catalogs_root),
        *_nightcrate_sources(),
    ]


def user_catalogs_root() -> Path:
    """User-writable catalogs directory under the OS app-data folder.

    Resolves ``APP_DIR`` dynamically from ``nightcrate.core.app_config``
    on every call so test fixtures that monkey-patch
    ``app_config.APP_DIR`` take effect immediately — even if this module
    was imported before the patch ran (the import-by-name pattern would
    otherwise freeze the reference to the real OS path at import time).
    """
    return app_config.APP_DIR / "catalogs"
