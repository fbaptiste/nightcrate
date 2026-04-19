"""Unit tests for the OpenNGC `Identifiers` column cross-reference parser."""

from __future__ import annotations

from nightcrate.catalog_loader.crossref_parser import parse_other_id


def _as_tuples(raw: str | None) -> list[tuple[str, str]]:
    return [(r.catalog, r.identifier) for r in parse_other_id(raw)]


def test_empty_input_returns_empty_list():
    assert parse_other_id(None) == []
    assert parse_other_id("") == []


def test_simple_two_token_parse():
    assert _as_tuples("C 020, LBN 373") == [("caldwell", "20"), ("lbn", "373")]


def test_mixed_galaxy_catalogs():
    result = _as_tuples("MCG-00-07-079, PGC 10266, UGC 2271")
    assert result == [
        ("mcg", "00-07-079"),
        ("pgc", "10266"),
        ("ugc", "2271"),
    ]


def test_sharpless_hyphen_form():
    assert _as_tuples("Sh2-281, LBN 974") == [
        ("sharpless2", "281"),
        ("lbn", "974"),
    ]


def test_sharpless_beats_single_s():
    # Longest-match: Sh2 must resolve before a hypothetical single-letter S.
    assert _as_tuples("Sh2-001") == [("sharpless2", "1")]


def test_unknown_prefix_silently_dropped():
    assert _as_tuples("XYZ 123, 2MASX J12345, SDSS J9999") == []


def test_unknown_mixed_with_known():
    # PGC 000778 → leading zeros stripped to 778. MCG identifier has a leading
    # dash and compound digits — not purely numeric, so it passes through.
    assert _as_tuples("2MASX J00110081-1249206, MCG -02-01-031, PGC 000778") == [
        ("mcg", "-02-01-031"),
        ("pgc", "778"),
    ]


def test_barnard_requires_digit_or_whitespace():
    # 'BD+12' starts with 'B' followed by 'D' — NOT whitespace/digit, so must drop.
    # 'B 33' and 'B33' must match.
    assert _as_tuples("BD+12 345") == []
    assert _as_tuples("B 33") == [("barnard", "33")]
    assert _as_tuples("B33") == [("barnard", "33")]


def test_caldwell_single_letter_guard():
    # 'C 20' matches Caldwell; 'CRL 2688' does NOT (C followed by R, not ws/digit).
    assert _as_tuples("C 20") == [("caldwell", "20")]
    assert _as_tuples("CRL 2688") == []


def test_whitespace_tolerance():
    assert _as_tuples("  PGC   12345  ,   UGC 456  ") == [
        ("pgc", "12345"),
        ("ugc", "456"),
    ]


def test_hickson_longer_prefix_wins():
    assert _as_tuples("HCG 44") == [("hickson", "44")]


def test_identifier_preserved_verbatim():
    # Identifiers with internal dashes, plus signs, or letters should pass through.
    assert _as_tuples("MCG +03-01-029") == [("mcg", "+03-01-029")]
