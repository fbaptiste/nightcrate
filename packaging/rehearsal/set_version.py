#!/usr/bin/env python3
"""Set all build-time versions for a disposable rehearsal build."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def replace_toml(path: Path, version: str, section: str) -> None:
    text = path.read_text(encoding="utf-8")
    pattern = rf"(?ms)(^\[{re.escape(section)}\].*?^version\s*=\s*)\"[^\"]+\""
    changed, count = re.subn(pattern, rf'\g<1>"{version}"', text, count=1)
    if count != 1:
        raise RuntimeError(f"could not set {section}.version in {path}")
    path.write_text(changed, encoding="utf-8")


def replace_json(path: Path, version: str) -> None:
    value = json.loads(path.read_text(encoding="utf-8"))
    value["version"] = version
    if isinstance(value.get("packages"), dict) and isinstance(
        value["packages"].get(""), dict
    ):
        value["packages"][""]["version"] = version
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 2 or not re.fullmatch(r"\d+\.\d+\.\d+", sys.argv[1]):
        print("usage: set_version.py X.Y.Z", file=sys.stderr)
        return 2
    version = sys.argv[1]
    (ROOT / "VERSION").write_text(version + "\n", encoding="utf-8")
    replace_toml(ROOT / "backend/pyproject.toml", version, "project")
    replace_toml(ROOT / "packaging/shell/src-tauri/Cargo.toml", version, "package")
    replace_json(ROOT / "frontend/package.json", version)
    replace_json(ROOT / "frontend/package-lock.json", version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
