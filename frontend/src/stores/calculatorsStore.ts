import { create } from "zustand";

/** Identifiers used by ClocksCalc for the individual clock cards. Any new
 *  clock must be added here AND rendered by ClocksCalc; a persisted order
 *  containing an unknown id is silently filtered at load time. Persistence
 *  itself lives in the SQLite `settings` table (`calculators_clock_order`);
 *  this module only owns session-only state. */
export const CLOCK_IDS = [
  "local",
  "utc",
  "lst",
  "display-tz",
  "location-tz",
  "jd",
  "mjd",
] as const;

export type ClockId = (typeof CLOCK_IDS)[number];

export const DEFAULT_CLOCK_ORDER: ClockId[] = [...CLOCK_IDS];

interface CalculatorsState {
  /** Selected location on the Calculators page. Session-only — never written
   *  to disk; re-initialised to `null` on reload. */
  selectedLocationId: number | null;
  setSelectedLocationId: (id: number | null) => void;
}

export const useCalculatorsStore = create<CalculatorsState>((set) => ({
  selectedLocationId: null,
  setSelectedLocationId: (id) => set({ selectedLocationId: id }),
}));
