"""Store alternate DSO names separately from the preferred name."""

from yoyo import step

__depends__ = {"0066.more_catalogs"}


def _split_names(value: str) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for part in value.split(","):
        name = part.strip()
        key = name.casefold()
        if name and key not in seen:
            names.append(name)
            seen.add(key)
    return names


def _apply(conn) -> None:
    conn.execute(
        """
        CREATE TABLE dso_other_name (
            id       INTEGER PRIMARY KEY,
            dso_id   INTEGER NOT NULL REFERENCES dso(id) ON DELETE CASCADE,
            name     TEXT NOT NULL CHECK (length(trim(name)) > 0 AND instr(name, ',') = 0),
            position INTEGER NOT NULL CHECK (position >= 1),
            UNIQUE (dso_id, name COLLATE NOCASE),
            UNIQUE (dso_id, position)
        )
        """
    )
    conn.execute("ALTER TABLE dso_group ADD COLUMN common_name TEXT")

    rows = conn.execute(
        "SELECT id, common_name FROM dso WHERE instr(common_name, ',') > 0"
    ).fetchall()
    for dso_id, value in rows:
        names = _split_names(value)
        preferred_name = names[0] if names else None
        conn.execute(
            "UPDATE dso SET common_name = ? WHERE id = ?",
            (preferred_name, dso_id),
        )
        conn.executemany(
            "INSERT INTO dso_other_name (dso_id, name, position) VALUES (?, ?, ?)",
            ((dso_id, name, position) for position, name in enumerate(names[1:], start=1)),
        )


def _rollback(conn) -> None:
    conn.execute("DROP TABLE dso_other_name")


steps = [step(_apply, _rollback)]
