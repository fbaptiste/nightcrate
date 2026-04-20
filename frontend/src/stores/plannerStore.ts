import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

/** Target Planner selector state.
 *
 *  Persisted in localStorage so refresh keeps the user's last rig +
 *  location choice. The page validates stored ids against the current
 *  locations/rigs query on mount; ids that no longer resolve fall
 *  back to the default (default location / no rig). */
interface PlannerState {
  selectedLocationId: number | null;
  selectedRigId: number | null;
  setSelectedLocationId: (id: number | null) => void;
  setSelectedRigId: (id: number | null) => void;
}

export const usePlannerStore = create<PlannerState>()(
  persist(
    (set) => ({
      selectedLocationId: null,
      selectedRigId: null,
      setSelectedLocationId: (id) => set({ selectedLocationId: id }),
      setSelectedRigId: (id) => set({ selectedRigId: id }),
    }),
    {
      name: "nightcrate-planner",
      storage: createJSONStorage(() => localStorage),
    },
  ),
);
