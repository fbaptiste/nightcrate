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
import zipfile
from collections import defaultdict
from importlib import metadata
from pathlib import Path, PurePosixPath
from typing import Any

import certifi

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = Path(__file__).with_name("licence_policy.toml")
LICENCE_TEXT_DIR = Path(__file__).with_name("licence-texts")
NATIVE_SUFFIXES = (".dylib", ".dll", ".pyd", ".so")
SOURCE_LICENCES = {"LGPL-2.1-or-later", "LGPL-3.0-or-later"}
GCC_RUNTIME_PREFIXES = ("libgcc_s", "libgfortran", "libquadmath")
MSVC_RUNTIME_PREFIXES = ("vcruntime140", "msvcp140")
MSVC_SYSTEM_LIBRARY_NOTICE = (
    "GPLv3 §1 System Library; no Corresponding Source archive is required."
)
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


def _licence_identifiers(expression: str) -> list[str]:
    """Return each SPDX licence or exception identifier in a chosen expression."""
    return list(
        dict.fromkeys(
            token
            for token in _tokenise_expression(expression)
            if token.upper() not in {"AND", "OR", "WITH"} and token not in {"(", ")"}
        )
    )


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
            encoding="utf-8",
            errors="strict",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise NoticeError(f"required tool is not installed: {command[0]}") from exc
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() or exc.stdout.strip() or f"exit {exc.returncode}"
        raise NoticeError(f"{' '.join(command)} failed: {detail}") from exc
    except UnicodeError as exc:
        raise NoticeError(
            f"{' '.join(command)} produced output that is not valid UTF-8: {exc}"
        ) from exc
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


def _declared_authors(value: Any) -> list[str]:
    """Normalise Python, npm, and Cargo author metadata for notice rendering."""
    if isinstance(value, str):
        value = " ".join(value.split())
        return [value] if value else []
    if isinstance(value, dict):
        return _declared_authors(value.get("name"))
    if isinstance(value, list):
        return list(
            dict.fromkeys(
                author for item in value for author in _declared_authors(item)
            )
        )
    return []


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
    distributions = {
        _canonical(dist.metadata["Name"]): dist
        for dist in metadata.distributions()
        if dist.metadata.get("Name")
    }
    roots = {Path(dist.locate_file("")) for dist in distributions.values()}
    for root in sorted(roots):
        for metadata_path in sorted(root.rglob("*.dist-info/METADATA")):
            dist = metadata.Distribution.at(metadata_path.parent)
            name = dist.metadata.get("Name")
            if name:
                distributions.setdefault(_canonical(name), dist)
    return distributions


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


def _interpreter_native_candidates(
    interpreter_root: Path | None = None,
    platstdlib: Path | None = None,
    python_version: str | None = None,
) -> dict[str, list[tuple[Path, dict[str, Any]]]]:
    """Index CPython and MSVC natives from the build interpreter."""
    interpreter_root = interpreter_root or Path(sys.base_prefix)
    if platstdlib is None:
        platstdlib_paths = {
            Path(sysconfig.get_path("platstdlib")),
            Path(
                sysconfig.get_path(
                    "platstdlib",
                    vars={"base": sys.base_prefix, "platbase": sys.base_prefix},
                )
            ),
        }
    else:
        platstdlib_paths = {platstdlib}
    python_version = python_version or platform.python_version()
    result: dict[str, list[tuple[Path, dict[str, Any]]]] = defaultdict(list)

    def add(path: Path, owner: dict[str, Any]) -> None:
        if path.is_file():
            result[path.name.lower()].append((path, owner))

    cpython_owner: dict[str, Any] = {
        "kind": "cpython",
        "name": "CPython",
        "version": python_version,
    }
    msvc_owner: dict[str, Any] = {
        "kind": "system",
        "name": "Microsoft Visual C++ runtime",
        "system_library": True,
        "notice": MSVC_SYSTEM_LIBRARY_NOTICE,
    }

    def interpreter_owner(path: Path) -> dict[str, Any]:
        if path.name.lower().startswith(MSVC_RUNTIME_PREFIXES):
            return msvc_owner
        return cpython_owner

    dlls = interpreter_root / "DLLs"
    if dlls.is_dir():
        for path in dlls.iterdir():
            add(path, interpreter_owner(path))
    if interpreter_root.is_dir():
        for path in interpreter_root.iterdir():
            add(path, interpreter_owner(path))
    for path_root in platstdlib_paths:
        lib_dynload = path_root / "lib-dynload"
        if lib_dynload.is_dir():
            for path in lib_dynload.iterdir():
                if path.is_file() and _is_native(path):
                    add(path, cpython_owner)
    return result


def _interpreter_native_owner(
    path: Path,
    candidates: dict[str, list[tuple[Path, dict[str, Any]]]],
) -> dict[str, Any] | None:
    target_hash = _sha256(path)
    matches = [
        owner
        for source, owner in candidates.get(path.name.lower(), [])
        if _sha256(source) == target_hash
    ]
    distinct = {json.dumps(owner, sort_keys=True) for owner in matches}
    if len(distinct) == 1:
        return matches[0]
    if matches:
        raise NoticeError(f"{path}: interpreter native file has ambiguous ownership")
    return None


def _frozen_distribution_versions(backend_dir: Path) -> dict[str, str]:
    versions: dict[str, str] = {}

    def add(message: email.message.Message, source: str) -> None:
        name = message.get("Name")
        version = message.get("Version")
        if not name or not version:
            raise NoticeError(f"{source}: frozen distribution metadata is incomplete")
        canonical = _canonical(name)
        if canonical in versions and versions[canonical] != version:
            raise NoticeError(f"{name}: frozen build contains conflicting versions")
        versions[canonical] = version

    for metadata_path in backend_dir.rglob("*.dist-info/METADATA"):
        with metadata_path.open("r", encoding="utf-8", errors="replace") as handle:
            message = email.parser.Parser().parse(handle)
        add(message, str(metadata_path))
    archive = backend_dir / "lib" / "library.zip"
    if archive.is_file():
        try:
            with zipfile.ZipFile(archive) as frozen_zip:
                for entry in frozen_zip.namelist():
                    if not entry.endswith(".dist-info/METADATA"):
                        continue
                    text = frozen_zip.read(entry).decode("utf-8", errors="replace")
                    add(email.parser.Parser().parsestr(text), f"{archive}!{entry}")
        except (OSError, zipfile.BadZipFile) as exc:
            raise NoticeError(
                f"cannot inspect frozen Python archive {archive}: {exc}"
            ) from exc
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
) -> str | None:
    if frozen_version is None:
        raise NoticeError(f"{library}: frozen {package} dist-info version is missing")
    if environment_version != frozen_version:
        raise NoticeError(
            f"{library}: build-environment {package} version {environment_version} "
            f"does not match frozen version {frozen_version}"
        )
    if compiler_record and str(compiler_record.get("name", "")).lower() == "gcc":
        version = str(compiler_record.get("version", "")).strip()
        if version:
            return version
    if sys.platform.startswith("linux"):
        return _elf_gcc_version(library)
    return None


def _elf_gcc_version(library: Path) -> str | None:
    """Read the compiler release from an ELF .comment section when available."""
    output = _run(["readelf", "--string-dump=.comment", str(library)])
    match = re.search(r"GCC: \(GNU\)\s+([^\s]+)", output)
    return match.group(1) if match else None


def _native_binary_kind(path: Path) -> str | None:
    try:
        with path.open("rb") as handle:
            magic = handle.read(4)
    except OSError:
        return None
    if magic == b"\x7fELF":
        return "elf"
    if magic in {
        b"\xfe\xed\xfa\xce",
        b"\xce\xfa\xed\xfe",
        b"\xfe\xed\xfa\xcf",
        b"\xcf\xfa\xed\xfe",
        b"\xca\xfe\xba\xbe",
        b"\xbe\xba\xfe\xca",
    }:
        return "macho"
    return None


def _candidate_owners(
    candidates: list[tuple[metadata.Distribution, str, Path]],
) -> set[tuple[str, str]]:
    return {
        (_canonical(candidate[0].metadata["Name"]), candidate[0].version)
        for candidate in candidates
    }


def _disambiguate_distribution_candidates(
    candidates: list[tuple[metadata.Distribution, str, Path]],
    record_relative: str,
    binary_path: Path,
) -> list[tuple[metadata.Distribution, str, Path]]:
    """Narrow identical or relocated binaries using their frozen path."""
    if len(_candidate_owners(candidates)) <= 1:
        return candidates

    exact = [candidate for candidate in candidates if candidate[1] == record_relative]
    if exact:
        candidates = exact
        if len(_candidate_owners(candidates)) <= 1:
            return candidates

    suffix = [
        candidate
        for candidate in candidates
        if candidate[1].endswith(f"/{record_relative}")
    ]
    if suffix:
        candidates = suffix
        if len(_candidate_owners(candidates)) <= 1:
            return candidates

    frozen_libs = {
        part for part in PurePosixPath(record_relative).parts if part.endswith(".libs")
    }
    if frozen_libs:
        libs_matches = [
            candidate
            for candidate in candidates
            if frozen_libs.intersection(PurePosixPath(candidate[1]).parts)
        ]
        if libs_matches:
            candidates = libs_matches
            if len(_candidate_owners(candidates)) <= 1:
                return candidates

    binary = binary_path.read_bytes()
    embedded_owner = [
        candidate
        for candidate in candidates
        if candidate[1].split("/", 1)[0].encode() in binary
    ]
    return embedded_owner or candidates


def _distribution_native_owner(
    path: Path,
    record_relative: str,
    by_basename: dict[str, list[tuple[metadata.Distribution, str, Path]]],
    source_hashes: dict[str, str],
    frozen_versions: dict[str, str],
) -> dict[str, Any] | None:
    candidates = by_basename.get(path.name, [])
    target_hash = _sha256(path)
    matching = [
        candidate
        for candidate in candidates
        if source_hashes.get(str(candidate[2])) == target_hash
    ]
    patched_note: str | None = None
    if matching:
        candidates = _disambiguate_distribution_candidates(
            matching,
            record_relative,
            path,
        )
    elif sys.platform.startswith("linux") or sys.platform == "darwin":
        expected_kind = "elf" if sys.platform.startswith("linux") else "macho"
        target_kind = _native_binary_kind(path)
        binary_candidates = [
            candidate
            for candidate in candidates
            if target_kind == expected_kind
            and _native_binary_kind(candidate[2]) == expected_kind
        ]
        path_matches = [
            candidate
            for candidate in binary_candidates
            if candidate[1] == record_relative
            or candidate[1].endswith(f"/{record_relative}")
        ]
        if not path_matches:
            path_matches = [
                candidate
                for candidate in binary_candidates
                if PurePosixPath(candidate[1]).name
                == PurePosixPath(record_relative).name
            ]
        candidates = _disambiguate_distribution_candidates(
            path_matches,
            record_relative,
            path,
        )
        if path_matches:
            patched_note = (
                "binary patched by the freezer (RPATH)"
                if expected_kind == "elf"
                else "binary patched by the freezer (install name)"
            )
    else:
        candidates = []
    owners = {
        (_canonical(candidate[0].metadata["Name"]), candidate[0].version)
        for candidate in candidates
    }
    if not owners:
        return None
    if len(owners) != 1:
        detail = ", ".join(f"{name}=={version}" for name, version in sorted(owners))
        raise NoticeError(f"{path}: native library has ambiguous owners ({detail})")
    name, version = owners.pop()
    dist = next(
        candidate[0]
        for candidate in candidates
        if _canonical(candidate[0].metadata["Name"]) == name
    )
    note = {"notice": patched_note} if patched_note else {}
    if _is_gcc_runtime(path):
        display_name = dist.metadata["Name"]
        gcc_version = _gcc_runtime_version(
            display_name,
            dist.version,
            frozen_versions.get(_canonical(display_name)),
            _compiler_record(dist),
            path,
        )
        if gcc_version:
            return {
                "kind": "gcc",
                "name": "GCC runtime",
                "version": gcc_version,
                "provider": display_name,
                "provider_version": dist.version,
                **note,
            }
        licences = _distribution_licences(dist)
        if not licences:
            raise NoticeError(
                f"{path}: unresolved GCC runtime provider {display_name} "
                "has no bundled licence file"
            )
        return {
            "kind": "gcc-unresolved",
            "name": "GCC runtime library, exact GCC release undetermined",
            "provider": display_name,
            "provider_version": dist.version,
            "source_url": "https://gcc.gnu.org/",
            "licence_files": licences,
            **note,
        }
    return {
        "kind": "python",
        "name": dist.metadata["Name"],
        "version": version,
        **note,
    }


def _owner_for_python_native(
    path: Path,
    backend_dir: Path,
    by_basename: dict[str, list[tuple[metadata.Distribution, str, Path]]],
    source_hashes: dict[str, str],
    frozen_versions: dict[str, str],
    interpreter_candidates: dict[str, list[tuple[Path, dict[str, Any]]]],
) -> dict[str, Any]:
    interpreter_owner = _interpreter_native_owner(path, interpreter_candidates)
    if interpreter_owner is not None:
        return interpreter_owner
    relative = path.relative_to(backend_dir).as_posix()
    if relative.startswith("lib/"):
        relative = relative[4:]
    owner = _distribution_native_owner(
        path,
        relative,
        by_basename,
        source_hashes,
        frozen_versions,
    )
    if owner is None:
        raise NoticeError(
            f"{path}: native library has no unique owner "
            "(no installed distribution matches)"
        )
    return owner


def _python_distribution_index(
    distributions: dict[str, metadata.Distribution],
) -> dict[str, set[str]]:
    """Map top-level names under ``lib/`` to build-environment distributions.

    Keys are importable names plus any top-level folder a distribution's
    ``RECORD`` lists, such as the ``numpy.libs`` DLL folder of a Windows wheel.
    """
    result: dict[str, set[str]] = defaultdict(set)
    for canonical, dist in distributions.items():
        top_levels = {
            line.strip()
            for line in (dist.read_text("top_level.txt") or "").splitlines()
            if line.strip()
        }
        for item in dist.files or []:
            item_text = str(item).replace("\\", "/")
            parts = PurePosixPath(item_text).parts
            if (
                not parts
                or item_text.startswith("../")
                or parts[0].endswith((".dist-info", ".egg-info", ".data"))
                or parts[0] == "licenses"
            ):
                continue
            top_level = parts[0]
            if len(parts) == 1:
                match = re.match(
                    r"^(.+?)(?:\.pyc?|\.(?:cpython-[^.]+|abi3)\.(?:so|pyd))$",
                    top_level,
                )
                if match:
                    top_level = match.group(1)
                else:
                    continue
                if re.fullmatch(r"[A-Za-z_]\w*", top_level):
                    top_levels.add(top_level)
            else:
                result[top_level].add(canonical)
        for top_level in top_levels:
            if re.fullmatch(r"[A-Za-z_]\w*", top_level):
                result[top_level].add(canonical)
    return result


def _module_top_level(path: str) -> str | None:
    parts = PurePosixPath(path).parts
    if not parts or any(part.endswith(".dist-info") for part in parts):
        return None
    top_level = parts[0]
    if len(parts) == 1:
        match = re.fullmatch(r"(.+?)\.pyc?", top_level)
        if not match:
            return None
        top_level = match.group(1)
    return top_level if re.fullmatch(r"[A-Za-z_]\w*", top_level) else None


def _python_module_owner(
    top_level: str,
    path: str,
    distribution_index: dict[str, set[str]],
    distributions: dict[str, metadata.Distribution],
) -> tuple[dict[str, Any], set[str]]:
    if top_level in sys.stdlib_module_names or top_level.startswith("_sysconfigdata_"):
        return (
            {
                "kind": "cpython",
                "name": "CPython",
                "version": platform.python_version(),
            },
            set(),
        )
    if top_level == "BUILD_CONSTANTS":
        name = _canonical("cx-Freeze")
        dist = distributions.get(name)
        if dist is None:
            raise NoticeError(f"{path}: cx_Freeze distribution metadata is missing")
        return (
            {"kind": "python", "name": dist.metadata["Name"], "version": dist.version},
            {name},
        )
    if re.fullmatch(r"__(?:init|main)__nightcrate_backend", top_level):
        return ({"kind": "project", "name": "NightCrate"}, set())
    names = distribution_index.get(top_level, set())
    if not names:
        raise NoticeError(
            f"{path}: shipped Python module {top_level!r} has no distribution owner"
        )
    if len(names) != 1:
        detail = ", ".join(sorted(names))
        raise NoticeError(
            f"{path}: shipped Python module {top_level!r} has ambiguous "
            f"distribution owners ({detail})"
        )
    name = next(iter(names))
    dist = distributions[name]
    return (
        {"kind": "python", "name": dist.metadata["Name"], "version": dist.version},
        {name},
    )


def _frozen_python_inventory(
    backend_dir: Path,
    distributions: dict[str, metadata.Distribution],
) -> tuple[list[dict[str, Any]], set[str]]:
    distribution_index = _python_distribution_index(distributions)
    modules: list[dict[str, Any]] = []
    names: set[str] = set()
    library = backend_dir / "lib"
    archive = library / "library.zip"
    if archive.is_file():
        try:
            with zipfile.ZipFile(archive) as frozen_zip:
                entries = sorted(
                    entry for entry in frozen_zip.namelist() if not entry.endswith("/")
                )
        except (OSError, zipfile.BadZipFile) as exc:
            raise NoticeError(
                f"cannot inspect frozen Python archive {archive}: {exc}"
            ) from exc
        for entry in entries:
            top_level = _module_top_level(entry)
            if top_level is None:
                continue
            module_path = f"lib/library.zip!{entry}"
            owner, component_names = _python_module_owner(
                top_level,
                module_path,
                distribution_index,
                distributions,
            )
            modules.append({"path": module_path, "owner": owner})
            names.update(component_names)
    if library.is_dir():
        for child in sorted(library.iterdir()):
            if child == archive or child.name.endswith(".dist-info"):
                continue
            top_level = child.name if child.is_dir() else _module_top_level(child.name)
            if top_level is None or top_level in sys.stdlib_module_names:
                continue
            if top_level == "nightcrate":
                continue
            component_names = distribution_index.get(top_level, set())
            if not component_names:
                raise NoticeError(
                    f"{child.relative_to(backend_dir).as_posix()}: shipped Python "
                    f"module {top_level!r} has no distribution owner"
                )
            names.update(component_names)
    return modules, names


def _python_components(
    backend_dir: Path,
    native_owners: list[dict[str, Any]],
    distributions: dict[str, metadata.Distribution],
    policy: dict[str, Any],
    frozen_versions: dict[str, str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    names = {
        _canonical(owner["name"])
        for owner in native_owners
        if owner["kind"] == "python"
    }
    modules, frozen_names = _frozen_python_inventory(backend_dir, distributions)
    names.update(frozen_names)
    names.update(frozen_versions)
    names.update({_canonical("cx-Freeze"), _canonical("freeze-core")})
    names.discard("nightcrate")
    result: list[dict[str, Any]] = []
    for name in sorted(names):
        dist = distributions.get(name)
        if dist is None:
            raise NoticeError(
                f"{name}: shipped Python distribution metadata is missing"
            )
        frozen_version = frozen_versions.get(name)
        if frozen_version is not None and dist.version != frozen_version:
            raise NoticeError(
                f"{dist.metadata['Name']}: build-environment version {dist.version} "
                f"does not match frozen version {frozen_version}"
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
                "authors": _declared_authors(dist.metadata.get("Author")),
                "licence_files": licences,
            }
        )
    return result, modules


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
        package_data: dict[str, Any] = {}
        package_json = install_dir / "package.json"
        if package_json.is_file():
            try:
                package_data = json.loads(package_json.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise NoticeError(
                    f"{name}: cannot read installed package.json: {exc}"
                ) from exc
        authors = _declared_authors(item.get("author") or package_data.get("author"))
        authors.extend(
            author
            for author in _declared_authors(
                item.get("contributors") or package_data.get("contributors")
            )
            if author not in authors
        )
        result.append(
            {
                "kind": "frontend",
                "name": name,
                "version": version,
                "licence": expression,
                "selected_licence": selected,
                "source_url": f"https://www.npmjs.com/package/{name}/v/{version}",
                "authors": authors,
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
                "authors": _declared_authors(item.get("authors")),
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


def _appimage_backend_record_path(path: Path, appimage: Path) -> str | None:
    parts = path.relative_to(appimage).parts
    backend_indices = [
        index for index, part in enumerate(parts) if part.lower() == "backend"
    ]
    if not backend_indices:
        return None
    tail = list(parts[backend_indices[-1] + 1 :])
    if tail and tail[0].lower() == "lib":
        tail = tail[1:]
    return PurePosixPath(*tail).as_posix() if tail else None


def _appimage_backend_relative_path(path: Path, appimage: Path) -> str | None:
    parts = path.relative_to(appimage).parts
    backend_indices = [
        index for index, part in enumerate(parts) if part.lower() == "backend"
    ]
    if not backend_indices:
        return None
    tail = parts[backend_indices[-1] + 1 :]
    return PurePosixPath(*tail).as_posix() if tail else None


# auditwheel renames each library it vendors with an 8-hex-digit content hash,
# for example ``libLerc-d21eeb01.so.4``; no system library carries such a name.
_WHEEL_VENDORED_NAME = re.compile(r"-[0-9a-f]{8}\.so(?:\.\d+)*$")


def _appimage_copy_owner(
    owner: dict[str, Any], copy_note: str = "copied by the AppImage bundler"
) -> dict[str, Any]:
    inherited = dict(owner)
    if inherited.get("notice"):
        inherited["notice"] = f"{inherited['notice']}; {copy_note}"
    else:
        inherited["notice"] = copy_note
    return inherited


def _appimage_copy_of(
    matches: list[dict[str, Any]], relative: str, copy_note: str
) -> dict[str, Any]:
    """Owner of an AppImage copy of a library the frozen backend ships.

    numpy and scipy ship byte-identical GCC runtimes; the bundler copies one
    of them, so identical originals may have several owners.
    """
    if len({item["sha256"] for item in matches}) != 1:
        raise NoticeError(
            f"{relative}: same-named frozen backend libraries differ, so the "
            "copy's owner is ambiguous"
        )
    owners = sorted(
        {json.dumps(item["owner"], sort_keys=True) for item in matches},
        key=lambda value: json.loads(value)["name"],
    )
    owner = _appimage_copy_owner(json.loads(owners[0]), copy_note)
    if len(owners) > 1:
        others = ", ".join(json.loads(value)["name"] for value in owners[1:])
        owner["notice"] = f"{owner['notice']}; identical copies also ship with {others}"
    return owner


def _system_natives(
    appimage: Path,
    backend_dir: Path,
    by_basename: dict[str, list[tuple[metadata.Distribution, str, Path]]],
    source_hashes: dict[str, str],
    frozen_versions: dict[str, str],
    backend_natives: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    backend_by_path = {item["path"]: item for item in backend_natives}
    backend_by_hash: dict[str, list[dict[str, Any]]] = defaultdict(list)
    backend_by_wheel_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in backend_natives:
        backend_by_hash[item["sha256"]].append(item)
        name = PurePosixPath(item["path"]).name
        if _WHEEL_VENDORED_NAME.search(name):
            backend_by_wheel_name[name].append(item)
    natives: list[dict[str, Any]] = []
    packages: dict[tuple[str, str], dict[str, Any]] = {}
    for path in sorted(appimage.rglob("*")):
        if not path.is_file() or not _is_native(path):
            continue
        relative = path.relative_to(appimage).as_posix()
        digest = _sha256(path)
        backend_relative = _appimage_backend_relative_path(path, appimage)
        backend_match = (
            backend_by_path.get(backend_relative)
            if backend_relative is not None
            else None
        )
        if backend_match is not None:
            natives.append(
                {
                    "path": relative,
                    "sha256": digest,
                    "owner": _appimage_copy_owner(backend_match["owner"]),
                }
            )
            continue
        hash_matches = backend_by_hash.get(digest, [])
        if hash_matches:
            natives.append(
                {
                    "path": relative,
                    "sha256": digest,
                    "owner": _appimage_copy_of(
                        hash_matches, relative, "copied by the AppImage bundler"
                    ),
                }
            )
            continue
        # linuxdeploy rewrites the RPATH of each library it copies, so the copy
        # of a wheel-vendored library no longer matches the backend's bytes.
        name_matches = backend_by_wheel_name.get(path.name, [])
        if name_matches:
            natives.append(
                {
                    "path": relative,
                    "sha256": digest,
                    "owner": _appimage_copy_of(
                        name_matches,
                        relative,
                        "copied by the AppImage bundler, which rewrote its "
                        "library path",
                    ),
                }
            )
            continue
        record_relative = _appimage_backend_record_path(path, appimage)
        if record_relative is not None:
            try:
                python_owner = _distribution_native_owner(
                    path,
                    record_relative,
                    by_basename,
                    source_hashes,
                    frozen_versions,
                )
            except NoticeError as exc:
                raise NoticeError(f"{relative}: {exc}") from exc
            if python_owner is not None:
                natives.append(
                    {
                        "path": relative,
                        "sha256": digest,
                        "owner": python_owner,
                    }
                )
                continue
        try:
            owner, copyright_text = _dpkg_owner(path)
        except NoticeError as exc:
            raise NoticeError(f"{relative}: {exc}") from exc
        natives.append(
            {
                "path": relative,
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
    owners: list[dict[str, Any]] = []
    interpreter_candidates = _interpreter_native_candidates()
    for path in sorted(backend_dir.rglob("*")):
        if not path.is_file() or not _is_native(path):
            continue
        relative = path.relative_to(backend_dir).as_posix()
        try:
            owner = _owner_for_python_native(
                path,
                backend_dir,
                by_basename,
                source_hashes,
                frozen_versions,
                interpreter_candidates,
            )
        except NoticeError as exc:
            raise NoticeError(f"{relative}: {exc}") from exc
        owners.append(owner)
        natives.append(
            {
                "path": relative,
                "sha256": _sha256(path),
                "owner": owner,
            }
        )
    python_components, python_modules = _python_components(
        backend_dir,
        owners,
        distributions,
        policy,
        frozen_versions,
    )
    frontend_components = _frontend_components(policy)
    rust_components = _rust_components(shell_dir.resolve(), policy)
    system_components: list[dict[str, Any]] = []
    if appimage is not None:
        if not appimage.is_dir():
            raise NoticeError(f"extracted AppImage directory is missing: {appimage}")
        appimage_natives, system_components = _system_natives(
            appimage.resolve(),
            backend_dir,
            by_basename,
            source_hashes,
            frozen_versions,
            natives,
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
        "python_modules": python_modules,
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


def _gcc_source_versions(inventory_data: dict[str, Any]) -> set[str]:
    return {
        item["owner"]["version"]
        for item in inventory_data["native_libraries"]
        if item["owner"]["kind"] == "gcc"
    }


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
        for gcc_version in sorted(_gcc_source_versions(inventory_data)):
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


def _component_licence_files(
    component: dict[str, Any], licence_text_dir: Path
) -> list[dict[str, str]]:
    bundled = component.get("licence_files", [])
    if bundled:
        return bundled
    authors = _declared_authors(component.get("authors")) or ["the package authors"]
    copyright_line = f"Copyright: {', '.join(authors)}"
    result: list[dict[str, str]] = []
    for identifier in _licence_identifiers(component["selected_licence"]):
        path = licence_text_dir / f"{identifier}.txt"
        if not path.is_file():
            raise NoticeError(
                f"{component['name']}: canonical licence text is missing for "
                f"{identifier} ({path})"
            )
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            raise NoticeError(
                f"{component['name']}: canonical licence text is empty for {identifier}"
            )
        result.append(
            {
                "name": f"SPDX {identifier}",
                "text": f"{copyright_line}\n\n{text}\n",
            }
        )
    if not result:
        raise NoticeError(f"{component['name']}: chosen licence has no identifiers")
    return result


def _notices_text(
    inventory_data: dict[str, Any],
    archive_name: str,
    licence_text_dir: Path = LICENCE_TEXT_DIR,
) -> str:
    has_unresolved_gcc = any(
        item["owner"]["kind"] == "gcc-unresolved"
        for item in inventory_data["native_libraries"]
    )
    source_summary = (
        "The exact sources for bundled LGPL components with identified releases are in:"
        if has_unresolved_gcc
        else "The exact sources for bundled LGPL components are in:"
    )
    lines = [
        "NightCrate third-party notices",
        "==============================",
        "",
        f"Build: NightCrate {inventory_data['project']['version']} "
        f"({inventory_data['platform']}/{inventory_data['architecture']})",
        "",
        source_summary,
        f"  {archive_name}",
        "",
        "Components",
        "----------",
    ]
    text_groups: dict[str, dict[str, Any]] = {}

    def add_licence_text(text: str, user: str) -> None:
        text = text.rstrip() + "\n"
        digest = hashlib.sha256(text.encode()).hexdigest()
        group = text_groups.setdefault(digest, {"text": text, "users": []})
        group["users"].append(user)

    for component in inventory_data["components"]:
        lines.append(
            f"- [{component['kind']}] {component['name']} {component['version']}: "
            f"{component['licence']} (accepted as {component['selected_licence']})"
        )
        lines.append(f"  Source: {component['source_url']}")
        for licence_file in _component_licence_files(component, licence_text_dir):
            add_licence_text(
                licence_file["text"],
                f"{component['name']} {component['version']} ({licence_file['name']})",
            )
    lines.extend(["", "Native libraries", "----------------"])
    for item in inventory_data["native_libraries"]:
        owner = item["owner"]
        provider = ""
        if owner.get("provider"):
            provider = f", provided by {owner['provider']} {owner['provider_version']}"
        version = f" {owner['version']}" if owner.get("version") else ""
        owner_label = (
            owner["name"]
            if owner["kind"] == "gcc-unresolved"
            else f"{owner['kind']} {owner['name']}{version}"
        )
        lines.append(
            f"- {item['path']}: {owner_label} (sha256 {item['sha256']}{provider})"
        )
        if owner.get("notice"):
            lines.append(f"  Notice: {owner['notice']}")
        if owner.get("source_url"):
            lines.append(f"  Source: {owner['source_url']}")
        for licence_file in owner.get("licence_files", []):
            add_licence_text(
                licence_file["text"],
                f"{item['path']} ({licence_file['name']})",
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


def render(
    inventory_path: Path, out: Path, *, allow_unresolved_gcc: bool = False
) -> Path:
    inventory_data = json.loads(inventory_path.read_text(encoding="utf-8"))
    if inventory_data.get("schema") != 1:
        raise NoticeError(f"unsupported inventory schema in {inventory_path}")
    unresolved = [
        item
        for item in inventory_data["native_libraries"]
        if item["owner"]["kind"] == "gcc-unresolved"
    ]
    if unresolved and not allow_unresolved_gcc:
        paths = ", ".join(item["path"] for item in unresolved)
        raise NoticeError(f"unresolved GCC runtime libraries: {paths}")
    for item in unresolved:
        print(
            f"warning: {item['path']}: GCC runtime library, exact GCC release "
            "undetermined; omitted from the exact-source archive",
            file=sys.stderr,
        )
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
    render_parser.add_argument(
        "--allow-unresolved-gcc",
        action="store_true",
        help="allow test builds with GCC runtimes whose exact release is unknown",
    )
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
            archive = render(
                args.inventory,
                args.out,
                allow_unresolved_gcc=args.allow_unresolved_gcc,
            )
            print(f"wrote {args.out / 'licences'} and {archive}")
    except NoticeError as exc:
        print(f"licence notices failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
