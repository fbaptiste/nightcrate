#!/usr/bin/env python3
"""Validate a frozen NightCrate backend before it is bundled."""

from __future__ import annotations

import hashlib
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_MIGRATIONS = ROOT / "backend" / "src" / "nightcrate" / "db" / "migrations"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree(path: Path) -> dict[str, str]:
    return {
        item.relative_to(path).as_posix(): digest(item)
        for item in path.rglob("*")
        if item.is_file()
    }


def check_build(build_dir: Path) -> list[str]:
    failures: list[str] = []
    executable = build_dir / (
        "nightcrate-backend.exe" if sys.platform == "win32" else "nightcrate-backend"
    )
    frozen_migrations = build_dir / "lib" / "nightcrate" / "db" / "migrations"

    if not executable.is_file():
        failures.append(f"missing backend executable: {executable}")
    if not frozen_migrations.is_dir():
        failures.append(f"missing migrations folder: {frozen_migrations}")
    elif tree(frozen_migrations) != tree(SOURCE_MIGRATIONS):
        source = tree(SOURCE_MIGRATIONS)
        frozen = tree(frozen_migrations)
        for name in sorted(source.keys() | frozen.keys()):
            if source.get(name) != frozen.get(name):
                failures.append(f"migration differs: {name}")

    if sys.platform == "darwin":
        dylibs = list(build_dir.rglob("libmlx.dylib"))
        if not dylibs:
            failures.append("missing libmlx.dylib")
        for dylib in dylibs:
            if not (dylib.parent / "mlx.metallib").is_file():
                failures.append(
                    f"mlx.metallib is not beside {dylib.relative_to(build_dir)}"
                )

    if executable.is_file():
        result = subprocess.run(
            [str(executable), "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        with (ROOT / "backend" / "pyproject.toml").open("rb") as handle:
            expected = tomllib.load(handle)["project"]["version"]
        actual = result.stdout.strip()
        if result.returncode != 0 or actual != expected:
            failures.append(
                f"backend version mismatch: expected {expected!r}, got {actual!r} "
                f"(exit {result.returncode})"
            )
    return failures


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: check_build.py <frozen-backend-dir>", file=sys.stderr)
        return 2
    failures = check_build(Path(sys.argv[1]).resolve())
    for failure in failures:
        print(f"ERROR: {failure}", file=sys.stderr)
    if failures:
        return 1
    print("Frozen backend checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
