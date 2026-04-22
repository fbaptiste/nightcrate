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
  tonightOnly?: boolean;
  rigOnly?: boolean;
}

export const PLANNER_SORT_FIELDS: PlannerSortField[] = [
  { field: "primary_designation", label: "Designation" },
  { field: "common_name", label: "Common name" },
  { field: "constellation", label: "Constellation" },
  { field: "obj_type", label: "Type" },
  { field: "mag_v", label: "Mag V" },
  { field: "maj_axis_arcmin", label: "Size" },
  { field: "distance_pc", label: "Distance" },
  { field: "hours_visible", label: "Hours visible", tonightOnly: true },
  { field: "max_altitude_deg", label: "Max altitude", tonightOnly: true },
  {
    field: "altitude_at_transit_deg",
    label: "Meridian altitude",
    tonightOnly: true,
  },
  { field: "transit_time_utc", label: "Meridian time", tonightOnly: true },
  {
    field: "min_moon_separation_deg",
    label: "Moon separation",
    tonightOnly: true,
  },
  { field: "coverage_pct", label: "Coverage %", rigOnly: true },
  { field: "now_status", label: "Now status", tonightOnly: true },
];

const BY_FIELD: Record<string, PlannerSortField> = Object.fromEntries(
  PLANNER_SORT_FIELDS.map((f) => [f.field, f]),
);

export function sortFieldLabel(field: string): string {
  return BY_FIELD[field]?.label ?? field;
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
