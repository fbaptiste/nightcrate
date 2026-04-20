"""Unit tests for the DSO type-group dispatch."""

from __future__ import annotations

from nightcrate.services.dso_type_groups import (
    TYPE_GROUPS,
    group_for_raw_type,
    raw_types_for_group,
)


def test_every_openngc_raw_type_has_a_group():
    # The 19 OpenNGC obj_type codes we know about (matches the CHECK
    # vocabulary in migration 0015).
    known = {
        "G",
        "GPair",
        "GTrpl",
        "GGroup",
        "HII",
        "EmN",
        "RfN",
        "PN",
        "OCl",
        "GCl",
        "Cl+N",
        "SNR",
        "DrkN",
        "Neb",
        "*Ass",
        "Nova",
        "*",
        "**",
        "Other",
    }
    for raw in known:
        group = group_for_raw_type(raw)
        # Every code must map to a group name from TYPE_GROUPS.
        assert group in {g.name for g in TYPE_GROUPS}, f"{raw!r} → {group!r}"


def test_cl_plus_n_falls_under_emission_nebula():
    assert group_for_raw_type("Cl+N") == "Emission Nebula"


def test_raw_types_for_emission_nebula_group():
    types = raw_types_for_group("Emission Nebula")
    assert set(types) == {"HII", "EmN", "Cl+N"}


def test_raw_types_for_galaxy_group():
    assert raw_types_for_group("Galaxy") == ("G",)


def test_unknown_group_returns_empty_tuple():
    assert raw_types_for_group("Nebula of the Gods") == ()


def test_unknown_raw_type_falls_to_other():
    assert group_for_raw_type("QuasarFuture") == "Other"


def test_display_order_is_unique_and_monotonic():
    orders = [g.display_order for g in TYPE_GROUPS]
    assert orders == sorted(orders)
    assert len(set(orders)) == len(orders)
