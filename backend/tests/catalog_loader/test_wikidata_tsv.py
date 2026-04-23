"""Tests for the Wikidata SPARQL TSV parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from nightcrate.catalog_loader.wikidata_tsv import (
    WikidataParseError,
    build_search_keys,
    parse_wikidata_tsv,
    parse_wikidata_tsv_text,
)

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "catalogs" / "wikidata"


_HEADER = (
    "?item\t?itemLabel\t?ngc_id\t?pgc_id\t?ugc_id\t?msg\t?ic\t?cal\t?sh2\t?bar"
    "\t?simbad_id\t?enwiki_title\n"
)


def _row(
    *,
    item: str = "<http://www.wikidata.org/entity/Q1>",
    label: str = '"X"@en',
    ngc_id: str = "",
    pgc_id: str = "",
    ugc_id: str = "",
    msg: str = "",
    ic: str = "",
    cal: str = "",
    sh2: str = "",
    bar: str = "",
    simbad_id: str = "",
    enwiki_title: str = "",
) -> str:
    return (
        "\t".join(
            [
                item,
                label,
                ngc_id,
                pgc_id,
                ugc_id,
                msg,
                ic,
                cal,
                sh2,
                bar,
                simbad_id,
                enwiki_title,
            ]
        )
        + "\n"
    )


def test_parse_canonical_mini_fixture():
    records = list(parse_wikidata_tsv(FIXTURE_DIR / "mini_wikidata.tsv"))
    # 4 distinct entities, aggregated from 8 TSV rows (SPARQL UNION emits
    # one row per matching sub-pattern).
    assert len(records) == 4

    by_qid = {r.qid: r for r in records}

    orion = by_qid["Q13903"]
    assert orion.label == "Orion Nebula"
    assert orion.qid_url == "https://www.wikidata.org/wiki/Q13903"
    assert orion.catalog_ids == {"ngc": "1976", "sharpless2": "281"}
    assert orion.enwiki_title == "Orion Nebula"
    assert orion.enwiki_url == "https://en.wikipedia.org/wiki/Orion_Nebula"
    # Orion has a SIMBAD ID on Wikidata.
    assert orion.simbad_id == "NAME ORI NEB"

    andromeda = by_qid["Q2469"]
    assert andromeda.catalog_ids["ngc"] == "224"
    assert andromeda.catalog_ids["pgc"] == "2557"
    assert andromeda.catalog_ids["ugc"] == "454"
    assert andromeda.catalog_ids["messier"] == "31"
    assert andromeda.enwiki_url == "https://en.wikipedia.org/wiki/Andromeda_Galaxy"
    assert andromeda.simbad_id == "M 31"

    # Entity with ngc_id only, no enwiki sitelink, no SIMBAD.
    helix = by_qid["Q888888"]
    assert helix.catalog_ids == {"ngc": "7293"}
    assert helix.enwiki_title is None
    assert helix.enwiki_url is None
    assert helix.simbad_id is None


def test_build_search_keys_produces_dso_designation_form():
    records = list(parse_wikidata_tsv(FIXTURE_DIR / "mini_wikidata.tsv"))
    by_qid = {r.qid: r for r in records}

    # Orion has NGC 1976 + Sh2-281, so search_keys = ["ngc1976", "sh2281"].
    orion_keys = build_search_keys(by_qid["Q13903"])
    assert sorted(orion_keys) == ["ngc1976", "sh2281"]

    # Andromeda: M 31, NGC 224, PGC 2557, UGC 454 (aggregated across rows).
    andromeda_keys = set(build_search_keys(by_qid["Q2469"]))
    assert {"m31", "ngc224", "pgc2557", "ugc454"} <= andromeda_keys


def test_parse_aggregates_multiple_rows_for_same_qid():
    """SPARQL UNION emits one row per sub-pattern match; an entity with
    both an NGC (P3208) and a PGC (P4095) identifier is spread across
    TWO rows. Parser must aggregate into ONE record."""
    text = (
        _HEADER
        + _row(ngc_id='"224"', label='"Andromeda"@en', enwiki_title='"Andromeda Galaxy"@en')
        + _row(pgc_id='"2557"', label='"Andromeda"@en', enwiki_title='"Andromeda Galaxy"@en')
    )
    records = list(parse_wikidata_tsv_text(text))
    assert len(records) == 1
    rec = records[0]
    assert rec.catalog_ids == {"ngc": "224", "pgc": "2557"}
    assert rec.enwiki_title == "Andromeda Galaxy"
    assert rec.enwiki_url == "https://en.wikipedia.org/wiki/Andromeda_Galaxy"


def test_parse_strips_leading_zeros():
    text = _HEADER + _row(ngc_id='"00224"', label='"Zero-padded"@en')
    records = list(parse_wikidata_tsv_text(text))
    assert len(records) == 1
    assert records[0].catalog_ids == {"ngc": "224"}


def test_parse_strips_sharpless_prefix_variants():
    """Wikidata stores Sharpless entries as ``'SH 2-281'``, ``'Sh 2-281'``,
    or ``'Sh2-281'`` depending on the editor. All three must normalise to
    the bare number."""
    for form in ("SH 2-281", "Sh 2-281", "Sh2-281"):
        text = _HEADER + _row(sh2=f'"{form}"', label='"X"@en')
        records = list(parse_wikidata_tsv_text(text))
        assert records[0].catalog_ids == {"sharpless2": "281"}, f"failed for {form}"


def test_parse_label_matching_qid_treated_as_none():
    """``wikibase:label`` returns the QID as a fallback when the entity
    has no English label. Treat that as ``label=None``."""
    text = _HEADER + _row(
        item="<http://www.wikidata.org/entity/Q125818>",
        label='"Q125818"',  # No language tag — the fallback form
        ngc_id='"1483"',
    )
    records = list(parse_wikidata_tsv_text(text))
    assert records[0].label is None


def test_parse_builds_wikipedia_url_from_title():
    """The URL is built client-side: spaces in the title become
    underscores, no further escaping."""
    text = _HEADER + _row(
        ngc_id='"7293"',
        label='"Helix Nebula"@en',
        enwiki_title='"Helix Nebula (planetary nebula)"@en',
    )
    records = list(parse_wikidata_tsv_text(text))
    assert records[0].enwiki_title == "Helix Nebula (planetary nebula)"
    assert records[0].enwiki_url == "https://en.wikipedia.org/wiki/Helix_Nebula_(planetary_nebula)"


def test_parse_missing_column_in_header_raises():
    text = '?item\t?itemLabel\n<http://www.wikidata.org/entity/Q1>\t"foo"@en\n'
    with pytest.raises(WikidataParseError, match="missing column"):
        list(parse_wikidata_tsv_text(text))


def test_parse_wrong_column_count_raises():
    with pytest.raises(WikidataParseError, match="line 2"):
        list(parse_wikidata_tsv(FIXTURE_DIR / "mini_wikidata_malformed.tsv"))


def test_parse_empty_text_yields_nothing():
    assert list(parse_wikidata_tsv_text("")) == []


def test_parse_header_only_yields_nothing():
    assert list(parse_wikidata_tsv_text(_HEADER)) == []


def test_parse_drops_row_with_bad_qid():
    """Non-``Q\\d+`` value in the item column → skip that row silently."""
    text = _HEADER + _row(
        item="<http://example.com/not-a-qid>",
        label='"Bad"@en',
        ngc_id='"1"',
    )
    assert list(parse_wikidata_tsv_text(text)) == []


def test_parse_simbad_identifier_kept_verbatim():
    """SIMBAD IDs keep their Wikidata canonical form (including spaces
    and punctuation) — SIMBAD's name resolver accepts them directly."""
    text = _HEADER + _row(
        item="<http://www.wikidata.org/entity/Q2469>",
        label='"Andromeda Galaxy"@en',
        ngc_id='"224"',
        simbad_id='"M 31"',
    )
    records = list(parse_wikidata_tsv_text(text))
    assert len(records) == 1
    assert records[0].simbad_id == "M 31"


def test_parse_strips_whitespace_around_simbad():
    """Wikidata occasionally has stray whitespace around scalar IDs;
    the parser trims both ends."""
    text = _HEADER + _row(ngc_id='"224"', simbad_id='"  M 31  "')
    records = list(parse_wikidata_tsv_text(text))
    assert records[0].simbad_id == "M 31"


def test_parse_missing_simbad_yields_none():
    """Empty cells → simbad_id = None (not empty string)."""
    text = _HEADER + _row(ngc_id='"7293"')
    records = list(parse_wikidata_tsv_text(text))
    assert records[0].simbad_id is None
