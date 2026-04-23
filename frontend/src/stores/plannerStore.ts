import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import type { SortEntry } from "@/lib/plannerSortFields";
import type { FilterLine } from "@/api/planner";

/** Target Planner selector state.
 *
 *  Persisted in localStorage so refresh keeps the user's last rig +
 *  location + horizon + filter-intent choice, plus their multi-sort
 *  preference. The page validates stored ids against the current
 *  locations / rigs / horizons queries on mount; ids that no longer
 *  resolve fall back to the default (default location / default
 *  horizon / no rig). Sort entries whose field no longer exists are
 *  filtered at serialization time rather than pruned from state —
 *  keeps them alive across Tonight/Anytime toggles. */
interface PlannerState {
  selectedLocationId: number | null;
  selectedHorizonId: number | null;
  selectedRigId: number | null;
  sortBy: SortEntry[];
  /** Filter intent multi-select — any subset of Ha/SII/OIII/L/R/G/B.
   *  Drives the scoring moon dimension (v0.21.0). Persists across
   *  sessions per Q4: astrophotographers tend to have a stable
   *  imaging habit (SHO vs LRGB), so reselecting every launch is noise. */
  filterIntent: FilterLine[];
  setSelectedLocationId: (id: number | null) => void;
  setSelectedHorizonId: (id: number | null) => void;
  setSelectedRigId: (id: number | null) => void;
  setSortBy: (sort: SortEntry[]) => void;
  setFilterIntent: (intent: FilterLine[]) => void;
}

export const usePlannerStore = create<PlannerState>()(
  persist(
    (set) => ({
      selectedLocationId: null,
      selectedHorizonId: null,
      selectedRigId: null,
      // Tonight mode defaults to score:desc on the backend when
      // sortBy is empty; in-memory default below covers Anytime.
      sortBy: [{ field: "primary_designation", dir: "asc" }],
      filterIntent: [],
      setSelectedLocationId: (id) => set({ selectedLocationId: id }),
      setSelectedHorizonId: (id) => set({ selectedHorizonId: id }),
      setSelectedRigId: (id) => set({ selectedRigId: id }),
      setSortBy: (sort) => set({ sortBy: sort }),
      setFilterIntent: (intent) => set({ filterIntent: intent }),
    }),
    {
      name: "nightcrate-planner",
      storage: createJSONStorage(() => localStorage),
      // Bumped when the persisted shape changed incompatibly. v4 adds
      // ``filterIntent``; older state has every other field so we
      // carry those forward and default filterIntent to []. Without
      // an explicit migrate, Zustand discards the entire v3 payload
      // on mismatch — which would wipe the user's saved
      // location/horizon/rig/sortBy for no reason.
      version: 4,
      migrate: (persisted, fromVersion) => {
        const prev = (persisted ?? {}) as Partial<PlannerState>;
        if (fromVersion < 4) {
          return { ...prev, filterIntent: [] };
        }
        return prev;
      },
    },
  ),
);
