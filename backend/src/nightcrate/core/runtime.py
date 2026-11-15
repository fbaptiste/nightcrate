"""Process-wide runtime state shared by source and installed entrypoints."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Literal

InstallKind = Literal["installed", "source"]

install_kind: InstallKind = "source"
production: bool = False
last_activation_backup: Path | None = None
log_dir: Path | None = None


def app_version() -> str:
    """Return the installed package version."""
    try:
        return version("nightcrate")
    except PackageNotFoundError:
        return "unknown"


def report_step(
    step: Literal["starting", "backing_up", "upgrading"],
    workspace_name: str | None = None,
) -> None:
    """Report a machine-readable startup step to the installed shell."""
    if production:
        print(
            "NIGHTCRATE_STEP "
            + json.dumps({"step": step, "workspace": workspace_name}, separators=(",", ":")),
            flush=True,
        )


def start_heartbeat() -> Callable[[], None]:
    """Print startup heartbeats until the returned function is called."""
    stopped = threading.Event()

    def heartbeat() -> None:
        while not stopped.wait(5):
            print("NIGHTCRATE_ALIVE", flush=True)

    threading.Thread(target=heartbeat, name="nightcrate-heartbeat", daemon=True).start()
    return stopped.set
