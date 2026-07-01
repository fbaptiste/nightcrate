/**
 * Target Planner UI state — in-memory zustand store. Persistence lives
 * on the backend in the `settings` KV table (planner_* fields), bridged
 * by `lib/usePlannerSettingsSync.ts`.
 */
import { create } from "zustand";
import type { SortEntry } from "@/lib/plannerSortFields";
import type { FilterLine } from "@/api/planner";

export type PlannerTab = "tonight" | "anytime" | "wishlist";

interface PlannerState {
  selectedLocationId: number | null;
  selectedHorizonId: number | null;
  selectedRigId: number | null;
  sortBy: SortEntry[];
  filterIntent: FilterLine[];
  activeTab: PlannerTab;
  searchQuery: string;
  // ISO YYYY-MM-DD; null = tonight. Ephemeral (like searchQuery) — deliberately
  // NOT persisted via usePlannerSettingsSync; it carries "now" meaning, so it
  // resets to tonight each session.
  selectedDate: string | null;
  typeFilter: string[];
  catalogFilter: string[];
  constellationFilter: string[];
  detailId: number | null;
  minHours: number | null;
  maxMag: number | null;
  minSize: number | null;
  coverageRange: [number, number] | null;
  calendarLocationId: number | null;
  calendarHorizonId: number | null;
  calendarRigId: number | null;
  setSelectedLocationId: (id: number | null) => void;
  setSelectedHorizonId: (id: number | null) => void;
  setSelectedRigId: (id: number | null) => void;
  setSortBy: (sort: SortEntry[]) => void;
  setFilterIntent: (intent: FilterLine[]) => void;
  setActiveTab: (tab: PlannerTab) => void;
  setSearchQuery: (q: string) => void;
  setSelectedDate: (d: string | null) => void;
  setTypeFilter: (f: string[]) => void;
  setCatalogFilter: (f: string[]) => void;
  setConstellationFilter: (f: string[]) => void;
  setDetailId: (id: number | null) => void;
  setMinHours: (v: number | null) => void;
  setMaxMag: (v: number | null) => void;
  setMinSize: (v: number | null) => void;
  setCoverageRange: (v: [number, number] | null) => void;
  setCalendarLocationId: (id: number | null) => void;
  setCalendarHorizonId: (id: number | null) => void;
  setCalendarRigId: (id: number | null) => void;
}

export const DEFAULT_SORT: SortEntry[] = [{ field: "primary_designation", dir: "asc" }];

export const usePlannerStore = create<PlannerState>()((set) => ({
  selectedLocationId: null,
  selectedHorizonId: null,
  selectedRigId: null,
  sortBy: DEFAULT_SORT,
  filterIntent: [],
  activeTab: "tonight" as PlannerTab,
  searchQuery: "",
  selectedDate: null,
  typeFilter: [],
  catalogFilter: [],
  constellationFilter: [],
  detailId: null,
  minHours: null,
  maxMag: null,
  minSize: null,
  coverageRange: null,
  calendarLocationId: null,
  calendarHorizonId: null,
  calendarRigId: null,
  setSelectedLocationId: (id) => set({ selectedLocationId: id }),
  setSelectedHorizonId: (id) => set({ selectedHorizonId: id }),
  setSelectedRigId: (id) => set({ selectedRigId: id }),
  setSortBy: (sort) => set({ sortBy: sort }),
  setFilterIntent: (intent) => set({ filterIntent: intent }),
  setActiveTab: (tab) => set({ activeTab: tab }),
  setSearchQuery: (q) => set({ searchQuery: q }),
  setSelectedDate: (d) => set({ selectedDate: d }),
  setTypeFilter: (f) => set({ typeFilter: f }),
  setCatalogFilter: (f) => set({ catalogFilter: f }),
  setConstellationFilter: (f) => set({ constellationFilter: f }),
  setDetailId: (id) => set({ detailId: id }),
  setMinHours: (v) => set({ minHours: v }),
  setMaxMag: (v) => set({ maxMag: v }),
  setMinSize: (v) => set({ minSize: v }),
  setCoverageRange: (v) => set({ coverageRange: v }),
  setCalendarLocationId: (id) => set({ calendarLocationId: id, calendarHorizonId: null }),
  setCalendarHorizonId: (id) => set({ calendarHorizonId: id }),
  setCalendarRigId: (id) => set({ calendarRigId: id }),
}));
