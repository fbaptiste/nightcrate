"""CLI entry point for the seed loader.

Usage:
    python -m nightcrate.seed_loader --db nightcrate.sqlite --csv-root path/to/seed

Exit codes:
    0 — success
    1 — loader errors
    2 — CLI usage error (bad flags, missing paths)
    3 — hash contract version mismatch
"""

import argparse
import dataclasses
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from nightcrate.seed_loader import SeedReport, load_all

# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------


def _format_human(report: SeedReport) -> str:
    lines: list[str] = [f"Seed loader: {report.mode} mode"]
    for table_name, tr in report.per_table.items():
        parts: list[str] = []
        if tr.inserted:
            parts.append(f"{tr.inserted} inserted")
        if tr.updated:
            parts.append(f"{tr.updated} updated")
        if tr.unchanged:
            parts.append(f"{tr.unchanged} unchanged")
        if tr.skipped_user_modified:
            parts.append(f"{len(tr.skipped_user_modified)} skipped (user-modified)")
        if tr.skipped_corrupt:
            parts.append(f"{len(tr.skipped_corrupt)} skipped (corrupt source)")
        if tr.orphaned:
            parts.append(f"{len(tr.orphaned)} orphaned")
        if parts:
            lines.append(f"  {table_name}: {', '.join(parts)}")

    total_inserted = sum(tr.inserted for tr in report.per_table.values())
    total_updated = sum(tr.updated for tr in report.per_table.values())
    lines.append(f"\nOK — {total_inserted} inserted, {total_updated} updated")
    return "\n".join(lines)


def _report_to_dict(report: SeedReport) -> dict:
    """Convert SeedReport dataclass to a JSON-serialisable dict."""

    def _convert(obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
            return {k: _convert(v) for k, v in dataclasses.asdict(obj).items()}
        if isinstance(obj, dict):
            return {k: _convert(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_convert(i) for i in obj]
        return obj

    return _convert(report)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m nightcrate.seed_loader",
        description="Load equipment seed data from CSV files into the NightCrate database.",
    )
    parser.add_argument("--db", required=True, metavar="PATH", help="Path to SQLite database")
    parser.add_argument(
        "--csv-root", required=True, metavar="PATH", help="Path to seed CSV directory"
    )
    parser.add_argument(
        "--update", action="store_true", help="Force update mode (default: auto-detect)"
    )
    parser.add_argument(
        "--first-run", action="store_true", help="Force first-run mode (default: auto-detect)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute report then roll back — no changes are written",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Log per-row decisions (not yet implemented)"
    )
    parser.add_argument("--json", action="store_true", help="Emit SeedReport as JSON on stdout")

    args = parser.parse_args()

    # ------------------------------------------------------------------
    # Mutual exclusion
    # ------------------------------------------------------------------
    if args.update and args.first_run:
        parser.error("--update and --first-run are mutually exclusive")

    # ------------------------------------------------------------------
    # Path validation
    # ------------------------------------------------------------------
    db_path = Path(args.db)
    csv_root = Path(args.csv_root)

    if not db_path.exists():
        print(f"error: database not found: {db_path}", file=sys.stderr)
        sys.exit(2)

    if not csv_root.exists() or not csv_root.is_dir():
        print(f"error: csv-root not found or not a directory: {csv_root}", file=sys.stderr)
        sys.exit(2)

    # ------------------------------------------------------------------
    # Determine mode
    # ------------------------------------------------------------------
    if args.update:
        mode = "update"
    elif args.first_run:
        mode = "first_run"
    else:
        mode = "auto"

    # ------------------------------------------------------------------
    # Run loader
    # ------------------------------------------------------------------
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    try:
        conn.execute("BEGIN")
        try:
            report = load_all(conn, csv_root, mode=mode)  # type: ignore[arg-type]
        except RuntimeError as exc:
            msg = str(exc)
            # Detect hash contract mismatch
            if "Hash contract version mismatch" in msg:
                print(f"error: {msg}", file=sys.stderr)
                conn.rollback()
                sys.exit(3)
            print(f"error: {msg}", file=sys.stderr)
            conn.rollback()
            sys.exit(1)

        if args.dry_run:
            conn.rollback()
        else:
            conn.commit()

    finally:
        conn.close()

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------
    if args.json:
        print(json.dumps(_report_to_dict(report), indent=2))
    else:
        print(_format_human(report))

    sys.exit(0)


if __name__ == "__main__":
    main()
