"""Constants for the Target Planner scoring algorithm (v0.21.0)."""

from __future__ import annotations

# Open clusters, globular clusters, and stellar associations — sparse
# bright stars, minimal surface emission to compete with skyglow.
# ``Cl+N`` is intentionally excluded: imagers of M8 / M16 / M20 target
# the nebulosity, which behaves like an emission nebula under moonlight.
CLUSTER_OBJ_TYPES: frozenset[str] = frozenset({"OCl", "GCl", "*Ass"})

# Filter lines the user can declare as session intent. Multi-band
# filters are represented by selecting multiple lines (L-eXtreme →
# {"Ha", "OIII"}).
FILTER_LINES: tuple[str, ...] = ("Ha", "SII", "OIII", "L", "R", "G", "B")

# Descending by score band.
QUALITY_LABELS: tuple[str, ...] = ("Excellent", "Good", "Fair", "Poor")
