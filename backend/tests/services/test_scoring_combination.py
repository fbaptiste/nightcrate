"""Scoring combination / geometric-mean tests (spec §14.6)."""

from __future__ import annotations

import math

import pytest

from nightcrate.services.planner_scoring import _weighted_geometric_mean


def test_combination_all_ones():
    """All dimensions 1.0 → combined 1.0."""
    assert _weighted_geometric_mean([(1.0, 2.0), (1.0, 1.0), (1.0, 1.5), (1.0, 1.0)]) == 1.0


def test_combination_all_half():
    """All dimensions 0.5 → combined 0.5 regardless of weights."""
    assert _weighted_geometric_mean(
        [(0.5, 2.0), (0.5, 1.0), (0.5, 1.5), (0.5, 1.0)]
    ) == pytest.approx(0.5)


def test_combination_one_zero_collapses():
    """Any dimension at 0 with positive weight → combined 0."""
    assert _weighted_geometric_mean([(1.0, 2.0), (1.0, 1.0), (0.0, 1.5), (1.0, 1.0)]) == 0.0


def test_combination_three_at_nine_one_at_four():
    """Spec §9.2 example with equal weights: three at 0.9, one at 0.4
    → geometric mean ≈ 0.735 (beats arithmetic 0.775).

    Uses equal weights to match the spec's numerical claim — the
    default weight set (2, 1, 1.5, 1) produces ≈ 0.777.
    """
    raw = _weighted_geometric_mean([(0.9, 1.0), (0.9, 1.0), (0.9, 1.0), (0.4, 1.0)])
    assert raw == pytest.approx(0.735, abs=0.005)


def test_combination_default_weights_three_nine_one_four():
    """Same dimension scores with default weights (2, 1, 1.5, 1) →
    geometric mean ≈ 0.777. Pinned to catch drift in weight defaults.
    """
    raw = _weighted_geometric_mean([(0.9, 2.0), (0.9, 1.0), (0.9, 1.5), (0.4, 1.0)])
    assert raw == pytest.approx(0.777, abs=0.005)


def test_combination_zero_weight_drops_dimension():
    """A dimension with weight 0 contributes nothing → same result as omitting."""
    a = _weighted_geometric_mean([(0.9, 2.0), (0.2, 0.0), (0.8, 1.0)])
    b = _weighted_geometric_mean([(0.9, 2.0), (0.8, 1.0)])
    assert a == pytest.approx(b)


def test_combination_dropped_dimension_renormalises():
    """Fewer dimensions with same weights → geometric mean still proper.

    (obs=0.6, mer=0.8) weights (2, 1). Manual: (0.6^2 * 0.8^1) ^ (1/3).
    """
    raw = _weighted_geometric_mean([(0.6, 2.0), (0.8, 1.0)])
    expected = (0.6**2 * 0.8**1) ** (1 / 3)
    assert raw == pytest.approx(expected, abs=1e-6)


def test_combination_empty_returns_zero():
    """All weights zero / empty list → 0."""
    assert _weighted_geometric_mean([]) == 0.0
    assert _weighted_geometric_mean([(0.9, 0.0), (0.5, 0.0)]) == 0.0


def test_combination_matches_exp_formulation():
    """Sanity: the product form matches exp(sum(w * log(s)) / total_w)."""
    entries = [(0.7, 2.0), (0.9, 1.0), (0.5, 1.5), (0.85, 1.0)]
    raw = _weighted_geometric_mean(entries)
    total_w = sum(w for _, w in entries)
    expected = math.exp(sum(w * math.log(s) for s, w in entries) / total_w)
    assert raw == pytest.approx(expected, abs=1e-6)
