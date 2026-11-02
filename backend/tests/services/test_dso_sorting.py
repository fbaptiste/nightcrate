from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from nightcrate.services.dso_sorting import catalog_rank, designation_sort_key

SORTED_DESIGNATIONS = [
    "B 33",
    "C 14",
    "ESO 107-2",
    "ESO 107-010",
    "IC 2",
    "M 2",
    "M 31",
    "Mel 1",
    "NGC 1",
    "NGC 1A",
    "NGC 2",
    "NGC 10",
    "PGC 143",
    "Sh2-2",
    "Sh2-155",
    "UGC 4305",
]


def test_designation_sort_key_orders_prefixes_numbers_suffixes_and_compounds():
    scrambled = list(reversed(SORTED_DESIGNATIONS))
    assert sorted(scrambled, key=designation_sort_key) == SORTED_DESIGNATIONS


def test_designation_sort_key_handles_case_zero_padding_and_numeric_extremes():
    values = [
        "pgc 100000000000000000000",
        "PGC 99999999999999999999",
        "NGC 00010",
        "ngc 2",
    ]
    assert sorted(values, key=designation_sort_key) == [
        "ngc 2",
        "NGC 00010",
        "PGC 99999999999999999999",
        "pgc 100000000000000000000",
    ]
    assert designation_sort_key("NGC 2") == designation_sort_key("ngc 0002")
    assert designation_sort_key(None) is None


def test_designation_sort_key_is_sqlite_safe():
    conn = sqlite3.connect(":memory:")
    conn.create_function("designation_key", 1, designation_sort_key, deterministic=True)
    conn.execute("CREATE TABLE names (name TEXT)")
    conn.executemany(
        "INSERT INTO names VALUES (?)",
        ((value,) for value in reversed(SORTED_DESIGNATIONS)),
    )
    rows = conn.execute("SELECT name FROM names ORDER BY designation_key(name)").fetchall()
    assert [row[0] for row in rows] == SORTED_DESIGNATIONS


def test_catalog_rank_prioritizes_primary_catalogs_then_uses_catalog_code():
    catalogs = ["sharpless2", "ic", "barnard", "caldwell", "ngc", "messier", "arp"]

    assert sorted(catalogs, key=lambda code: (catalog_rank(code), code)) == [
        "messier",
        "ngc",
        "ic",
        "caldwell",
        "arp",
        "barnard",
        "sharpless2",
    ]
    assert catalog_rank("unknown_future_catalog") == catalog_rank("arp")


def test_typescript_uses_the_shared_ordering_vectors():
    root = Path(__file__).resolve().parents[3]
    source = (root / "frontend/src/lib/designationSort.ts").read_text(encoding="utf-8")
    match = re.search(
        r"DESIGNATION_SORT_VECTORS = (\[.*?\]) as const;",
        source,
        flags=re.DOTALL,
    )
    assert match is not None
    vectors = json.loads(match.group(1))
    assert all(designation_sort_key(left) < designation_sort_key(right) for left, right in vectors)
