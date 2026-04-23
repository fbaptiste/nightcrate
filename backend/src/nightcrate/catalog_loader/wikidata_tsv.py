"""Parser for Wikidata SPARQL TSV responses.

Converts the TSV rows emitted by :func:`wikidata.sparql_query` into
:class:`WikidataRecord` objects. Each record carries the Wikidata QID,
label, optional catalog identifiers for every supported catalog, and
an optional English Wikipedia sitelink.

SPARQL TSV is a CSV-like format with tab separators, no quoting of
plain strings, and literal URIs wrapped in ``<...>``. Empty cells are
empty strings. We handle:

- URI values ``<http://...>`` — strip angle brackets
- String literals with language tags (``"foo"@en``) — keep only the
  string body
- String literals without language tags (``"foo"``) — keep only the
  string body
- Plain tokens (bare integers from P3208/P4095/P6340) — keep verbatim
- Empty cells — map to None
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("nightcrate.catalog_loader.wikidata_tsv")

# Columns emitted by :func:`wikidata.sparql_query` — must stay in sync.
_EXPECTED_COLUMNS: tuple[str, ...] = (
    "item",
    "itemLabel",
    "ngc_id",
    "pgc_id",
    "ugc_id",
    "msg",
    "ic",
    "cal",
    "sh2",
    "bar",
    "enwiki_title",
)

_QID_URI_PREFIX = "http://www.wikidata.org/entity/"
_QID_RE = re.compile(r"^Q\d+$")

# Literal value patterns:
#   "foo"@en       → language-tagged literal
#   "foo"          → plain literal
#   "foo"^^<xsd>   → typed literal
# We only need the body, not the type annotation.
_LITERAL_BODY_RE = re.compile(r'^"(.*?)"(@[^"]*)?(\^\^<[^>]*>)?$')


class WikidataParseError(ValueError):
    """Raised for structural TSV errors (bad header, wrong column count)."""


@dataclass(frozen=True, slots=True)
class WikidataRecord:
    qid: str
    qid_url: str
    label: str | None
    # Keys are NightCrate designation normalisation prefixes:
    #   ngc, pgc, ugc, messier, ic, caldwell, sharpless2, barnard, leda
    # Values are bare catalog identifiers (e.g., "1976" for NGC 1976,
    # "42" for Messier 42). Empty dict if no catalog IDs matched.
    catalog_ids: dict[str, str]
    enwiki_title: str | None
    enwiki_url: str | None


def _unquote_literal(raw: str) -> str | None:
    """Return the literal body of a SPARQL TSV cell, or None for empty."""
    raw = raw.strip()
    if not raw:
        return None
    match = _LITERAL_BODY_RE.match(raw)
    if match is not None:
        body = match.group(1)
        # Un-escape the two sequences SPARQL TSV actually emits.
        body = body.replace("\\n", "\n").replace('\\"', '"')
        return body or None
    # Bare token — integer from a direct-ID property, or a URI without the
    # ``<...>`` wrapper (rare but valid in TSV).
    if raw.startswith("<") and raw.endswith(">"):
        return raw[1:-1]
    return raw


def _extract_qid(raw: str) -> str | None:
    value = _unquote_literal(raw)
    if value is None:
        return None
    if value.startswith(_QID_URI_PREFIX):
        value = value[len(_QID_URI_PREFIX) :]
    return value if _QID_RE.match(value) else None


def _strip_leading_zeros(value: str) -> str:
    """Return *value* with leading zeros dropped from a bare numeric prefix.

    Wikidata stores NGC/PGC/etc. identifiers inconsistently — some entries
    use ``"224"``, others ``"0224"``. NightCrate's ``search_key`` drops
    leading zeros on all numeric identifiers so we normalise here.
    """
    match = re.match(r"^0+(\d.*)$", value)
    return match.group(1) if match else value


def _extract_catalog_id_raw(raw_value: str | None, kind: str) -> str | None:
    """Return a cleaned-up catalog identifier from a canonical-form string.

    ``raw_value`` is the TSV cell body. For P528/P972 cells the live data
    carries formatted strings like ``"M 42"`` / ``"NGC 1976"`` / ``"Sh 2-281"``;
    strip the catalog prefix + whitespace so what remains is the bare number
    (or ``2-281`` for Sharpless where the hyphen is meaningful). For direct
    -ID cells the value is already bare.
    """
    if raw_value is None:
        return None
    cleaned = raw_value.strip()
    if not cleaned:
        return None

    # Prefix stripping for canonical-form P528 cells.
    prefixes = {
        "messier": ("M ", "Messier "),
        "ic": ("IC ",),
        "caldwell": ("C ", "Caldwell "),
        "sharpless2": ("SH ", "Sh ", "Sh2-", "SH2-", "Sh2 "),
        "barnard": ("Barnard ", "B "),
    }
    for prefix in prefixes.get(kind, ()):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix) :].strip()
            break
    # Sharpless strings arrive as ``"SH 2-281"`` / ``"Sh2-281"`` — drop the
    # leading ``"2-"`` that is the catalog volume identifier, not the object #.
    if kind == "sharpless2" and cleaned.startswith("2-"):
        cleaned = cleaned[2:]
    cleaned = _strip_leading_zeros(cleaned)
    return cleaned or None


# Mapping from SPARQL column names to NightCrate catalog keys.
# Values map to ``dso_designation.catalog`` (search_key is built from
# the short display form; see :func:`_build_search_key`).
_COLUMN_TO_CATALOG: tuple[tuple[str, str], ...] = (
    ("ngc_id", "ngc"),
    ("pgc_id", "pgc"),
    ("ugc_id", "ugc"),
    ("msg", "messier"),
    ("ic", "ic"),
    ("cal", "caldwell"),
    ("sh2", "sharpless2"),
    ("bar", "barnard"),
)


def _build_search_key(catalog: str, identifier: str) -> str:
    """Return the ``dso_designation.search_key`` form for *catalog/identifier*.

    Mirrors ``loader.py:_build_search_key`` for the catalogs we match.
    """
    prefix_map = {
        "ngc": "ngc",
        "ic": "ic",
        "messier": "m",
        "caldwell": "c",
        "sharpless2": "sh2",
        "barnard": "b",
        "ugc": "ugc",
        "pgc": "pgc",
    }
    prefix = prefix_map.get(catalog, catalog)
    return f"{prefix}{identifier}".lower()


def build_search_keys(record: WikidataRecord) -> list[str]:
    """Return the set of ``dso_designation.search_key`` values for *record*."""
    keys: list[str] = []
    seen: set[str] = set()
    for catalog, identifier in record.catalog_ids.items():
        key = _build_search_key(catalog, identifier)
        if key not in seen:
            seen.add(key)
            keys.append(key)
    return keys


def _parse_header(line: str) -> list[str]:
    columns = [col.strip().lstrip("?") for col in line.rstrip("\n").split("\t")]
    for required in _EXPECTED_COLUMNS:
        if required not in columns:
            raise WikidataParseError(f"missing column {required!r} in SPARQL TSV header")
    return columns


@dataclass(slots=True)
class _AggregatedRecord:
    qid: str
    label: str | None = None
    catalog_ids: dict[str, str] | None = None
    enwiki_title: str | None = None

    def merge_row(self, row: dict[str, str]) -> None:
        # Label: prefer the first non-fallback label we see. The
        # wikibase:label service returns the QID string as a fallback when
        # the entity has no English label — treat that as "no label".
        raw_label = _unquote_literal(row.get("itemLabel", ""))
        if self.label is None and raw_label is not None and raw_label != self.qid:
            self.label = raw_label

        # Catalog IDs: union across rows for the same QID. First hit wins
        # on collisions (direct-ID shortcut columns come first in
        # ``_COLUMN_TO_CATALOG`` so they're preferred over P528 forms).
        if self.catalog_ids is None:
            self.catalog_ids = {}
        for column, catalog in _COLUMN_TO_CATALOG:
            value = _unquote_literal(row.get(column, ""))
            identifier = _extract_catalog_id_raw(value, catalog)
            if identifier is not None:
                self.catalog_ids.setdefault(catalog, identifier)

        # Wikipedia title: first non-null wins. (An entity has at most one
        # enwiki sitelink, so this is really a "pick whichever row carries
        # it" merge.)
        if self.enwiki_title is None:
            title = _unquote_literal(row.get("enwiki_title", ""))
            if title is not None:
                self.enwiki_title = title

    def finalize(self) -> WikidataRecord:
        enwiki_title = self.enwiki_title
        enwiki_url = (
            f"https://en.wikipedia.org/wiki/{enwiki_title.replace(' ', '_')}"
            if enwiki_title
            else None
        )
        return WikidataRecord(
            qid=self.qid,
            qid_url=f"https://www.wikidata.org/wiki/{self.qid}",
            label=self.label,
            catalog_ids=dict(self.catalog_ids or {}),
            enwiki_title=enwiki_title,
            enwiki_url=enwiki_url,
        )


def _parse_row(columns: list[str], line: str, row_number: int) -> dict[str, str] | None:
    """Parse one TSV line into a raw ``{column_name: cell}`` dict.

    Returns ``None`` for rows without a recognisable QID in ``item``.
    Aggregation to :class:`WikidataRecord` happens in :func:`_parse_lines`.
    """
    cells = line.rstrip("\n").split("\t")
    if len(cells) != len(columns):
        raise WikidataParseError(
            f"line {row_number}: expected {len(columns)} columns, got {len(cells)} — {line[:200]!r}"
        )
    row = dict(zip(columns, cells, strict=False))
    qid = _extract_qid(row.get("item", ""))
    if qid is None:
        return None
    row["_qid"] = qid
    return row


def _parse_lines(lines: Iterable[str]) -> Iterator[WikidataRecord]:
    """Aggregate TSV rows by QID. SPARQL UNION emits one row per matching
    sub-pattern, so a single Wikidata entity with e.g. both an NGC and a
    PGC identifier produces two TSV rows. Merging here collapses them
    into one :class:`WikidataRecord` with the union of catalog IDs."""
    columns: list[str] | None = None
    aggregated: dict[str, _AggregatedRecord] = {}
    order: list[str] = []
    for i, raw_line in enumerate(lines, start=1):
        if not raw_line.strip():
            continue
        if columns is None:
            columns = _parse_header(raw_line)
            continue
        row = _parse_row(columns, raw_line, i)
        if row is None:
            continue
        qid = row["_qid"]
        agg = aggregated.get(qid)
        if agg is None:
            agg = _AggregatedRecord(qid=qid)
            aggregated[qid] = agg
            order.append(qid)
        agg.merge_row(row)

    for qid in order:
        yield aggregated[qid].finalize()


def parse_wikidata_tsv(path: Path) -> Iterator[WikidataRecord]:
    """Yield :class:`WikidataRecord` objects from a SPARQL-TSV file."""
    with path.open("r", encoding="utf-8", newline="") as fh:
        yield from _parse_lines(fh)


def parse_wikidata_tsv_text(text: str) -> Iterator[WikidataRecord]:
    """Version of :func:`parse_wikidata_tsv` for in-memory TSV (tests)."""
    yield from _parse_lines(text.splitlines(keepends=True))
