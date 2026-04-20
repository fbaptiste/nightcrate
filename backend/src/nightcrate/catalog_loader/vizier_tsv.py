"""Parse VizieR's ``asu-tsv`` export format.

The wire format looks like::

    #
    # COPYRIGHT ...
    # VizieR ...
    #
    _RAJ2000 _DEJ2000 Sh2 Diam Brgtns ...
    deg      deg      --  arcmin ...
    -------- -------- --- ------ ...
    83.8221  -5.3911  281 90     ...
    ...

- ``#``-prefixed metadata at the top (variable length)
- One line of tab-separated column names
- One line of units (tab-separated, sometimes empty)
- One line of hyphen separators
- Data rows, tab-separated

We read by column name — VizieR occasionally rearranges columns between
export tool versions, so positional access would be fragile.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path


def parse_vizier_tsv(path: Path) -> Iterator[dict[str, str | None]]:
    """Yield one dict per data row, keyed by column name.

    Empty cells are yielded as ``None``; non-empty cells are stripped
    strings. Raises ``ValueError`` if the header row is missing or the
    separator row doesn't follow the units row as expected.
    """
    with path.open("r", encoding="utf-8", newline="") as fh:
        lines = (line.rstrip("\r\n") for line in fh)

        # 1. Skip all leading metadata.
        header_line: str | None = None
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            header_line = line
            break

        if header_line is None:
            raise ValueError(f"{path}: no header row found")

        columns = header_line.split("\t")

        # 2. Skip the units row.
        units_line = next(lines, None)
        if units_line is None:
            raise ValueError(f"{path}: missing units row after header")

        # 3. Skip the hyphen separator row. Accept either hyphens or a blank
        # line here — different VizieR exports vary slightly.
        separator_line = next(lines, None)
        if separator_line is None:
            raise ValueError(f"{path}: missing separator row after units")

        # 4. Data rows. A trailing ``#END`` marker or blank line terminates.
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                break
            values = line.split("\t")
            row: dict[str, str | None] = {}
            for i, name in enumerate(columns):
                value = values[i].strip() if i < len(values) else ""
                row[name] = value or None
            yield row
