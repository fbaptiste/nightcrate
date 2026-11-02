from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest

from nightcrate.services.dso_display import (
    CONSTELLATION_NAMES,
    DSO_TYPE_DISPLAY,
    label_sort_expression,
)


def _typescript_record(path: Path, export_name: str) -> dict[str, str]:
    source = path.read_text(encoding="utf-8")
    match = re.search(
        rf"export const {export_name}: Record<string, string> = \{{(.*?)\n\}};",
        source,
        flags=re.DOTALL,
    )
    assert match is not None
    result: dict[str, str] = {}
    entry = re.compile(r'^\s*(?:"([^"]+)"|([^:\s]+)):\s*"([^"]*)",\s*$')
    for line in match.group(1).splitlines():
        if not line.strip():
            continue
        parsed = entry.match(line)
        assert parsed is not None, line
        quoted_key, bare_key, value = parsed.groups()
        result[quoted_key or bare_key] = value
    return result


def test_backend_label_maps_match_frontend():
    root = Path(__file__).resolve().parents[3]
    assert DSO_TYPE_DISPLAY == _typescript_record(
        root / "frontend/src/lib/dsoTypeNames.ts", "DSO_TYPE_DISPLAY"
    )
    assert CONSTELLATION_NAMES == _typescript_record(
        root / "frontend/src/lib/constellations.ts", "CONSTELLATION_NAMES"
    )


@pytest.mark.parametrize(
    ("labels", "values", "expected"),
    [
        (DSO_TYPE_DISPLAY, ["*", "G", "Unknown", ""], ["G", "*", "Unknown", ""]),
        (
            CONSTELLATION_NAMES,
            ["CMa", "Cam", "Unknown", None],
            ["Cam", "CMa", "Unknown", None],
        ),
    ],
)
def test_label_expression_sorts_display_labels_with_fallback_and_nulls_last(
    labels, values, expected
):
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE values_to_sort (value TEXT)")
    conn.executemany("INSERT INTO values_to_sort VALUES (?)", ((value,) for value in values))
    expression, params = label_sort_expression("value", labels)
    rows = conn.execute(
        f"SELECT value FROM values_to_sort ORDER BY {expression} ASC NULLS LAST",  # nosec B608
        params,
    ).fetchall()
    assert [row[0] for row in rows] == expected

    rows = conn.execute(
        f"SELECT value FROM values_to_sort ORDER BY {expression} DESC NULLS LAST",  # nosec B608
        params,
    ).fetchall()
    assert [row[0] for row in rows][-1] in {None, ""}
