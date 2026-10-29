"""Guards against binding user app-data paths at module import time."""

from __future__ import annotations

import ast
from pathlib import Path

_APP_CONFIG_MODULE = "nightcrate.core.app_config"
_APP_DATA_NAMES = frozenset({"APP_DIR", "CONFIG_PATH"})


class _ModuleScopeAppConfigVisitor(ast.NodeVisitor):
    def __init__(self, filename: str) -> None:
        self.filename = filename
        self.violations: list[str] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        pass

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        pass

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        pass

    def visit_Lambda(self, node: ast.Lambda) -> None:
        pass

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if (
            isinstance(node.value, ast.Name)
            and node.value.id == "app_config"
            and node.attr in _APP_DATA_NAMES
        ):
            self.violations.append(
                f"{self.filename}:{node.lineno}: references app_config.{node.attr} at module scope"
            )
        self.generic_visit(node)


def _find_import_time_app_data_references(
    source: str,
    filename: str,
    *,
    allow_by_value_imports: bool = False,
) -> list[str]:
    tree = ast.parse(source, filename=filename)
    violations: list[str] = []
    if not allow_by_value_imports:
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == _APP_CONFIG_MODULE:
                for alias in node.names:
                    if alias.name in _APP_DATA_NAMES:
                        violations.append(
                            f"{filename}:{node.lineno}: imports {alias.name} by value"
                        )

    visitor = _ModuleScopeAppConfigVisitor(filename)
    for statement in tree.body:
        visitor.visit(statement)
    return [*violations, *visitor.violations]


def test_app_data_guard_detects_by_value_import():
    violations = _find_import_time_app_data_references(
        "from nightcrate.core.app_config import APP_DIR\n",
        "example.py",
    )
    assert violations == ["example.py:1: imports APP_DIR by value"]


def test_app_data_paths_are_resolved_at_call_time():
    source_root = Path(__file__).resolve().parents[1] / "src" / "nightcrate"
    violations: list[str] = []
    for source_path in sorted(source_root.rglob("*.py")):
        relative = source_path.relative_to(source_root)
        if relative.parts[:2] == ("db", "migrations"):
            continue
        violations.extend(
            _find_import_time_app_data_references(
                source_path.read_text(encoding="utf-8"),
                str(relative),
                allow_by_value_imports=relative == Path("core/app_config.py"),
            )
        )
    assert not violations, "App-data paths bound at import time:\n" + "\n".join(violations)


def test_cache_directories_follow_patched_app_dir(tmp_path: Path):
    from nightcrate.services import sky_tile_cache, thumbnails

    assert thumbnails.thumb_dir() == tmp_path / "thumbnails"
    assert sky_tile_cache.cell_dir() == tmp_path / "sky_tiles"


async def test_thumbnail_orphan_sweep_uses_redirected_app_dir(tmp_path: Path):
    from nightcrate.db.session import get_db
    from nightcrate.services.thumbnails import sync_orphan_files

    thumbnail_dir = tmp_path / "thumbnails"
    thumbnail_dir.mkdir()
    orphan = thumbnail_dir / "ra50723_dec593038_list_180x180.jpg"
    orphan.write_bytes(b"\xff\xd8" + b"x" * 100 + b"\xff\xd9")

    async with get_db() as conn:
        removed = await sync_orphan_files(conn)

    assert removed == 1
    assert not orphan.exists()
