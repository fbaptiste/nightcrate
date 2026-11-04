"""Tests for the stated-match review screen."""

from __future__ import annotations

from pathlib import Path

from nightcrate.catalog_loader.match_review import flag_stated_matches, main
from nightcrate.catalog_loader.reconcile import NewObject, ObjectSet, StatedMatch


def _object(primary: str, size: float) -> NewObject:
    return NewObject(
        "test",
        primary,
        {
            "primary_designation": primary,
            "obj_type": "Neb",
            "maj_axis_arcmin": size,
            "source_row_hash": primary,
        },
        (),
        0,
    )


def test_screen_flags_target_part_and_size_ratio_with_evidence():
    new = ObjectSet(
        (_object("NGC 6960", 60), _object("NGC 7000", 10)),
        {},
        {},
        0,
        stated_matches=(
            StatedMatch("lbn", "191", 0, 210, 60, "catalog column"),
            StatedMatch("test", "2", 1, 35, 10, "OpenNGC alternate"),
        ),
    )

    flags = flag_stated_matches(new, {("LBN 191", "NGC 6960")})

    assert [(flag.designation, flag.reason) for flag in flags] == [
        ("LBN 191", "size_ratio"),
        ("LBN 191", "target_is_part"),
        ("TEST 2", "size_ratio"),
    ]
    assert all(flag.evidence for flag in flags)


def test_match_review_cli_prints_csv(capsys, tmp_path: Path):
    result = main([str(tmp_path / "catalogs")])

    assert result == 0
    assert capsys.readouterr().out.startswith(
        "designation,target_designation,reason,entry_size_arcmin,target_size_arcmin,evidence"
    )
