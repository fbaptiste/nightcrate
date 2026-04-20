"""Unit tests for the VizieR TSV parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from nightcrate.catalog_loader.vizier_tsv import parse_vizier_tsv


def _write_tsv(tmp_path: Path, body: str, name: str = "in.tsv") -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def test_parses_minimal_tsv(tmp_path):
    path = _write_tsv(
        tmp_path,
        (
            "#\n"
            "# Some metadata\n"
            "#\n"
            "colA\tcolB\tcolC\n"
            "--\t--\t--\n"
            "--------\t--------\t--------\n"
            "1\talpha\t\n"
            "2\tbeta\tgamma\n"
        ),
    )
    rows = list(parse_vizier_tsv(path))
    assert rows == [
        {"colA": "1", "colB": "alpha", "colC": None},
        {"colA": "2", "colB": "beta", "colC": "gamma"},
    ]


def test_reads_by_column_name_shuffled(tmp_path):
    path = _write_tsv(
        tmp_path,
        ("colB\tcolA\n--\t--\n------\t------\nbeta\t1\ndelta\t2\n"),
    )
    rows = list(parse_vizier_tsv(path))
    assert rows[0]["colA"] == "1"
    assert rows[0]["colB"] == "beta"


def test_tolerates_dos_line_endings(tmp_path):
    body = "colA\tcolB\r\n--\t--\r\n------\t------\r\nhello\tworld\r\n"
    path = tmp_path / "dos.tsv"
    path.write_bytes(body.encode("utf-8"))
    rows = list(parse_vizier_tsv(path))
    assert rows == [{"colA": "hello", "colB": "world"}]


def test_stops_at_trailing_metadata(tmp_path):
    path = _write_tsv(
        tmp_path,
        ("colA\n--\n--\nalpha\n#END\nnever_reached\n"),
    )
    rows = list(parse_vizier_tsv(path))
    assert rows == [{"colA": "alpha"}]


def test_raises_on_missing_header(tmp_path):
    path = _write_tsv(tmp_path, "# only comments\n#\n")
    with pytest.raises(ValueError, match="no header"):
        list(parse_vizier_tsv(path))


def test_empty_fields_yield_none(tmp_path):
    path = _write_tsv(
        tmp_path,
        ("colA\tcolB\tcolC\n--\t--\t--\n---\t---\t---\nx\t\ty\n"),
    )
    rows = list(parse_vizier_tsv(path))
    assert rows[0]["colB"] is None
    assert rows[0]["colA"] == "x"
    assert rows[0]["colC"] == "y"
