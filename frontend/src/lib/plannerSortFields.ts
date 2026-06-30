/**
 * Sort-field catalog for the Target Planner's multi-sort panel.
 *
 * Mirrors ``PLANNER_SORT_FIELDS`` in ``backend/api/planner.py`` — keep
 * the two lists in lockstep when adding or removing a field. Field
 * names match the ``PlannerTargetItem`` attribute names so the
 * backend's ``getattr(item, field)`` fetches the right value.
 *
 * ``tonightOnly`` hides the pill in Anytime mode (where the backend
 * returns ``null`` for visibility-derived fields). ``rigOnly`` hides
 * Coverage % until the user picks a rig. The Sort panel filters the
 * Available pill set by these flags; entries that are in the active
 * sort but no longer applicable get filtered out at query-string
 * serialization so toggling back restores them.
 */
export type SortDir = "asc" | "desc";

export interface SortEntry {
  field: string;
  dir: SortDir;
}

export interface PlannerSortField {
  field: string;
  label: string;
  /** One-line explanation of what the field means, shown as a tooltip
   *  on every pill (Available, active Sort-by, collapsed summary). */
  description: string;
  tonightOnly?: boolean;
  rigOnly?: boolean;
}

export const PLANNER_SORT_FIELDS: PlannerSortField[] = [
  {
    field: "primary_designation",
    label: "Designation",
    description: "Primary catalog designation (e.g. M 31, NGC 7000).",
  },
  {
    field: "common_name",
    label: "Common name",
    description: "Popular name, where the object has one (e.g. Andromeda Galaxy).",
  },
  {
    field: "constellation",
    label: "Constellation",
    description: "Constellation the target lies in.",
  },
  {
    field: "obj_type",
    label: "Type",
    description: "Object type — galaxy, nebula, open or globular cluster, and so on.",
  },
  {
    field: "mag_v",
    label: "Mag V",
    description: "Visual magnitude; lower numbers are brighter.",
  },
  {
    field: "maj_axis_arcmin",
    label: "Size",
    description: "Apparent size along the major axis, in arcminutes.",
  },
  {
    field: "distance_pc",
    label: "Distance",
    description: "Distance from Earth, in parsecs.",
  },
  {
    field: "hours_visible",
    label: "Hours visible",
    description:
      "Hours the target stays above your horizon during tonight's astro-dark window.",
    tonightOnly: true,
  },
  {
    field: "max_altitude_deg",
    label: "Max altitude",
    description: "Highest altitude the target reaches tonight.",
    tonightOnly: true,
  },
  {
    field: "altitude_at_transit_deg",
    label: "Meridian altitude",
    description:
      "Altitude as the target crosses the meridian — its highest point of the night.",
    tonightOnly: true,
  },
  {
    field: "transit_time_utc",
    label: "Meridian time",
    description: "Clock time the target crosses the meridian (transits) tonight.",
    tonightOnly: true,
  },
  {
    field: "min_moon_separation_deg",
    label: "Moon separation",
    description:
      "Closest the Moon comes to the target while it's visible — larger is better.",
    tonightOnly: true,
  },
  {
    field: "coverage_pct",
    label: "Coverage %",
    description:
      "How much of your selected rig's field of view the target fills.",
    rigOnly: true,
  },
  {
    field: "now_status",
    label: "Now status",
    description: "Whether the target is up, rising, or already set right now.",
    tonightOnly: true,
  },
  // v0.21.0 — 0-100 quality score; gated targets (null score) sort
  // last regardless of direction per the planner's nulls-last policy.
  {
    field: "score_pct",
    label: "Score",
    description:
      "Overall 0–100 imaging-quality score blending altitude, Moon, and meridian timing.",
    tonightOnly: true,
  },
];

const BY_FIELD: Record<string, PlannerSortField> = Object.fromEntries(
  PLANNER_SORT_FIELDS.map((f) => [f.field, f]),
);

export function sortFieldLabel(field: string): string {
  return BY_FIELD[field]?.label ?? field;
}

/** One-line tooltip description for a sort field, or "" for an unknown
 *  field (so callers can pass it straight to a MUI ``Tooltip`` title —
 *  an empty title renders no tooltip). */
export function sortFieldDescription(field: string): string {
  return BY_FIELD[field]?.description ?? "";
}

/** ``true`` when the field is allowed for the current mode + rig
 *  state. Used both to gate the Available pill set AND to drop
 *  inapplicable entries from the serialized query string. */
export function sortFieldAvailable(
  field: string,
  restrictTonight: boolean,
  rigSelected: boolean,
): boolean {
  const meta = BY_FIELD[field];
  if (!meta) return false;
  if (meta.tonightOnly && !restrictTonight) return false;
  if (meta.rigOnly && !rigSelected) return false;
  return true;
}

/** Serialize a sort-entry list as the ``sort`` query param, filtering
 *  out entries that aren't applicable under the current mode / rig. */
export function serializeSort(
  entries: SortEntry[],
  restrictTonight: boolean,
  rigSelected: boolean,
): string | null {
  const applicable = entries.filter((e) =>
    sortFieldAvailable(e.field, restrictTonight, rigSelected),
  );
  if (applicable.length === 0) return null;
  return applicable.map((e) => `${e.field}:${e.dir}`).join(",");
}
