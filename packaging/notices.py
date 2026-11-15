"""Inventory shipped code, enforce licence policy, and render release notices."""

from __future__ import annotations

import argparse
import email.message
import email.parser
import hashlib
import importlib
import json
import platform
import re
import shutil
import ssl
import subprocess
import sys
import sysconfig
import tarfile
import tempfile
import tomllib
import urllib.error
import urllib.request
from collections import defaultdict
from importlib import metadata
from pathlib import Path, PurePosixPath
from typing import Any

import certifi

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = Path(__file__).with_name("licence_policy.toml")
NATIVE_SUFFIXES = (".dylib", ".dll", ".pyd", ".so")
SOURCE_LICENCES = {"LGPL-2.1-or-later", "LGPL-3.0-or-later"}
GCC_RUNTIME_PREFIXES = ("libgcc_s", "libgfortran", "libquadmath")
HEADER_SUFFIXES = {
    ".c",
    ".cc",
    ".cpp",
    ".css",
    ".h",
    ".hpp",
    ".js",
    ".mjs",
    ".rs",
    ".ts",
    ".tsx",
}
MPL_INCOMPATIBLE = "Incompatible With Secondary Licenses"
SPDX_TOKEN = re.compile(
    r"\(|\)|\bAND\b|\bOR\b|\bWITH\b|[A-Za-z0-9][A-Za-z0-9.+-]*",
    re.IGNORECASE,
)


class NoticeError(RuntimeError):
    """A fail-closed inventory or rendering error."""


def _canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _normalise_expression(expression: str, policy: dict[str, Any]) -> str:
    expression = expression.strip()
    expression = policy.get("aliases", {}).get(expression, expression)
    # Cargo metadata still contains legacy slash-separated OR expressions.
    expression = re.sub(r"\s*/\s*", " OR ", expression)
    return expression


def _tokenise_expression(expression: str) -> list[str]:
    tokens = SPDX_TOKEN.findall(expression)
    compact_input = re.sub(r"\s+", "", expression)
    compact_tokens = "".join(tokens)
    if compact_input.lower() != compact_tokens.lower():
        raise NoticeError(f"cannot parse licence expression {expression!r}")
    return tokens


class _ExpressionParser:
    def __init__(self, tokens: list[str], accepted: set[str]):
        self.tokens = tokens
        self.accepted = accepted
        self.index = 0

    def parse(self) -> tuple[bool, str | None]:
        result = self._or_expression()
        if self.index != len(self.tokens):
            raise NoticeError(
                f"unexpected token {self.tokens[self.index]!r} in licence expression"
            )
        return result

    def _or_expression(self) -> tuple[bool, str | None]:
        alternatives = [self._and_expression()]
        while self._take("OR"):
            alternatives.append(self._and_expression())
        for allowed, choice in alternatives:
            if allowed:
                return True, choice
        return False, None

    def _and_expression(self) -> tuple[bool, str | None]:
        terms = [self._primary()]
        while self._take("AND"):
            terms.append(self._primary())
        allowed = all(term[0] for term in terms)
        choices = [term[1] for term in terms if term[1]]
        return allowed, " AND ".join(choices) if allowed else None

    def _primary(self) -> tuple[bool, str | None]:
        if self._take("("):
            result = self._or_expression()
            if not self._take(")"):
                raise NoticeError("unclosed parenthesis in licence expression")
            return result
        if self.index >= len(self.tokens):
            raise NoticeError("incomplete licence expression")
        licence = self.tokens[self.index]
        self.index += 1
        if self._take("WITH"):
            if self.index >= len(self.tokens):
                raise NoticeError("missing exception after WITH")
            licence += " WITH " + self.tokens[self.index]
            self.index += 1
        return licence in self.accepted, licence if licence in self.accepted else None

    def _take(self, value: str) -> bool:
        if self.index < len(self.tokens) and self.tokens[self.index].upper() == value:
            self.index += 1
            return True
        return False


def evaluate_licence(
    package: str,
    expression: str,
    policy: dict[str, Any] | None = None,
) -> str:
    """Return the accepted alternative or fail with the component name."""
    policy = policy or load_policy()
    expression = _normalise_expression(expression, policy)
    chosen = policy.get("choices", {}).get(_canonical(package))
    if chosen:
        expression = chosen
    accepted = set(policy.get("accepted", []))
    for licence, rule in policy.get("scoped", {}).items():
        if _canonical(package) in {_canonical(item) for item in rule["packages"]}:
            accepted.add(licence)
    allowed, selected = _ExpressionParser(
        _tokenise_expression(expression), accepted
    ).parse()
    if not allowed or not selected:
        raise NoticeError(
            f"{package}: licence expression {expression!r} is outside the policy"
        )
    return selected


def _is_standard_mpl_text(text: str) -> bool:
    lowered = text.lower()
    return (
        "mozilla public license version 2.0" in lowered
        and "exhibit a" in lowered
        and "exhibit b" in lowered
    )


def has_applied_mpl_incompatibility(text: str) -> bool:
    """Distinguish an applied MPL Exhibit B notice from the licence template."""
    return MPL_INCOMPATIBLE.lower() in text.lower() and not _is_standard_mpl_text(text)


def _check_mpl_tree(package: str, root: Path) -> None:
    if not root.is_dir():
        return
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        is_notice = path.name.upper().startswith(
            ("LICENSE", "LICENCE", "NOTICE", "COPYING")
        )
        if path.suffix.lower() not in HEADER_SUFFIXES and not is_notice:
            continue
        try:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                text = handle.read(
                    16_384 if path.suffix.lower() in HEADER_SUFFIXES else -1
                )
        except OSError as exc:
            raise NoticeError(
                f"{package}: cannot inspect MPL notice {path}: {exc}"
            ) from exc
        if has_applied_mpl_incompatibility(text):
            raise NoticeError(
                f"{package}: applied MPL 'Incompatible With Secondary Licenses' notice "
                f"in {path}"
            )


def _run(command: list[str], *, cwd: Path | None = None) -> str:
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise NoticeError(f"required tool is not installed: {command[0]}") from exc
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() or exc.stdout.strip() or f"exit {exc.returncode}"
        raise NoticeError(f"{' '.join(command)} failed: {detail}") from exc
    return result.stdout


def _licence_files(
    directory: Path, explicit: str | None = None
) -> list[dict[str, str]]:
    paths: list[Path] = []
    if explicit:
        candidate = directory / explicit
        if candidate.is_file():
            paths.append(candidate)
    for pattern in ("LICENSE*", "LICENCE*", "COPYING*", "NOTICE*"):
        paths.extend(path for path in directory.glob(pattern) if path.is_file())
    result: list[dict[str, str]] = []
    seen: set[Path] = set()
    for path in sorted(paths):
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        result.append(
            {
                "name": path.name,
                "text": path.read_text(encoding="utf-8", errors="replace"),
            }
        )
    return result


def _metadata_expression(message: email.message.Message) -> str:
    expression = message.get("License-Expression")
    if expression:
        return expression.strip()
    licence = (message.get("License") or "").strip()
    if licence and "\n" not in licence and len(licence) < 100:
        return licence
    if "Permission is hereby granted, free of charge" in licence:
        return "MIT"
    if "Apache License" in licence and "Version 2.0" in licence:
        return "Apache-2.0"
    classifiers = message.get_all("Classifier", [])
    classifier_map = {
        "Apache Software License": "Apache-2.0",
        "BSD License": "BSD-3-Clause",
        "GNU Lesser General Public License v2 or later (LGPLv2+)": "LGPL-2.1-or-later",
        "GNU Lesser General Public License v3 or later (LGPLv3+)": "LGPL-3.0-or-later",
        "MIT License": "MIT",
        "Mozilla Public License 2.0 (MPL 2.0)": "MPL-2.0",
        "Python Software Foundation License": "PSF-2.0",
    }
    found = [
        value
        for classifier in classifiers
        for suffix, value in classifier_map.items()
        if classifier.endswith(suffix)
    ]
    if found:
        return " OR ".join(dict.fromkeys(found))
    raise NoticeError(f"{message.get('Name', '<unknown>')}: no usable licence metadata")


def _distribution_licences(dist: metadata.Distribution) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for item in dist.files or []:
        lower = str(item).lower()
        if ".dist-info/" not in lower or not any(
            marker in PurePosixPath(lower).name
            for marker in ("license", "licence", "copying", "notice")
        ):
            continue
        path = Path(dist.locate_file(item))
        if path.is_file():
            result.append(
                {
                    "name": PurePosixPath(str(item)).name,
                    "text": path.read_text(encoding="utf-8", errors="replace"),
                }
            )
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _is_native(path: Path) -> bool:
    lower = path.name.lower()
    return lower.endswith(NATIVE_SUFFIXES) or ".so." in lower


def _installed_distributions() -> dict[str, metadata.Distribution]:
    return {
        _canonical(dist.metadata["Name"]): dist
        for dist in metadata.distributions()
        if dist.metadata.get("Name")
    }


def _native_distribution_indices(
    distributions: dict[str, metadata.Distribution],
) -> tuple[dict[str, list[tuple[metadata.Distribution, str, Path]]], dict[str, str]]:
    by_basename: dict[str, list[tuple[metadata.Distribution, str, Path]]] = defaultdict(
        list
    )
    hashes: dict[str, str] = {}
    for dist in distributions.values():
        for item in dist.files or []:
            item_text = str(item).replace("\\", "/")
            if not _is_native(Path(item_text)):
                continue
            source = Path(dist.locate_file(item))
            if not source.is_file():
                continue
            by_basename[source.name].append((dist, item_text, source))
            try:
                hashes[str(source)] = _sha256(source)
            except OSError as exc:
                raise NoticeError(
                    f"cannot hash installed native library {source}: {exc}"
                ) from exc
    return by_basename, hashes


def _is_gcc_runtime(path: Path) -> bool:
    return path.name.lower().startswith(GCC_RUNTIME_PREFIXES)


def _frozen_distribution_versions(backend_dir: Path) -> dict[str, str]:
    versions: dict[str, str] = {}
    for metadata_path in backend_dir.rglob("*.dist-info/METADATA"):
        with metadata_path.open("r", encoding="utf-8", errors="replace") as handle:
            message = email.parser.Parser().parse(handle)
        name = message.get("Name")
        version = message.get("Version")
        if not name or not version:
            raise NoticeError(
                f"{metadata_path}: frozen distribution metadata is incomplete"
            )
        canonical = _canonical(name)
        if canonical in versions and versions[canonical] != version:
            raise NoticeError(f"{name}: frozen build contains conflicting versions")
        versions[canonical] = version
    return versions


def _compiler_record(dist: metadata.Distribution) -> dict[str, Any] | None:
    package_map = metadata.packages_distributions()
    candidates = [
        package
        for package, names in package_map.items()
        if any(_canonical(name) == _canonical(dist.metadata["Name"]) for name in names)
    ]
    for package in candidates:
        try:
            config_module = importlib.import_module(f"{package}.__config__")
        except ImportError:
            continue
        config = getattr(config_module, "CONFIG", None)
        if not isinstance(config, dict):
            continue
        compilers = config.get("Compilers")
        if isinstance(compilers, dict):
            record = compilers.get("fortran")
            if isinstance(record, dict):
                return record
    return None


def _gcc_runtime_version(
    package: str,
    environment_version: str,
    frozen_version: str | None,
    compiler_record: dict[str, Any] | None,
    library: Path,
) -> str:
    if frozen_version is None:
        raise NoticeError(f"{library}: frozen {package} dist-info version is missing")
    if environment_version != frozen_version:
        raise NoticeError(
            f"{library}: build-environment {package} version {environment_version} "
            f"does not match frozen version {frozen_version}"
        )
    if not compiler_record or str(compiler_record.get("name", "")).lower() != "gcc":
        raise NoticeError(f"{library}: {package} compiler record does not name gcc")
    version = str(compiler_record.get("version", "")).strip()
    if not version:
        raise NoticeError(f"{library}: {package} gcc compiler record has no version")
    return version


def _owner_for_python_native(
    path: Path,
    backend_dir: Path,
    by_basename: dict[str, list[tuple[metadata.Distribution, str, Path]]],
    source_hashes: dict[str, str],
    frozen_versions: dict[str, str],
) -> dict[str, str]:
    candidates = by_basename.get(path.name, [])
    relative = path.relative_to(backend_dir).as_posix()
    if relative.startswith("lib/"):
        relative = relative[4:]
    exact = [candidate for candidate in candidates if candidate[1] == relative]
    if len(exact) == 1:
        candidates = exact
    else:
        target_hash = _sha256(path)
        matching = [
            candidate
            for candidate in candidates
            if source_hashes[str(candidate[2])] == target_hash
        ]
        if matching:
            candidates = matching
        elif len(candidates) > 1:
            # cx_Freeze rewrites load paths, so copied wheel libraries no longer
            # hash to their RECORD source. The rewritten install name retains the
            # owning top-level package (for example, /DLC/PIL/.dylibs/...).
            binary = path.read_bytes()
            embedded_owner = [
                candidate
                for candidate in candidates
                if f"/{candidate[1].split('/', 1)[0]}/".encode() in binary
            ]
            if embedded_owner:
                candidates = embedded_owner
    owners = {
        (_canonical(candidate[0].metadata["Name"]), candidate[0].version)
        for candidate in candidates
    }
    if len(owners) != 1:
        detail = ", ".join(f"{name}=={version}" for name, version in sorted(owners))
        if not detail:
            detail = "no installed distribution matches"
        raise NoticeError(f"{path}: native library has no unique owner ({detail})")
    name, version = owners.pop()
    dist = next(
        candidate[0]
        for candidate in candidates
        if _canonical(candidate[0].metadata["Name"]) == name
    )
    if _is_gcc_runtime(path):
        display_name = dist.metadata["Name"]
        gcc_version = _gcc_runtime_version(
            display_name,
            dist.version,
            frozen_versions.get(_canonical(display_name)),
            _compiler_record(dist),
            path,
        )
        return {
            "kind": "gcc",
            "name": "GCC runtime",
            "version": gcc_version,
            "provider": display_name,
            "provider_version": dist.version,
        }
    return {
        "kind": "python",
        "name": dist.metadata["Name"],
        "version": version,
    }


def _python_components(
    backend_dir: Path,
    native_owners: list[dict[str, str]],
    distributions: dict[str, metadata.Distribution],
    policy: dict[str, Any],
) -> list[dict[str, Any]]:
    names = {
        _canonical(owner["name"])
        for owner in native_owners
        if owner["kind"] == "python"
    }
    package_map = metadata.packages_distributions()
    library = backend_dir / "lib"
    if library.is_dir():
        for child in library.iterdir():
            top_level = child.name
            if child.is_file():
                top_level = re.split(r"\.(?:cpython-|abi3|pyc$)", top_level)[0]
            for dist_name in package_map.get(top_level, []):
                names.add(_canonical(dist_name))
    names.update({_canonical("cx-Freeze"), _canonical("freeze-core")})
    names.discard("nightcrate")
    result: list[dict[str, Any]] = []
    for name in sorted(names):
        dist = distributions.get(name)
        if dist is None:
            raise NoticeError(
                f"{name}: shipped Python distribution metadata is missing"
            )
        display_name = dist.metadata["Name"]
        expression = _metadata_expression(dist.metadata)
        selected = evaluate_licence(display_name, expression, policy)
        licences = _distribution_licences(dist)
        if "MPL-2.0" in selected:
            root = Path(dist.locate_file(""))
            top_levels = [
                line.strip()
                for line in (dist.read_text("top_level.txt") or "").splitlines()
                if line.strip()
            ]
            for top_level in top_levels:
                _check_mpl_tree(display_name, root / top_level)
        result.append(
            {
                "kind": "python",
                "name": display_name,
                "version": dist.version,
                "licence": expression,
                "selected_licence": selected,
                "source_url": f"https://pypi.org/project/{display_name}/{dist.version}/",
                "licence_files": licences,
            }
        )
    return result


def _frontend_package_name(lock_path: str, item: dict[str, Any]) -> str:
    if item.get("name"):
        return item["name"]
    marker = "node_modules/"
    if marker not in lock_path:
        raise NoticeError(f"cannot determine npm package name from {lock_path}")
    return lock_path.rsplit(marker, 1)[1]


def _frontend_components(policy: dict[str, Any]) -> list[dict[str, Any]]:
    frontend = ROOT / "frontend"
    if not (frontend / "node_modules").is_dir():
        raise NoticeError(
            "frontend/node_modules is missing; run npm ci before inventory"
        )
    lock_path = frontend / "package-lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    result: list[dict[str, Any]] = []
    for package_path, item in sorted(lock["packages"].items()):
        install_dir = frontend / package_path
        if not package_path or item.get("dev") is True or not install_dir.is_dir():
            continue
        name = _frontend_package_name(package_path, item)
        version = item.get("version")
        expression = item.get("license")
        if not version or not expression:
            raise NoticeError(
                f"{name}: production npm package lacks version or licence"
            )
        selected = evaluate_licence(name, expression, policy)
        if "MPL-2.0" in selected:
            _check_mpl_tree(name, install_dir)
        result.append(
            {
                "kind": "frontend",
                "name": name,
                "version": version,
                "licence": expression,
                "selected_licence": selected,
                "source_url": f"https://www.npmjs.com/package/{name}/v/{version}",
                "licence_files": _licence_files(install_dir),
            }
        )
    if not result:
        raise NoticeError("no installed production frontend packages were inventoried")
    return result


def _rust_components(shell_dir: Path, policy: dict[str, Any]) -> list[dict[str, Any]]:
    if shell_dir.is_dir() and (shell_dir / "src-tauri" / "Cargo.toml").is_file():
        manifest = shell_dir / "src-tauri" / "Cargo.toml"
    else:
        manifest = shell_dir / "Cargo.toml" if shell_dir.is_dir() else shell_dir
    if not manifest.is_file():
        raise NoticeError(f"Rust manifest is missing: {manifest}")
    output = _run(
        [
            "cargo",
            "metadata",
            "--format-version",
            "1",
            "--locked",
            "--manifest-path",
            str(manifest),
        ]
    )
    cargo = json.loads(output)
    result: list[dict[str, Any]] = []
    for item in sorted(
        cargo["packages"], key=lambda value: (value["name"], value["version"])
    ):
        if item["name"] == "nightcrate-shell" and item.get("source") is None:
            continue
        expression = item.get("license")
        if not expression:
            raise NoticeError(f"{item['name']}: Rust crate has no licence expression")
        selected = evaluate_licence(item["name"], expression, policy)
        crate_root = Path(item["manifest_path"]).parent
        licence_files = _licence_files(crate_root, item.get("license_file"))
        if "MPL-2.0" in selected:
            _check_mpl_tree(item["name"], crate_root)
        result.append(
            {
                "kind": "rust",
                "name": item["name"],
                "version": item["version"],
                "licence": expression,
                "selected_licence": selected,
                "source_url": item.get("repository")
                or f"https://crates.io/crates/{item['name']}/{item['version']}",
                "licence_files": licence_files,
            }
        )
    if not result:
        raise NoticeError("cargo metadata returned no third-party Rust crates")
    return result


def _dpkg_owner(path: Path) -> tuple[dict[str, str], str]:
    output = _run(["dpkg-query", "-S", f"*/{path.name}"])
    candidates: list[tuple[str, Path]] = []
    for line in output.splitlines():
        package, separator, installed_path = line.partition(": ")
        if separator and Path(installed_path).is_file():
            candidates.append((package, Path(installed_path)))
    target_hash = _sha256(path)
    matches = [
        (package, item) for package, item in candidates if _sha256(item) == target_hash
    ]
    if matches:
        candidates = matches
    packages = {package for package, _ in candidates}
    if len(packages) != 1:
        detail = ", ".join(sorted(packages)) or "no dpkg match"
        raise NoticeError(
            f"{path}: native library has no unique system owner ({detail})"
        )
    package = packages.pop()
    query = _run(
        [
            "dpkg-query",
            "-W",
            "-f=${binary:Package}\t${Version}\t${source:Package}\t${source:Version}",
            package,
        ]
    ).strip()
    binary, version, source, source_version = query.split("\t")
    source = source or binary.split(":", 1)[0]
    source_version = source_version or version
    copyright_path = Path("/usr/share/doc") / binary.split(":", 1)[0] / "copyright"
    copyright_text = (
        copyright_path.read_text(encoding="utf-8", errors="replace")
        if copyright_path.is_file()
        else ""
    )
    owner = {
        "kind": "system",
        "name": binary,
        "version": version,
        "source_package": source,
        "source_version": source_version,
    }
    return owner, copyright_text


def _system_natives(
    appimage: Path, backend_dir: Path
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    backend_hashes = {
        _sha256(path)
        for path in backend_dir.rglob("*")
        if path.is_file() and _is_native(path)
    }
    natives: list[dict[str, Any]] = []
    packages: dict[tuple[str, str], dict[str, Any]] = {}
    for path in sorted(appimage.rglob("*")):
        if not path.is_file() or not _is_native(path):
            continue
        digest = _sha256(path)
        if digest in backend_hashes:
            continue
        owner, copyright_text = _dpkg_owner(path)
        natives.append(
            {
                "path": path.relative_to(appimage).as_posix(),
                "sha256": digest,
                "owner": owner,
            }
        )
        key = (owner["name"], owner["version"])
        if key not in packages:
            source_required = bool(
                re.search(
                    r"GNU (?:Library|Lesser) General Public License|\bLGPL\b",
                    copyright_text,
                    re.IGNORECASE,
                )
            )
            packages[key] = {
                "kind": "system",
                **owner,
                "licence": "System package copyright file",
                "selected_licence": "system",
                "source_required": source_required,
                "source_url": f"https://packages.ubuntu.com/{owner['name'].split(':', 1)[0]}",
                "licence_files": (
                    [{"name": "copyright", "text": copyright_text}]
                    if copyright_text
                    else []
                ),
            }
    return natives, sorted(
        packages.values(), key=lambda item: (item["name"], item["version"])
    )


def _platform_name() -> str:
    if sys.platform == "darwin":
        return "macos"
    if sys.platform == "win32":
        return "windows"
    if sys.platform.startswith("linux"):
        return "linux"
    raise NoticeError(f"unsupported release platform: {sys.platform}")


def inventory(
    backend_dir: Path, shell_dir: Path, appimage: Path | None
) -> dict[str, Any]:
    backend_dir = backend_dir.resolve()
    if (
        not (backend_dir / "nightcrate-backend").is_file()
        and not (backend_dir / "nightcrate-backend.exe").is_file()
    ):
        raise NoticeError(f"frozen backend executable is missing from {backend_dir}")
    policy = load_policy()
    distributions = _installed_distributions()
    by_basename, source_hashes = _native_distribution_indices(distributions)
    frozen_versions = _frozen_distribution_versions(backend_dir)
    natives: list[dict[str, Any]] = []
    owners: list[dict[str, str]] = []
    for path in sorted(backend_dir.rglob("*")):
        if not path.is_file() or not _is_native(path):
            continue
        owner = _owner_for_python_native(
            path,
            backend_dir,
            by_basename,
            source_hashes,
            frozen_versions,
        )
        owners.append(owner)
        natives.append(
            {
                "path": path.relative_to(backend_dir).as_posix(),
                "sha256": _sha256(path),
                "owner": owner,
            }
        )
    python_components = _python_components(backend_dir, owners, distributions, policy)
    frontend_components = _frontend_components(policy)
    rust_components = _rust_components(shell_dir.resolve(), policy)
    system_components: list[dict[str, Any]] = []
    if appimage is not None:
        if not appimage.is_dir():
            raise NoticeError(f"extracted AppImage directory is missing: {appimage}")
        appimage_natives, system_components = _system_natives(
            appimage.resolve(), backend_dir
        )
        natives.extend(appimage_natives)
    project = tomllib.loads(
        (ROOT / "backend" / "pyproject.toml").read_text(encoding="utf-8")
    )
    cpython_candidates = (
        Path(sysconfig.get_path("stdlib")) / "LICENSE.txt",
        Path(sys.base_prefix) / "LICENSE.txt",
        Path(sys.base_prefix) / "Lib" / "LICENSE.txt",
    )
    cpython_licence = next(
        (path for path in cpython_candidates if path.is_file()), None
    )
    if cpython_licence is None:
        checked = ", ".join(str(path) for path in cpython_candidates)
        raise NoticeError(f"CPython licence file is missing (checked {checked})")
    frozen_licence = backend_dir / "frozen_application_license.txt"
    if not frozen_licence.is_file():
        raise NoticeError(f"cx_Freeze runtime licence is missing: {frozen_licence}")
    cx_freeze = distributions.get(_canonical("cx-Freeze"))
    if cx_freeze is None:
        raise NoticeError("cx_Freeze distribution metadata is missing")
    cx_freeze_licences = _distribution_licences(cx_freeze)
    if not cx_freeze_licences:
        raise NoticeError("cx_Freeze packaged licence file is missing")
    return {
        "schema": 1,
        "project": {"name": "nightcrate", "version": project["project"]["version"]},
        "platform": _platform_name(),
        "architecture": platform.machine(),
        "python_version": platform.python_version(),
        "cpython_licence": cpython_licence.read_text(encoding="utf-8"),
        "cx_freeze_licence": cx_freeze_licences[0]["text"],
        "native_libraries": sorted(natives, key=lambda item: item["path"]),
        "components": sorted(
            python_components
            + frontend_components
            + rust_components
            + system_components,
            key=lambda item: (item["kind"], item["name"].lower(), item["version"]),
        ),
    }


# Verify against certifi's bundle: python.org's macOS builds ship no system
# certificate store, so the default context fails there.
_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
_USER_AGENT = {"User-Agent": "NightCrate-release-builder"}


def _urlopen(url: str, timeout: int):
    request = urllib.request.Request(url, headers=_USER_AGENT)
    return urllib.request.urlopen(request, timeout=timeout, context=_SSL_CONTEXT)  # noqa: S310


def _download(url: str, destination: Path, expected_sha256: str | None = None) -> None:
    try:
        with _urlopen(url, timeout=60) as response:
            with destination.open("wb") as handle:
                shutil.copyfileobj(response, handle)
    except (OSError, urllib.error.URLError) as exc:
        raise NoticeError(f"missing source download {url}: {exc}") from exc
    if expected_sha256 and _sha256(destination) != expected_sha256:
        destination.unlink(missing_ok=True)
        raise NoticeError(f"source download checksum mismatch: {url}")


def _download_python_sdist(component: dict[str, Any], directory: Path) -> Path:
    name = component["name"]
    version = component["version"]
    url = f"https://pypi.org/pypi/{name}/{version}/json"
    try:
        with _urlopen(url, timeout=30) as response:
            payload = json.load(response)
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise NoticeError(f"missing source for {name}=={version}: {exc}") from exc
    sdists = [
        item for item in payload.get("urls", []) if item.get("packagetype") == "sdist"
    ]
    if len(sdists) != 1:
        raise NoticeError(f"missing unique source distribution for {name}=={version}")
    item = sdists[0]
    filename = item["filename"]
    if Path(filename).name != filename or "\\" in filename:
        raise NoticeError(f"unsafe source filename for {name}=={version}: {filename!r}")
    destination = directory / filename
    _download(item["url"], destination, item.get("digests", {}).get("sha256"))
    return destination


def _download_apt_source(component: dict[str, Any], directory: Path) -> list[Path]:
    before = {path.name for path in directory.iterdir()}
    source = component["source_package"]
    version = component["source_version"]
    _run(["apt-get", "source", "--download-only", f"{source}={version}"], cwd=directory)
    paths = sorted(path for path in directory.iterdir() if path.name not in before)
    if not paths:
        raise NoticeError(f"missing Ubuntu source for {source}={version}")
    return paths


def _source_archive(inventory_data: dict[str, Any], out: Path) -> Path:
    version = inventory_data["project"]["version"]
    platform_name = inventory_data["platform"]
    destination = out / f"nightcrate-{version}-lgpl-sources-{platform_name}.tar.gz"
    destination.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory(prefix="nightcrate-sources-") as temp_name:
        temp = Path(temp_name)
        members: list[tuple[Path, str]] = []
        for component in inventory_data["components"]:
            selected = component.get("selected_licence", "")
            if component["kind"] == "python" and any(
                licence in selected for licence in SOURCE_LICENCES
            ):
                directory = (
                    temp / "python" / f"{component['name']}-{component['version']}"
                )
                directory.mkdir(parents=True)
                path = _download_python_sdist(component, directory)
                members.append((path, f"python/{directory.name}/{path.name}"))
            elif component["kind"] == "system" and component.get("source_required"):
                directory = (
                    temp
                    / "ubuntu"
                    / (f"{component['source_package']}-{component['source_version']}")
                )
                directory.mkdir(parents=True)
                for path in _download_apt_source(component, directory):
                    members.append((path, f"ubuntu/{directory.name}/{path.name}"))
        gcc_versions = {
            item["owner"]["version"]
            for item in inventory_data["native_libraries"]
            if item["owner"]["kind"] == "gcc"
        }
        for gcc_version in sorted(gcc_versions):
            filename = f"gcc-{gcc_version}.tar.xz"
            path = temp / "gcc" / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            _download(f"https://ftp.gnu.org/gnu/gcc/gcc-{gcc_version}/{filename}", path)
            members.append((path, f"gcc/{filename}"))
        if not members:
            raise NoticeError("no LGPL source components were found in the inventory")
        temporary_archive = destination.with_suffix(destination.suffix + ".tmp")
        with tarfile.open(temporary_archive, "w:gz") as archive:
            for path, arcname in sorted(members, key=lambda item: item[1]):
                archive.add(path, arcname=arcname, recursive=False)
        temporary_archive.replace(destination)
    return destination


def _notices_text(inventory_data: dict[str, Any], archive_name: str) -> str:
    lines = [
        "NightCrate third-party notices",
        "==============================",
        "",
        f"Build: NightCrate {inventory_data['project']['version']} "
        f"({inventory_data['platform']}/{inventory_data['architecture']})",
        "",
        "The exact sources for bundled LGPL components are in:",
        f"  {archive_name}",
        "",
        "Components",
        "----------",
    ]
    text_groups: dict[str, dict[str, Any]] = {}
    for component in inventory_data["components"]:
        lines.append(
            f"- [{component['kind']}] {component['name']} {component['version']}: "
            f"{component['licence']} (accepted as {component['selected_licence']})"
        )
        lines.append(f"  Source: {component['source_url']}")
        for licence_file in component.get("licence_files", []):
            text = licence_file["text"].rstrip() + "\n"
            digest = hashlib.sha256(text.encode()).hexdigest()
            group = text_groups.setdefault(
                digest,
                {"text": text, "users": []},
            )
            group["users"].append(
                f"{component['name']} {component['version']} ({licence_file['name']})"
            )
    lines.extend(["", "Native libraries", "----------------"])
    for item in inventory_data["native_libraries"]:
        owner = item["owner"]
        provider = ""
        if owner.get("provider"):
            provider = f", provided by {owner['provider']} {owner['provider_version']}"
        lines.append(
            f"- {item['path']}: {owner['kind']} {owner['name']} {owner['version']} "
            f"(sha256 {item['sha256']}{provider})"
        )
    lines.extend(["", "Licence texts", "-------------"])
    for number, group in enumerate(text_groups.values(), start=1):
        lines.extend(
            [
                "",
                f"Licence text {number}",
                "Used by: " + "; ".join(group["users"]),
                "",
                group["text"].rstrip(),
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def render(inventory_path: Path, out: Path) -> Path:
    inventory_data = json.loads(inventory_path.read_text(encoding="utf-8"))
    if inventory_data.get("schema") != 1:
        raise NoticeError(f"unsupported inventory schema in {inventory_path}")
    out.mkdir(parents=True, exist_ok=True)
    archive = _source_archive(inventory_data, out)
    licences = out / "licences"
    if licences.exists():
        shutil.rmtree(licences)
    (licences / "sky").mkdir(parents=True)
    shutil.copyfile(ROOT / "LICENSE", licences / "LICENSE")
    (licences / "CPython-LICENSE.txt").write_text(
        inventory_data["cpython_licence"], encoding="utf-8"
    )
    (licences / "cx_Freeze-LICENSE.md").write_text(
        inventory_data["cx_freeze_licence"], encoding="utf-8"
    )
    (licences / "THIRD_PARTY_NOTICES.txt").write_text(
        _notices_text(inventory_data, archive.name), encoding="utf-8"
    )
    sky = ROOT / "frontend" / "src" / "data" / "sky"
    shutil.copyfile(
        sky / "LICENSE-d3-celestial.txt", licences / "sky" / "LICENSE-d3-celestial.txt"
    )
    shutil.copyfile(sky / "SOURCES.md", licences / "sky" / "SOURCES.md")
    return archive


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    inventory_parser = commands.add_parser("inventory", help="inventory a frozen build")
    inventory_parser.add_argument("--backend-dir", type=Path, required=True)
    inventory_parser.add_argument("--shell-dir", type=Path, required=True)
    inventory_parser.add_argument("--appimage", type=Path)
    inventory_parser.add_argument("--out", type=Path, required=True)
    render_parser = commands.add_parser(
        "render", help="render notices and LGPL sources"
    )
    render_parser.add_argument("--inventory", type=Path, required=True)
    render_parser.add_argument("--out", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        if args.command == "inventory":
            result = inventory(args.backend_dir, args.shell_dir, args.appimage)
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(
                json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            print(f"wrote {args.out}")
        else:
            archive = render(args.inventory, args.out)
            print(f"wrote {args.out / 'licences'} and {archive}")
    except NoticeError as exc:
        print(f"licence notices failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
