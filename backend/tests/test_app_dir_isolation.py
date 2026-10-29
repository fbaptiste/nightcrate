"""Guards against binding user app-data paths at module import time."""

from __future__ import annotations

import ast
from pathlib import Path

_APP_CONFIG_MODULE = "nightcrate.core.app_config"
_APP_DATA_NAMES = frozenset({"APP_DIR", "CONFIG_PATH"})


class _ImportTimeAliasVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.aliases: set[str] = set()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        pass

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        pass

    def visit_Lambda(self, node: ast.Lambda) -> None:
        pass

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name == _APP_CONFIG_MODULE and alias.asname is not None:
                self.aliases.add(alias.asname)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module == "nightcrate.core":
            for alias in node.names:
                if alias.name == "app_config":
                    self.aliases.add(alias.asname or alias.name)


class _ModuleScopeAppConfigVisitor(ast.NodeVisitor):
    def __init__(self, filename: str, aliases: set[str]) -> None:
        self.filename = filename
        self.aliases = aliases
        self.violations: list[str] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        for decorator in node.decorator_list:
            self.visit(decorator)
        self._visit_defaults(node.args)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        for decorator in node.decorator_list:
            self.visit(decorator)
        self._visit_defaults(node.args)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for base in node.bases:
            self.visit(base)
        for keyword in node.keywords:
            self.visit(keyword.value)
        for decorator in node.decorator_list:
            self.visit(decorator)
        for statement in node.body:
            self.visit(statement)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self._visit_defaults(node.args)

    def _visit_defaults(self, arguments: ast.arguments) -> None:
        for default in arguments.defaults:
            self.visit(default)
        for default in arguments.kw_defaults:
            if default is not None:
                self.visit(default)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr in _APP_DATA_NAMES and self._is_app_config_reference(node.value):
            self.violations.append(
                f"{self.filename}:{node.lineno}: references app_config.{node.attr} at import time"
            )
        self.generic_visit(node)

    def _is_app_config_reference(self, node: ast.expr) -> bool:
        if isinstance(node, ast.Name):
            return node.id in self.aliases
        return self._attribute_chain(node) == ("nightcrate", "core", "app_config")

    @staticmethod
    def _attribute_chain(node: ast.expr) -> tuple[str, ...] | None:
        parts: list[str] = []
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        if not isinstance(node, ast.Name):
            return None
        parts.append(node.id)
        return tuple(reversed(parts))


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

    alias_visitor = _ImportTimeAliasVisitor()
    for statement in tree.body:
        alias_visitor.visit(statement)

    visitor = _ModuleScopeAppConfigVisitor(filename, alias_visitor.aliases)
    for statement in tree.body:
        visitor.visit(statement)
    return [*violations, *visitor.violations]


def test_app_data_guard_detects_by_value_import():
    violations = _find_import_time_app_data_references(
        "from nightcrate.core.app_config import APP_DIR\n",
        "example.py",
    )
    assert violations == ["example.py:1: imports APP_DIR by value"]


def test_app_data_guard_detects_import_time_references():
    cases = [
        (
            "module_assignment.py",
            "from nightcrate.core import app_config\nCACHE = app_config.APP_DIR / 'cache'\n",
            ["module_assignment.py:2: references app_config.APP_DIR at import time"],
        ),
        (
            "class_body.py",
            "from nightcrate.core import app_config\n"
            "class Settings:\n"
            "    cache = app_config.APP_DIR / 'cache'\n",
            ["class_body.py:3: references app_config.APP_DIR at import time"],
        ),
        (
            "function_default.py",
            "from nightcrate.core import app_config\n"
            "def f(directory=app_config.APP_DIR / 'cache'):\n"
            "    pass\n",
            ["function_default.py:2: references app_config.APP_DIR at import time"],
        ),
        (
            "keyword_default.py",
            "from nightcrate.core import app_config\n"
            "def f(*, path=app_config.CONFIG_PATH):\n"
            "    pass\n",
            ["keyword_default.py:2: references app_config.CONFIG_PATH at import time"],
        ),
        (
            "lambda_default.py",
            "from nightcrate.core import app_config\n"
            "f = lambda directory=app_config.APP_DIR: directory\n",
            ["lambda_default.py:2: references app_config.APP_DIR at import time"],
        ),
        (
            "decorator.py",
            "from nightcrate.core import app_config\n"
            "@register(app_config.APP_DIR)\n"
            "def f():\n"
            "    pass\n",
            ["decorator.py:2: references app_config.APP_DIR at import time"],
        ),
        (
            "alias.py",
            "from nightcrate.core import app_config as ac\nCACHE = ac.APP_DIR\n",
            ["alias.py:2: references app_config.APP_DIR at import time"],
        ),
        (
            "dotted.py",
            "import nightcrate.core.app_config\nCACHE = nightcrate.core.app_config.CONFIG_PATH\n",
            ["dotted.py:2: references app_config.CONFIG_PATH at import time"],
        ),
        (
            "function_bodies.py",
            "from nightcrate.core import app_config\n"
            "def f():\n"
            "    return app_config.APP_DIR\n"
            "class Service:\n"
            "    def path(self):\n"
            "        return app_config.CONFIG_PATH\n",
            [],
        ),
    ]
    for filename, source, expected in cases:
        assert _find_import_time_app_data_references(source, filename) == expected


def test_app_data_paths_are_resolved_at_call_time():
    source_root = Path(__file__).resolve().parents[1] / "src" / "nightcrate"
    violations: list[str] = []
    scanned_paths: list[Path] = []
    for source_path in sorted(source_root.rglob("*.py")):
        relative = source_path.relative_to(source_root)
        if relative.parts[:2] == ("db", "migrations"):
            continue
        scanned_paths.append(relative)
        violations.extend(
            _find_import_time_app_data_references(
                source_path.read_text(encoding="utf-8"),
                str(relative),
                allow_by_value_imports=relative == Path("core/app_config.py"),
            )
        )
    assert Path("services/thumbnails.py") in scanned_paths
    assert len(scanned_paths) >= 100
    assert not violations, "App-data paths bound at import time:\n" + "\n".join(violations)


def test_cache_directories_follow_patched_app_dir(tmp_path: Path):
    from nightcrate.services import sky_tile_cache, thumbnails

    assert thumbnails.thumb_dir() == tmp_path / "thumbnails"
    assert sky_tile_cache.cell_dir() == tmp_path / "sky_tiles"


async def test_thumbnail_orphan_sweep_uses_redirected_app_dir(tmp_path: Path):
    from nightcrate.db.session import get_db
    from nightcrate.services import thumbnails

    thumbnail_dir = tmp_path / "thumbnails"
    assert thumbnails.thumb_dir(create=False) == thumbnail_dir
    thumbnail_dir.mkdir()
    orphan = thumbnail_dir / "ra50723_dec593038_list_180x180.jpg"
    orphan.write_bytes(b"\xff\xd8" + b"x" * 100 + b"\xff\xd9")

    async with get_db() as conn:
        removed = await thumbnails.sync_orphan_files(conn)

    assert removed == 1
    assert not orphan.exists()
