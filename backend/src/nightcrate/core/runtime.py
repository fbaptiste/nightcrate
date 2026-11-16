"""Process-wide runtime state shared by source and installed entrypoints."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Literal

InstallKind = Literal["installed", "source"]

install_kind: InstallKind = "source"
production: bool = False
last_activation_backup: Path | None = None
log_dir: Path | None = None
admitted_work: int = 0
install_lease_until: datetime | None = None
install_owner: str | None = None
install_barrier: bool = False


def utcnow() -> datetime:
    return datetime.now(UTC)


def install_is_reserved(now: datetime | None = None) -> bool:
    now = now or utcnow()
    return install_barrier or (install_lease_until is not None and now < install_lease_until)


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
