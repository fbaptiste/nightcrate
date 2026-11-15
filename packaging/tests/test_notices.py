from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

from notices import (  # noqa: E402
    NoticeError,
    _check_mpl_tree,
    _gcc_runtime_version,
    evaluate_licence,
    has_applied_mpl_incompatibility,
    load_policy,
)


POLICY = load_policy(Path(__file__).parents[1] / "licence_policy.toml")


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


def test_gcc_runtime_rejects_missing_gcc_record() -> None:
    with pytest.raises(NoticeError, match="compiler record does not name gcc"):
        _gcc_runtime_version(
            "scipy",
            "1.17.1",
            "1.17.1",
            None,
            Path("libquadmath.0.dylib"),
        )
