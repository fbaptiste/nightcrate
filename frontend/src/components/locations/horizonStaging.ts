/**
 * Staged horizon state — restores the v0.13.0 save-button-owns-everything
 * flow that v0.19.0 accidentally dropped when it rewrote the horizon
 * section for immediate persistence.
 *
 * The Location editor dialog owns a ``StagedHorizon[]`` array that
 * represents the user's desired final state. Horizon edits mutate this
 * array only — nothing hits the server until the outer Save button is
 * clicked. Cancel discards everything. This keeps the dirty-state
 * model consistent with how the location's own fields work.
 *
 *   state=unchanged → exists on server and matches it
 *   state=new       → added locally; has a temp negative id
 *   state=modified  → exists on server but differs in ≥1 field
 *   state=deleted   → tombstone; hidden in UI; becomes a DELETE at Save
 */
import type { Horizon, HorizonPoint } from "@/api/horizons";
import type { LocationCreateHorizonSeed } from "@/api/locations";

export type HorizonLifecycle = "unchanged" | "new" | "modified" | "deleted";

export interface StagedHorizon {
  /** Negative for locally-added rows; positive when it exists on the
   *  server. Stable for the life of the dialog session. */
  id: number;
  /** Original server row (null for ``state=new``). Used by
   *  ``isModified`` to diff persisted fields. */
  serverRow: Horizon | null;
  name: string;
  type: "custom" | "artificial";
  flat_altitude_deg: number | null;
  points: HorizonPoint[];
  is_default: boolean;
  state: HorizonLifecycle;
}

// Negative temp ids for newly-added-but-not-yet-saved rows. Allocated
// by ``nextTempId`` to avoid collisions across the dialog session.
const _TEMP_ID_CEILING = -1;

/** Return the next negative temp id given the current staged array. */
export function nextTempId(staged: StagedHorizon[]): number {
  const minId = staged.reduce(
    (acc, h) => (h.id < acc ? h.id : acc),
    _TEMP_ID_CEILING + 1,
  );
  return Math.min(minId - 1, _TEMP_ID_CEILING);
}

/** Build an unchanged staged entry from a server row (dialog open in edit mode). */
export function fromServerRow(server: Horizon): StagedHorizon {
  return {
    id: server.id,
    serverRow: server,
    name: server.name,
    type: server.type,
    flat_altitude_deg: server.flat_altitude_deg ?? null,
    points: server.points ?? [],
    is_default: server.is_default,
    state: "unchanged",
  };
}

interface NewArtificialParams {
  staged: StagedHorizon[];
  name: string;
  flat_altitude_deg: number;
  is_default?: boolean;
}

/** Create a new staged artificial horizon with the next temp id. */
export function newArtificial({
  staged,
  name,
  flat_altitude_deg,
  is_default = false,
}: NewArtificialParams): StagedHorizon {
  return {
    id: nextTempId(staged),
    serverRow: null,
    name,
    type: "artificial",
    flat_altitude_deg,
    points: [],
    is_default,
    state: "new",
  };
}

interface NewCustomParams {
  staged: StagedHorizon[];
  name: string;
  points: HorizonPoint[];
  is_default?: boolean;
  source?: "drawn" | "imported" | null;
}

export function newCustom({
  staged,
  name,
  points,
  is_default = false,
}: NewCustomParams): StagedHorizon {
  return {
    id: nextTempId(staged),
    serverRow: null,
    name,
    type: "custom",
    flat_altitude_deg: null,
    points,
    is_default,
    state: "new",
  };
}

/** Return ``staged`` less deleted entries — the UI-visible list. */
export function visibleHorizons(staged: StagedHorizon[]): StagedHorizon[] {
  return staged.filter((h) => h.state !== "deleted");
}

/** Return the visible entry currently marked as default, or null. */
export function defaultHorizon(staged: StagedHorizon[]): StagedHorizon | null {
  return visibleHorizons(staged).find((h) => h.is_default) ?? null;
}

/** Return the visible custom horizon (at most one), or null. */
export function customHorizon(staged: StagedHorizon[]): StagedHorizon | null {
  return visibleHorizons(staged).find((h) => h.type === "custom") ?? null;
}

/** Seed the "new location" dialog with a single 0° flat default — mirrors
 *  the server's legacy auto-seed so the user starts with a sensible
 *  default they can delete or modify before committing. */
export function seedNewLocationDefault(): StagedHorizon[] {
  return [
    {
      id: _TEMP_ID_CEILING,
      serverRow: null,
      name: "0° flat",
      type: "artificial",
      flat_altitude_deg: 0,
      points: [],
      is_default: true,
      state: "new",
    },
  ];
}

// ── Diff + dirty check ──────────────────────────────────────────────────────

function pointsDiffer(a: HorizonPoint[], b: HorizonPoint[]): boolean {
  if (a.length !== b.length) return true;
  for (let i = 0; i < a.length; i++) {
    if (a[i].azimuth_deg !== b[i].azimuth_deg) return true;
    if (a[i].altitude_deg !== b[i].altitude_deg) return true;
  }
  return false;
}

/** True when the staged entry's persisted fields differ from its server
 *  counterpart. Only meaningful for rows with ``serverRow !== null``. */
export function differsFromServer(h: StagedHorizon): boolean {
  const s = h.serverRow;
  if (s === null) return false;
  if (h.name !== s.name) return true;
  if (h.flat_altitude_deg !== (s.flat_altitude_deg ?? null)) return true;
  if (h.is_default !== s.is_default) return true;
  if (h.type === "custom" && pointsDiffer(h.points, s.points ?? [])) return true;
  return false;
}

/** True when any staged entry has pending changes (new/modified/deleted)
 *  relative to the server snapshot. */
export function hasDirtyHorizons(staged: StagedHorizon[]): boolean {
  return staged.some((h) => h.state === "new" || h.state === "modified" || h.state === "deleted");
}

/** Update a staged row's lifecycle tag after a field edit — walks the
 *  diff against its ``serverRow`` and reassigns ``state`` to
 *  ``unchanged`` vs ``modified``. No-op for ``new`` and ``deleted`` rows. */
export function retagState(h: StagedHorizon): StagedHorizon {
  if (h.state === "new" || h.state === "deleted") return h;
  return { ...h, state: differsFromServer(h) ? "modified" : "unchanged" };
}

// ── Default-promotion helpers ──────────────────────────────────────────────

/** Promote ``targetId`` to the sole default; demote every other visible
 *  horizon. Deleted rows are left untouched (their flag doesn't matter
 *  — they'll be DELETEd at Save). Re-tags modified / unchanged status. */
export function promoteDefault(staged: StagedHorizon[], targetId: number): StagedHorizon[] {
  return staged.map((h) => {
    if (h.state === "deleted") return h;
    const should = h.id === targetId;
    if (h.is_default === should) return h;
    const updated = { ...h, is_default: should };
    return retagState(updated);
  });
}

/** Mark a horizon as staged-for-delete. For rows with ``state=new``
 *  (never committed), we drop the entry entirely since there's nothing
 *  to undo. For server-backed rows, we flip to ``deleted`` so the
 *  Save dispatcher can issue a DELETE. The deletion leaves the row
 *  intact in the array so the user's Cancel action can restore it. */
export function markDeleted(
  staged: StagedHorizon[],
  targetId: number,
): StagedHorizon[] {
  const target = staged.find((h) => h.id === targetId);
  if (target === undefined) return staged;
  if (target.state === "new") {
    return staged.filter((h) => h.id !== targetId);
  }
  return staged.map((h) =>
    h.id === targetId ? { ...h, state: "deleted" as HorizonLifecycle } : h,
  );
}

// ── Serialization ──────────────────────────────────────────────────────────

/** Convert staged horizons into seeds for ``POST /api/locations`` atomic
 *  create. Drops deleted entries (they were never saved so nothing to
 *  clean up). Caller is expected to have already validated
 *  exactly-one-default and at-most-one-custom invariants. */
export function toCreateSeeds(staged: StagedHorizon[]): LocationCreateHorizonSeed[] {
  return visibleHorizons(staged).map((h) => {
    if (h.type === "artificial") {
      return {
        name: h.name,
        type: "artificial",
        flat_altitude_deg: h.flat_altitude_deg,
        is_default: h.is_default,
        notes: null,
      };
    }
    return {
      name: h.name,
      type: "custom",
      points: h.points,
      source: "drawn",
      is_default: h.is_default,
      notes: null,
    };
  });
}

// ── Save-dispatch plan for the EXISTING-location case ──────────────────────

/** Ordered list of server operations to apply when saving an existing
 *  location. Order is important because the server enforces
 *  exactly-one-default + at-most-one-custom invariants:
 *
 *    1. create-new   → POST (with is_default=false for safety; default
 *                       flip comes later)
 *    2. update       → PATCH modifiable fields (name, altitude, points)
 *    3. promote      → PATCH is_default=true on the target; server auto-
 *                       demotes the previous default in the same op
 *    4. delete       → DELETE (if any remaining row was a default, by
 *                       step 3 we've already moved the default off it)
 */
export interface HorizonSaveOps {
  creates: { tempId: number; seed: LocationCreateHorizonSeed }[];
  updates: {
    horizonId: number;
    patch: {
      name?: string;
      flat_altitude_deg?: number | null;
      points?: HorizonPoint[];
    };
  }[];
  promoteDefaultId: number | null;
  deletes: number[];
}

/** Build the save-dispatch plan for the existing-location case. */
export function planSaveOps(staged: StagedHorizon[]): HorizonSaveOps {
  const creates: HorizonSaveOps["creates"] = [];
  const updates: HorizonSaveOps["updates"] = [];
  const deletes: number[] = [];

  const deletedIds = new Set(staged.filter((h) => h.state === "deleted").map((h) => h.id));
  for (const id of deletedIds) {
    if (id > 0) deletes.push(id); // only server-known rows need a DELETE call
  }

  for (const h of staged) {
    if (h.state === "new") {
      creates.push({
        tempId: h.id,
        seed:
          h.type === "artificial"
            ? {
                name: h.name,
                type: "artificial",
                flat_altitude_deg: h.flat_altitude_deg,
                // NOTE: is_default=false on CREATE. The server's
                // partial unique index would fail if we tried to mark
                // a new row as default while another existing default
                // is still present. Promotion is a separate PATCH
                // step below that atomically demotes the old default.
                is_default: false,
                notes: null,
              }
            : {
                name: h.name,
                type: "custom",
                points: h.points,
                source: "drawn",
                is_default: false,
                notes: null,
              },
      });
    } else if (h.state === "modified") {
      // Only include fields that actually changed vs serverRow. Skip
      // is_default here — it's handled separately via promoteDefaultId.
      const s = h.serverRow!;
      const patch: HorizonSaveOps["updates"][number]["patch"] = {};
      if (h.name !== s.name) patch.name = h.name;
      if (h.flat_altitude_deg !== (s.flat_altitude_deg ?? null)) {
        patch.flat_altitude_deg = h.flat_altitude_deg;
      }
      if (h.type === "custom" && pointsDiffer(h.points, s.points ?? [])) {
        patch.points = h.points;
      }
      if (Object.keys(patch).length > 0) {
        updates.push({ horizonId: h.id, patch });
      }
    }
  }

  // Compute the promote step: if the current staged default differs
  // from the server default, we need to PATCH is_default=true on the
  // target. For new rows, the temp id maps to a real id after the
  // POST resolves — the caller threads that mapping through.
  const stagedDefault = defaultHorizon(staged);
  const serverDefaultId =
    staged.find((h) => h.serverRow?.is_default)?.serverRow?.id ?? null;
  let promoteDefaultId: number | null = null;
  if (stagedDefault && stagedDefault.id !== serverDefaultId) {
    promoteDefaultId = stagedDefault.id; // may be negative (temp); caller resolves
  }

  return { creates, updates, promoteDefaultId, deletes };
}
