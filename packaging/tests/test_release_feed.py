from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from release_feed import platform_entry  # noqa: E402


def test_only_macos_feed_entry_carries_configured_minimum() -> None:
    root = Path(__file__).parents[2]
    config = json.loads(
        (root / "packaging/shell/src-tauri/tauri.conf.json").read_text(encoding="utf-8")
    )

    mac = platform_entry(
        "darwin-aarch64", url="https://example.test/mac", signature="mac", tauri_config=config
    )
    linux = platform_entry(
        "linux-x86_64", url="https://example.test/linux", signature="linux", tauri_config=config
    )
    windows = platform_entry(
        "windows-x86_64",
        url="https://example.test/windows",
        signature="windows",
        tauri_config=config,
    )

    assert mac["min_os"] == "14.0"
    assert "min_os" not in linux
    assert "min_os" not in windows


def test_frozen_backend_explicitly_includes_raw_runtime_packages() -> None:
    root = Path(__file__).parents[2]
    freeze_source = (root / "packaging/freeze.py").read_text(encoding="utf-8")

    assert '"rawpy",' in freeze_source
    assert '"exiv2",' in freeze_source
