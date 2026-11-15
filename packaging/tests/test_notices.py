from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

import notices  # noqa: E402
from notices import (  # noqa: E402
    NoticeError,
    _check_mpl_tree,
    _gcc_runtime_version,
    _gcc_source_versions,
    _interpreter_native_candidates,
    _notices_text,
    _owner_for_python_native,
    _run,
    _system_natives,
    evaluate_licence,
    has_applied_mpl_incompatibility,
    load_policy,
    render,
)


POLICY = load_policy(Path(__file__).parents[1] / "licence_policy.toml")


def test_subprocess_output_is_decoded_as_strict_utf8() -> None:
    output = _run(
        [
            sys.executable,
            "-c",
            "import os; os.write(1, 'Ł'.encode('utf-8'))",
        ]
    )

    assert output == "Ł"


def test_invalid_utf8_subprocess_output_fails_with_command_name() -> None:
    command = [
        sys.executable,
        "-c",
        "import os; os.write(1, b'\\x81')",
    ]

    with pytest.raises(NoticeError, match="produced output that is not valid UTF-8"):
        _run(command)


def test_or_expression_accepts_one_allowed_alternative() -> None:
    assert evaluate_licence("example", "MIT OR Proprietary", POLICY) == "MIT"


def test_r_efi_uses_the_reviewed_mit_alternative() -> None:
    expression = "MIT OR Apache-2.0 OR LGPL-2.1-or-later"
    assert evaluate_licence("r-efi", expression, POLICY) == "MIT"


def test_scoped_cdla_exception_is_limited_to_webpki_root_certs() -> None:
    assert (
        evaluate_licence("webpki-root-certs", "CDLA-Permissive-2.0", POLICY)
        == "CDLA-Permissive-2.0"
    )
    with pytest.raises(NoticeError, match="other-roots"):
        evaluate_licence("other-roots", "CDLA-Permissive-2.0", POLICY)


def test_unknown_licence_fails_with_package_name() -> None:
    with pytest.raises(NoticeError, match="mystery-package"):
        evaluate_licence("mystery-package", "LicenseRef-Unknown", POLICY)


def test_applied_mpl_incompatibility_notice_fails(tmp_path: Path) -> None:
    header = """/* This Source Code Form is Incompatible With Secondary Licenses,
    as defined by the Mozilla Public License, v. 2.0. */
    """
    assert has_applied_mpl_incompatibility(header)
    (tmp_path / "source.rs").write_text(header, encoding="utf-8")
    with pytest.raises(NoticeError, match="mpl-component"):
        _check_mpl_tree("mpl-component", tmp_path)


def test_plain_mpl_licence_template_does_not_apply_exhibit_b(tmp_path: Path) -> None:
    standard_text = "\n".join(
        [
            "Mozilla Public License Version 2.0",
            "1. Definitions",
            "Exhibit A - Source Code Form License Notice",
            "Exhibit B - Incompatible With Secondary Licenses Notice",
            "This Source Code Form is Incompatible With Secondary Licenses",
        ]
    )
    assert not has_applied_mpl_incompatibility(standard_text)
    (tmp_path / "NOTICE").write_text(standard_text, encoding="utf-8")
    _check_mpl_tree("plain-mpl-component", tmp_path)


def test_gcc_runtime_rejects_scipy_version_mismatch() -> None:
    with pytest.raises(NoticeError, match="does not match frozen version"):
        _gcc_runtime_version(
            "scipy",
            "1.17.1",
            "1.17.0",
            {"name": "gcc", "version": "13.4.0"},
            Path("libquadmath.0.dylib"),
        )


def test_gcc_runtime_without_compiler_evidence_is_unresolved() -> None:
    assert (
        _gcc_runtime_version(
            "scipy",
            "1.17.1",
            "1.17.1",
            None,
            Path("libquadmath.0.dylib"),
        )
        is None
    )


def _native_owner(
    frozen_file: Path,
    candidates: dict[str, list[tuple[Path, dict[str, object]]]],
) -> dict[str, object]:
    return _owner_for_python_native(
        frozen_file,
        frozen_file.parent,
        {},
        {},
        {},
        candidates,
    )


def test_unlisted_windows_dlls_file_is_attributed_by_name_and_hash(
    tmp_path: Path,
) -> None:
    interpreter = tmp_path / "python"
    dlls = interpreter / "DLLs"
    dlls.mkdir(parents=True)
    source = dlls / "zlib1.dll"
    source.write_bytes(b"CPython bundled DLL")
    frozen = tmp_path / "frozen" / "zlib1.dll"
    frozen.parent.mkdir()
    frozen.write_bytes(source.read_bytes())
    candidates = _interpreter_native_candidates(
        interpreter,
        tmp_path / "platstdlib",
        "3.14.0",
    )

    owner = _native_owner(frozen, candidates)

    assert owner == {"kind": "cpython", "name": "CPython", "version": "3.14.0"}


def test_posix_lib_dynload_extension_is_attributed_to_cpython(
    tmp_path: Path,
) -> None:
    platstdlib = tmp_path / "platstdlib"
    lib_dynload = platstdlib / "lib-dynload"
    lib_dynload.mkdir(parents=True)
    source = lib_dynload / "_asyncio.cpython-314-test.so"
    source.write_bytes(b"CPython POSIX extension")
    frozen = tmp_path / "frozen" / source.name
    frozen.parent.mkdir()
    frozen.write_bytes(source.read_bytes())
    candidates = _interpreter_native_candidates(
        tmp_path / "python",
        platstdlib,
        "3.14.0",
    )

    owner = _native_owner(frozen, candidates)

    assert owner == {"kind": "cpython", "name": "CPython", "version": "3.14.0"}


def test_unknown_pyd_still_fails(tmp_path: Path) -> None:
    interpreter = tmp_path / "python"
    dlls = interpreter / "DLLs"
    dlls.mkdir(parents=True)
    (dlls / "unknown.pyd").write_bytes(b"different interpreter extension")
    frozen = tmp_path / "frozen" / "unknown.pyd"
    frozen.parent.mkdir()
    frozen.write_bytes(b"unknown extension")
    candidates = _interpreter_native_candidates(
        interpreter,
        tmp_path / "platstdlib",
        "3.14.0",
    )

    with pytest.raises(NoticeError, match="unknown.pyd.*no unique owner"):
        _native_owner(frozen, candidates)


class _FakeDistribution:
    def __init__(self, name: str = "pycryptodomex", version: str = "3.23.0"):
        self.metadata = {"Name": name}
        self.version = version


def test_hash_mismatched_elf_record_path_is_attributed_with_freezer_note(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(notices.sys, "platform", "linux")
    record_path = "Cryptodome/Cipher/_ARC4.abi3.so"
    source = tmp_path / "installed" / record_path
    source.parent.mkdir(parents=True)
    source.write_bytes(b"\x7fELForiginal")
    appimage = tmp_path / "appimage"
    backend = tmp_path / "backend"
    backend.mkdir()
    frozen = appimage / "usr" / "lib" / "NightCrate" / "backend" / "lib" / record_path
    frozen.parent.mkdir(parents=True)
    frozen.write_bytes(b"\x7fELFpatched-rpath")
    distribution = _FakeDistribution()
    by_basename = {source.name: [(distribution, record_path, source)]}

    monkeypatch.setattr(
        notices,
        "_dpkg_owner",
        lambda _path: pytest.fail("distribution-owned binary reached dpkg"),
    )
    natives, system_components = _system_natives(
        appimage,
        backend,
        by_basename,
        {str(source): notices._sha256(source)},
        {},
    )

    assert system_components == []
    assert len(natives) == 1
    owner = natives[0]["owner"]
    assert owner["name"] == "pycryptodomex"
    assert owner["notice"] == "binary patched by the freezer (RPATH)"


def test_hash_mismatched_elf_without_record_path_falls_through_to_dpkg(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(notices.sys, "platform", "linux")
    appimage = tmp_path / "appimage"
    frozen = (
        appimage
        / "usr"
        / "lib"
        / "NightCrate"
        / "backend"
        / "lib"
        / "Cryptodome"
        / "Cipher"
        / "_ARC4.abi3.so"
    )
    frozen.parent.mkdir(parents=True)
    frozen.write_bytes(b"\x7fELFpatched-rpath")
    backend = tmp_path / "backend"
    backend.mkdir()
    dpkg_calls: list[Path] = []

    def failing_dpkg(path: Path) -> tuple[dict[str, str], str]:
        dpkg_calls.append(path)
        raise NoticeError("dpkg lookup failed")

    monkeypatch.setattr(notices, "_dpkg_owner", failing_dpkg)

    with pytest.raises(NoticeError, match="dpkg lookup failed"):
        _system_natives(
            appimage,
            backend,
            {},
            {},
            {},
        )

    assert dpkg_calls == [frozen]


def test_linux_freeze_core_relocation_is_attributed_by_basename(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(notices.sys, "platform", "linux")
    filename = "_bz2.cpython-314-x86_64-linux-gnu.so"
    record_path = f"freeze_core/lib/{filename}"
    source = tmp_path / "installed" / record_path
    source.parent.mkdir(parents=True)
    source.write_bytes(b"\x7fELForiginal")
    backend = tmp_path / "backend"
    frozen = backend / "lib" / filename
    frozen.parent.mkdir(parents=True)
    frozen.write_bytes(b"\x7fELFpatched-rpath")
    distribution = _FakeDistribution("freeze-core", "0.8.1")

    owner = _owner_for_python_native(
        frozen,
        backend,
        {filename: [(distribution, record_path, source)]},
        {str(source): notices._sha256(source)},
        {},
        {},
    )

    assert owner["name"] == "freeze-core"
    assert owner["notice"] == "binary patched by the freezer (RPATH)"


def test_ambiguous_relocated_basename_still_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(notices.sys, "platform", "linux")
    filename = "libshared.so"
    first = tmp_path / "installed" / "alpha.libs" / filename
    second = tmp_path / "installed" / "beta.libs" / filename
    first.parent.mkdir(parents=True)
    second.parent.mkdir(parents=True)
    first.write_bytes(b"\x7fELFalpha")
    second.write_bytes(b"\x7fELFbeta")
    backend = tmp_path / "backend"
    frozen = backend / "lib" / filename
    frozen.parent.mkdir(parents=True)
    frozen.write_bytes(b"\x7fELFpatched-without-owner-path")
    alpha = _FakeDistribution("alpha")
    beta = _FakeDistribution("beta")
    candidates = [
        (alpha, f"alpha.libs/{filename}", first),
        (beta, f"beta.libs/{filename}", second),
    ]

    with pytest.raises(NoticeError, match="ambiguous owners.*alpha.*beta"):
        _owner_for_python_native(
            frozen,
            backend,
            {filename: candidates},
            {
                str(first): notices._sha256(first),
                str(second): notices._sha256(second),
            },
            {},
            {},
        )


@pytest.mark.parametrize(
    ("libs_directory", "expected_owner"),
    [("numpy.libs", "numpy"), ("scipy.libs", "scipy")],
)
def test_identical_hashes_are_disambiguated_by_frozen_record_path(
    tmp_path: Path,
    libs_directory: str,
    expected_owner: str,
) -> None:
    filename = "x.so"
    shared_bytes = b"\x7fELFidentical-library"
    numpy_source = tmp_path / "installed" / "numpy.libs" / filename
    scipy_source = tmp_path / "installed" / "scipy.libs" / filename
    numpy_source.parent.mkdir(parents=True)
    scipy_source.parent.mkdir(parents=True)
    numpy_source.write_bytes(shared_bytes)
    scipy_source.write_bytes(shared_bytes)
    backend = tmp_path / "backend"
    frozen = backend / "lib" / libs_directory / filename
    frozen.parent.mkdir(parents=True)
    frozen.write_bytes(shared_bytes)
    numpy = _FakeDistribution("numpy", "2.4.4")
    scipy = _FakeDistribution("scipy", "1.17.1")
    candidates = [
        (numpy, f"numpy.libs/{filename}", numpy_source),
        (scipy, f"scipy.libs/{filename}", scipy_source),
    ]

    owner = _owner_for_python_native(
        frozen,
        backend,
        {filename: candidates},
        {
            str(numpy_source): notices._sha256(numpy_source),
            str(scipy_source): notices._sha256(scipy_source),
        },
        {},
        {},
    )

    assert owner["name"] == expected_owner


def test_vcruntime_is_a_system_library(tmp_path: Path) -> None:
    interpreter = tmp_path / "python"
    interpreter.mkdir()
    source = interpreter / "vcruntime140.dll"
    source.write_bytes(b"MSVC runtime")
    frozen = tmp_path / "frozen" / "vcruntime140.dll"
    frozen.parent.mkdir()
    frozen.write_bytes(source.read_bytes())
    candidates = _interpreter_native_candidates(
        interpreter,
        tmp_path / "platstdlib",
        "3.14.0",
    )

    owner = _native_owner(frozen, candidates)

    assert owner["name"] == "Microsoft Visual C++ runtime"
    assert owner["system_library"] is True
    assert "GPLv3 §1 System Library" in str(owner["notice"])


def test_linux_elf_comment_is_second_gcc_version_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(notices.sys, "platform", "linux")
    monkeypatch.setattr(notices, "_elf_gcc_version", lambda _path: "12.3.0")

    version = _gcc_runtime_version(
        "numpy",
        "2.4.4",
        "2.4.4",
        {"name": "clang", "version": "18.0.0"},
        Path("libgfortran.so.5"),
    )

    assert version == "12.3.0"


def test_unresolved_gcc_requires_flag_and_renders_warning_without_source_archive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    unresolved = {
        "path": "lib/numpy.libs/libgfortran.so.5",
        "sha256": "abc123",
        "owner": {
            "kind": "gcc-unresolved",
            "name": "GCC runtime library, exact GCC release undetermined",
            "provider": "numpy",
            "provider_version": "2.4.4",
            "source_url": "https://gcc.gnu.org/",
            "licence_files": [
                {"name": "LICENSE.txt", "text": "Provider bundled licence"}
            ],
        },
    }
    inventory = {
        "schema": 1,
        "project": {"version": "1.2.3"},
        "platform": "linux",
        "architecture": "x86_64",
        "cpython_licence": "CPython licence",
        "cx_freeze_licence": "cx_Freeze licence",
        "components": [],
        "native_libraries": [unresolved],
    }
    inventory_path = tmp_path / "inventory.json"
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")

    with pytest.raises(NoticeError, match="libgfortran.so.5"):
        render(inventory_path, tmp_path / "blocked")

    def fake_source_archive(data: dict[str, object], out: Path) -> Path:
        assert _gcc_source_versions(data) == set()
        archive = out / "sources.tar.gz"
        archive.write_bytes(b"")
        return archive

    monkeypatch.setattr(notices, "_source_archive", fake_source_archive)
    out = tmp_path / "allowed"
    render(inventory_path, out, allow_unresolved_gcc=True)

    warning = capsys.readouterr().err
    rendered = (out / "licences" / "THIRD_PARTY_NOTICES.txt").read_text(
        encoding="utf-8"
    )
    assert "lib/numpy.libs/libgfortran.so.5" in warning
    assert "omitted from the exact-source archive" in warning
    assert "GCC runtime library, exact GCC release undetermined" in rendered
    assert "https://gcc.gnu.org/" in rendered
    assert "Provider bundled licence" in rendered


def _inventory_with(component: dict[str, object]) -> dict[str, object]:
    return {
        "project": {"version": "1.2.3"},
        "platform": "test",
        "architecture": "test",
        "components": [component],
        "native_libraries": [],
    }


def test_missing_package_licence_renders_canonical_text_and_authors(
    tmp_path: Path,
) -> None:
    canonical_text = "MIT License\n\nPermission is hereby granted, free of charge"
    (tmp_path / "MIT.txt").write_text(canonical_text, encoding="utf-8")
    inventory = _inventory_with(
        {
            "kind": "rust",
            "name": "license-less-crate",
            "version": "1.0.0",
            "licence": "MIT",
            "selected_licence": "MIT",
            "source_url": "https://example.invalid/license-less-crate",
            "authors": ["Ada Example", "Grace Example"],
            "licence_files": [],
        }
    )

    notices = _notices_text(inventory, "sources.tar.gz", tmp_path)

    assert "Copyright: Ada Example, Grace Example" in notices
    assert canonical_text in notices
    assert "license-less-crate 1.0.0 (SPDX MIT)" in notices


def test_missing_canonical_licence_fails_with_component_name(tmp_path: Path) -> None:
    inventory = _inventory_with(
        {
            "kind": "frontend",
            "name": "missing-canonical-text",
            "version": "2.0.0",
            "licence": "MIT",
            "selected_licence": "MIT",
            "source_url": "https://example.invalid/missing-canonical-text",
            "authors": [],
            "licence_files": [],
        }
    )

    with pytest.raises(NoticeError, match="missing-canonical-text"):
        _notices_text(inventory, "sources.tar.gz", tmp_path)
