"""Wikidata SPARQL fetcher for DSO external references.

Hits the Wikidata Query Service (``query.wikidata.org/sparql``) with a
SPARQL query that returns every entity typed as an astronomical object
and carrying at least one catalog cross-reference NightCrate recognises
(NGC, Messier, Sharpless 2, Barnard, PGC, UGC, plus the less-used
IC/Caldwell/Melotte/Collinder). The response is a TSV that lands
atomically in ``APP_DIR/catalogs/wikidata/`` with a ``version.json``
commit marker — same pattern as OpenNGC / VizieR / 50 MGC.

The matching layer is downstream (:mod:`wikidata_loader`); this module
only deals with retrieval and on-disk storage.

Wikidata's User-Agent policy requires a descriptive UA; we ship a
project-identifying string with a link to the repo so the SRE team can
reach maintainers if something misbehaves.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from nightcrate.catalog_loader._common import retry_with_backoff
from nightcrate.services import http_client

logger = logging.getLogger("nightcrate.catalog_loader.wikidata")

WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"

# Bumping this string invalidates any stored TSV with the prior value and
# forces a re-fetch on next admin Reload. Increment when the query below
# changes shape in a way that affects the parser contract.
QUERY_VERSION = "v1"

# Smallest plausible TSV. Anything shorter indicates an error page
# masquerading as a success.
_MIN_BODY_BYTES = 1024

# Wikidata's 60s default works for the query but we give generous headroom
# to accommodate slow mirror hops and the occasional spike.
_DOWNLOAD_TIMEOUT_S = 180.0

# Tuple constant (see CLAUDE.md py314 ruff-format except note).
_VERSION_JSON_ERRS: tuple[type[BaseException], ...] = (json.JSONDecodeError, OSError)


def user_agent(app_version: str) -> str:
    """Compose the User-Agent string sent with every Wikidata request."""
    return f"NightCrate/{app_version} (https://github.com/fbaptiste/nightcrate)"


# ── SPARQL query ────────────────────────────────────────────────────────────
#
# The query returns one row per (Wikidata entity × catalog-code hit).
# Identifiers NightCrate uses are surfaced via three patterns:
#
#   1. The canonical ``P528`` (catalog code) + ``P972`` (catalog) qualifier
#      pattern, which is how Wikidata stores most catalog IDs. We filter
#      P972 to catalog Q-items NightCrate recognises.
#
#   2. Three direct-ID "shortcut" properties that appear on a meaningful
#      fraction of entities and can be pulled in one hop:
#        P3208 — NGC number
#        P4095 — PGC number
#        P6340 — UGC number
#
#   3. English Wikipedia sitelink (language-specific in the schema; we
#      restrict to ``en`` for MVP).
#
# An entity that has ONLY the direct-ID properties but no P528 row still
# surfaces — we emit a row per entity-level grouping and fold catalog
# codes onto it downstream.
#
# Verified live against Wikidata (2026-04-22):
#   Q13903 Orion Nebula → messier=M 42, ngc=1976, sh2=SH 2-281
#   Q2469 Andromeda Galaxy → messier=M 31, ngc=224, pgc=2557, ugc=454
#   Q14271 Horsehead Nebula → barnard=Barnard 33
#
# Catalog Q-items (verified on live entities):
#   Q14530 Messier object
#   Q14534 New General Catalogue
#   Q190553 Index Catalogue           (not verified on a live sample; included
#                                      for coverage — most IC DSOs also have
#                                      an NGC/Messier cross-ref, so miss is
#                                      tolerable)
#   Q14536 Caldwell catalogue         (not verified; same note)
#   Q66381095 Sharpless catalogue 2
#   Q3247327 Barnard Catalogue
#   Q1479861 Principal Galaxies Catalogue
#   Q615925  Uppsala General Catalogue
#
# Astro-object type filter (wdt:P31/wdt:P279*):
#   Q6999 astronomical object
#   Q13381402 deep-sky object
#   Q318 galaxy
#   Q204107 nebula
#   Q11387 star cluster
#   Q22247 planetary nebula
#   Q71963409 H II region

_SPARQL_QUERY = """
SELECT DISTINCT ?item ?itemLabel
       ?ngc_id ?pgc_id ?ugc_id
       ?msg ?ic ?cal ?sh2 ?bar
       ?enwiki_title
WHERE {
  # At least one recognised catalog identifier must be present.
  #
  # No ``wdt:P31/wdt:P279*`` class filter: the catalog-ID presence is
  # itself a tight astronomical-object filter, and the transitive
  # subclass closure from Q6999 was expensive enough to trip the
  # Wikidata Query Service's 60s timeout.
  {
    { ?item wdt:P3208 ?ngc_id . }
    UNION
    { ?item wdt:P4095 ?pgc_id . }
    UNION
    { ?item wdt:P6340 ?ugc_id . }
    UNION
    {
      ?item p:P528 ?s0 . ?s0 pq:P972 ?catalog0 .
      VALUES ?catalog0 {
        wd:Q14530 wd:Q190553 wd:Q14536 wd:Q66381095 wd:Q3247327
      }
    }
  }

  # Pull the canonical-form catalog codes for the five catalogs without
  # a direct-ID shortcut property. (NGC / PGC / UGC are already covered
  # by P3208 / P4095 / P6340 above, so their P528 duplicates are not
  # needed here.)
  OPTIONAL { ?item p:P528 ?m1 . ?m1 ps:P528 ?msg . ?m1 pq:P972 wd:Q14530 . }
  OPTIONAL { ?item p:P528 ?i1 . ?i1 ps:P528 ?ic  . ?i1 pq:P972 wd:Q190553 . }
  OPTIONAL { ?item p:P528 ?c1 . ?c1 ps:P528 ?cal . ?c1 pq:P972 wd:Q14536 . }
  OPTIONAL { ?item p:P528 ?s1 . ?s1 ps:P528 ?sh2 . ?s1 pq:P972 wd:Q66381095 . }
  OPTIONAL { ?item p:P528 ?b1 . ?b1 ps:P528 ?bar . ?b1 pq:P972 wd:Q3247327 . }

  # English Wikipedia sitelink (optional — many entities lack an article).
  # The enwiki URL is built client-side from ?enwiki_title (spaces →
  # underscores) — doing that in SPARQL via REPLACE+BIND added
  # measurable runtime overhead on every row.
  OPTIONAL {
    ?enwiki_article schema:about ?item ;
                    schema:isPartOf <https://en.wikipedia.org/> ;
                    schema:name ?enwiki_title .
  }

  SERVICE wikibase:label { bd:serviceParam wikibase:language "en" . }
}
"""


def sparql_query() -> str:
    """Return the SPARQL query body — exposed for tests and admin probes."""
    return _SPARQL_QUERY


# ── Result shape ────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class WikidataFetchResult:
    output_path: Path
    sha256: str
    size_bytes: int
    fetched_at: str
    query_version: str


# ── Version bookkeeping ─────────────────────────────────────────────────────


def _write_version_json(
    wikidata_dir: Path,
    result: WikidataFetchResult,
) -> Path:
    path = wikidata_dir / "version.json"
    payload = {
        "source_id": "wikidata_external_refs",
        "fetched_at": result.fetched_at,
        "sha256": result.sha256,
        "size_bytes": result.size_bytes,
        "query_version": result.query_version,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def read_installed_version(catalogs_root: Path) -> dict:
    """Return the parsed ``wikidata/version.json`` or an empty dict."""
    path = catalogs_root / "wikidata" / "version.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except _VERSION_JSON_ERRS:
        return {}


# ── Shape verification ──────────────────────────────────────────────────────


def _verify_tsv_shape(path: Path) -> None:
    """Smoke-check: first non-comment line must be a TSV header we recognise."""
    with path.open("r", encoding="utf-8", newline="") as fh:
        for line in fh:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            # SPARQL TSV header always starts with ``?item``.
            if not line.startswith("?item"):
                raise ValueError(
                    f"{path}: expected SPARQL TSV header starting with '?item', got {line[:80]!r}"
                )
            if "\t" not in line:
                raise ValueError(f"{path}: expected tab-separated columns, got {line[:80]!r}")
            return
        raise ValueError(f"{path}: no header line found")


# ── Fetch ───────────────────────────────────────────────────────────────────


async def fetch_wikidata_external_refs(
    catalogs_root: Path,
    *,
    app_version: str,
) -> WikidataFetchResult:
    """Download the Wikidata SPARQL TSV atomically into *catalogs_root*/wikidata.

    Flow:
      1. GET the SPARQL query result as TSV to ``<wikidata>/.download/dso_external_refs.tsv``.
      2. Smoke-check the header shape.
      3. Drop any stale ``wikidata/version.json`` so a crash between rename
         and version write leaves the install reporting "Not loaded".
      4. Atomic rename into place.
      5. Write the new ``version.json`` as the commit marker.
    """
    wikidata_dir = catalogs_root / "wikidata"
    tmp_dir = wikidata_dir / ".download"
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    tmp_path = tmp_dir / "dso_external_refs.tsv"
    final_path = wikidata_dir / "dso_external_refs.tsv"

    async def _download() -> bytes:
        # Wikidata's SPARQL endpoint drives format via ``Accept`` content
        # negotiation; the alternate ``format=`` query param is ignored when
        # ``Accept`` is set, and using both together was observed to fall
        # back to XML (the default) instead of respecting our preference.
        response = await http_client.get(
            WIKIDATA_SPARQL_URL,
            params={"query": _SPARQL_QUERY},
            headers={
                "User-Agent": user_agent(app_version),
                "Accept": "text/tab-separated-values",
            },
            label="wikidata:sparql",
            follow_redirects=True,
            timeout=_DOWNLOAD_TIMEOUT_S,
        )
        if response.status_code >= 400:
            raise RuntimeError(
                f"Wikidata SPARQL returned {response.status_code}: "
                f"{response.text[:200] if response.text else '(empty)'}"
            )
        content = response.content
        if not content:
            raise RuntimeError("Wikidata SPARQL returned empty body")
        if len(content) < _MIN_BODY_BYTES:
            raise RuntimeError(f"Wikidata SPARQL body suspiciously short ({len(content)} bytes)")
        tmp_path.write_bytes(content)
        return content

    try:
        content = await retry_with_backoff(
            _download,
            label="fetch:wikidata",
            logger=logger,
        )
        _verify_tsv_shape(tmp_path)

        # Invalidate the commit marker before renaming.
        version_json = wikidata_dir / "version.json"
        version_json.unlink(missing_ok=True)

        tmp_path.replace(final_path)

        result = WikidataFetchResult(
            output_path=final_path,
            sha256=hashlib.sha256(content).hexdigest(),
            size_bytes=len(content),
            fetched_at=datetime.now(UTC).isoformat(timespec="seconds"),
            query_version=QUERY_VERSION,
        )
        _write_version_json(wikidata_dir, result)

        logger.info(
            "[wikidata] downloaded %d bytes → %s",
            result.size_bytes,
            final_path,
        )
        return result
    finally:
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)
