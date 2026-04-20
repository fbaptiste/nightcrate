"""User-facing DSO type grouping.

OpenNGC's ``obj_type`` vocabulary has 19 codes (``G``, ``HII``, ``PN``, …)
that are accurate but too fine-grained for casual browsing. The UI's
primary filter bar uses these user-facing groups instead — e.g., the
"Emission Nebula" chip matches ``HII``, ``EmN``, and ``Cl+N`` together.

Raw codes remain available via an "Advanced filters" expander for power
users and tests.
"""

from __future__ import annotations

from dataclasses import dataclass

GROUP_OTHER = "Other"


@dataclass(frozen=True, slots=True)
class TypeGroup:
    name: str
    display_order: int
    raw_types: tuple[str, ...]


# Canonical order matches the display order the UI uses. Adding a new group
# requires updating the CHECK vocabulary on ``dso.obj_type`` in a migration
# AND adding the raw code here.
TYPE_GROUPS: tuple[TypeGroup, ...] = (
    TypeGroup("Galaxy", 1, ("G",)),
    TypeGroup("Galaxy Group", 2, ("GPair", "GTrpl", "GGroup")),
    TypeGroup("Open Cluster", 3, ("OCl",)),
    TypeGroup("Globular Cluster", 4, ("GCl",)),
    # Cl+N lives here because amateurs imaging the "cluster + nebulosity" target
    # are pointing at the nebulosity; the embedded cluster is incidental for
    # narrowband work.
    TypeGroup("Emission Nebula", 5, ("HII", "EmN", "Cl+N")),
    TypeGroup("Reflection Nebula", 6, ("RfN",)),
    TypeGroup("Planetary Nebula", 7, ("PN",)),
    TypeGroup("Dark Nebula", 8, ("DrkN",)),
    TypeGroup("Supernova Remnant", 9, ("SNR",)),
    TypeGroup("Other Nebula", 10, ("Neb",)),
    TypeGroup("Stellar Association", 11, ("*Ass",)),
    TypeGroup("Star / Multiple", 12, ("*", "**", "Nova")),
    TypeGroup(GROUP_OTHER, 13, ("Other",)),
)


_RAW_TO_GROUP: dict[str, str] = {
    raw: group.name for group in TYPE_GROUPS for raw in group.raw_types
}

_GROUP_TO_RAW: dict[str, tuple[str, ...]] = {group.name: group.raw_types for group in TYPE_GROUPS}


def group_for_raw_type(raw_type: str) -> str:
    """Return the user-facing group name for *raw_type*.

    Unknown codes fall through to the ``Other`` group rather than raising,
    matching the loader's ``obj_type`` fallback behaviour (unknown OpenNGC
    type → stored as ``'Other'`` with the original in ``raw_obj_type``).
    """
    return _RAW_TO_GROUP.get(raw_type, GROUP_OTHER)


def raw_types_for_group(group_name: str) -> tuple[str, ...]:
    """Return the tuple of raw OpenNGC codes that belong to *group_name*.

    Returns an empty tuple for an unknown group name (the API layer treats
    that as "no matches").
    """
    return _GROUP_TO_RAW.get(group_name, ())
