import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import type { SortEntry } from "@/lib/plannerSortFields";

/** Target Planner selector state.
 *
 *  Persisted in localStorage so refresh keeps the user's last rig +
 *  location + horizon choice, plus their multi-sort preference. The
 *  page validates stored ids against the current locations / rigs /
 *  horizons queries on mount; ids that no longer resolve fall back to
 *  the default (default location / default horizon / no rig). Sort
 *  entries whose field no longer exists are filtered at serialization
 *  time rather than pruned from state — keeps them alive across
 *  Tonight/Anytime toggles. */
interface PlannerState {
  selectedLocationId: number | null;
  selectedHorizonId: number | null;
  selectedRigId: number | null;
  sortBy: SortEntry[];
  setSelectedLocationId: (id: number | null) => void;
  setSelectedHorizonId: (id: number | null) => void;
  setSelectedRigId: (id: number | null) => void;
  setSortBy: (sort: SortEntry[]) => void;
}

export const usePlannerStore = create<PlannerState>()(
  persist(
    (set) => ({
      selectedLocationId: null,
      selectedHorizonId: null,
      selectedRigId: null,
      // Designation ascending is a safe default that applies in both
      // Tonight and Anytime modes. Users can replace it (or clear it)
      // via the Sort panel; cleared means "use the backend's
      // mode-appropriate default".
      sortBy: [{ field: "primary_designation", dir: "asc" }],
      setSelectedLocationId: (id) => set({ selectedLocationId: id }),
      setSelectedHorizonId: (id) => set({ selectedHorizonId: id }),
      setSelectedRigId: (id) => set({ selectedRigId: id }),
      setSortBy: (sort) => set({ sortBy: sort }),
    }),
    {
      name: "nightcrate-planner",
      storage: createJSONStorage(() => localStorage),
      // Bumped when the persisted shape changed incompatibly. Raising
      // the version throws away any state persisted under a lower
      // version (Zustand's default migrate behaviour). Needed here
      // because ``sortBy`` shipped briefly as ``[]`` in localStorage
      // and the in-memory default alone doesn't override that.
      version: 3,
    },
  ),
);
