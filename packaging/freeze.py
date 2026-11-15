"""Build the production backend used by NightCrate installers."""

from __future__ import annotations

import shutil
import sys
import tomllib
from importlib import metadata
from pathlib import Path

from cx_Freeze import Executable, setup
from cx_Freeze.hooks._anyio_ import Hook as AnyioHook

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
BUILD_DIR = ROOT / "packaging" / "build" / "backend"
PYTHON_SITE = Path(sys.prefix) / "lib" / "python3.14" / "site-packages"


def _include_current_anyio(self, finder, module) -> None:
    """Work around cx_Freeze 8.7.4's stale AnyIO 4.13 hook."""
    del self, module
    finder.exclude_module("anyio.pytest_plugin")
    for name in (
        "anyio._backends._asyncio",
        "anyio.from_thread",
        "anyio.functools",
        "anyio.to_interpreter",
        "anyio.to_process",
        "anyio.to_thread",
    ):
        finder.include_module(name)


AnyioHook.anyio = _include_current_anyio


def package_version() -> str:
    with (BACKEND / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)["project"]["version"]


def gcc_runtime_dist_info() -> list[tuple[str, str]]:
    """Keep exact provider versions beside bundled GCC runtime libraries."""
    result: list[tuple[str, str]] = []
    for dist in metadata.distributions():
        if not any(
            Path(str(item))
            .name.lower()
            .startswith(("libgcc_s", "libgfortran", "libquadmath"))
            for item in dist.files or []
        ):
            continue
        dist_info = Path(dist._path)  # noqa: SLF001
        if not dist_info.name.endswith(".dist-info"):
            raise RuntimeError(
                f"GCC runtime provider {dist.metadata['Name']} has no dist-info directory"
            )
        result.append((str(dist_info), f"lib/{dist_info.name}"))
    return result


if BUILD_DIR.exists():
    shutil.rmtree(BUILD_DIR)

include_files: list[tuple[str, str]] = [
    (str(ROOT / "frontend" / "dist"), "frontend"),
    (
        str(BACKEND / "src" / "nightcrate" / "db" / "migrations"),
        "lib/nightcrate/db/migrations",
    ),
] + gcc_runtime_dist_info()
if sys.platform == "darwin":
    include_files.append(
        (str(PYTHON_SITE / "mlx" / "lib" / "mlx.metallib"), "lib/mlx.metallib")
    )

build_options = {
    "build_exe": str(BUILD_DIR),
    "packages": [
        "nightcrate",
        "uvicorn",
        "fastapi",
        "starlette",
        "anyio",
        "h11",
        "httptools",
        "websockets",
        "watchfiles",
        "aiosqlite",
        "yoyo",
        "astropy",
        "astropy_healpix",
        "numpy",
        "scipy",
        "sep",
        "imagecodecs",
        "tifffile",
        "PIL",
        "bottleneck",
        "py7zr",
        "timezonefinder",
        "tzdata",
        "lz4",
        "zstandard",
        "defusedxml",
        "httpx",
        "platformdirs",
        "multipart",
    ]
    + (["mlx"] if sys.platform == "darwin" else []),
    "zip_include_packages": [],
    "zip_exclude_packages": ["*"],
    "include_files": include_files,
    "excludes": ["tkinter", "test", "unittest"],
}

setup(
    name="nightcrate",
    version=package_version(),
    script_args=["build_exe"],
    options={"build_exe": build_options},
    executables=[
        Executable(
            str(ROOT / "packaging" / "backend_entry.py"),
            target_name="nightcrate-backend",
        )
    ],
)

(BUILD_DIR / "licences").mkdir(exist_ok=True)
(BUILD_DIR / ".gitkeep").touch()
