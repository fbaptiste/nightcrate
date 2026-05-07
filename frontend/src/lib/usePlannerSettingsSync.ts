/**
 * Bridges the in-memory `usePlannerStore` (zustand) with the database-
 * backed `useSettingsStore`:
 *
 * 1. Hydrates the planner store from settings ONCE the first time
 *    settings becomes non-null (or from legacy localStorage if present).
 * 2. After hydration, pushes any planner-store change back to settings
 *    via `useSettingsStore.update(...)`.
 *
 * Search query stays out of the sync — it's intentionally ephemeral.
 */
import { useEffect, useRef } from "react";
import { useSettingsStore } from "@/stores/settingsStore";
import { usePlannerStore, DEFAULT_SORT } from "@/stores/plannerStore";
import type { Settings } from "@/api/settings";

const LEGACY_KEY = "nightcrate-planner";
const LEGACY_MIGRATED_FLAG = "nightcrate-planner.migrated";

/**
 * One-time migration of pre-existing zustand-localStorage state into the
 * settings backend. Idempotent via `LEGACY_MIGRATED_FLAG`. Returns the
 * legacy state as a Partial<Settings>-shaped patch (or null if nothing to
 * migrate), and clears localStorage on its way out.
 */
function consumeLegacyLocalStorage(): Partial<Settings> | null {
  let raw: string | null = null;
  try {
    if (window.localStorage.getItem(LEGACY_MIGRATED_FLAG)) return null;
    raw = window.localStorage.getItem(LEGACY_KEY);
  } catch {
    return null;
  }
  let patch: Partial<Settings> | null = null;
  if (raw) {
    try {
      const parsed = JSON.parse(raw);
      const state = parsed?.state ?? null;
      if (state && typeof state === "object") {
        patch = {};
        if (state.selectedLocationId != null) patch.planner_selected_location_id = state.selectedLocationId;
        if (state.selectedHorizonId != null) patch.planner_selected_horizon_id = state.selectedHorizonId;
        if (state.selectedRigId != null) patch.planner_selected_rig_id = state.selectedRigId;
        if (Array.isArray(state.sortBy) && state.sortBy.length > 0) patch.planner_sort_by = state.sortBy;
        if (Array.isArray(state.filterIntent) && state.filterIntent.length > 0) {
          patch.planner_filter_intent = state.filterIntent;
        }
      }
    } catch {
      // Corrupted localStorage — ignore.
    }
  }
  try {
    window.localStorage.removeItem(LEGACY_KEY);
    window.localStorage.setItem(LEGACY_MIGRATED_FLAG, "1");
  } catch {
    // ignore
  }
  return patch && Object.keys(patch).length > 0 ? patch : null;
}

export function usePlannerSettingsSync(): void {
  const settings = useSettingsStore((s) => s.settings);
  const updateSettings = useSettingsStore((s) => s.update);
  const hydratedRef = useRef(false);
  // Latest payload PUT to the backend, JSON-stringified. Used to skip
  // redundant saves — the post-hydration render is the prime offender.
  const lastPushedRef = useRef<string | null>(null);
  // rAF handle for the debounced save. A single frame coalesces multi-
  // setter actions (e.g. Clear filters → 3 sequential setters) into one PUT.
  const pendingSaveRef = useRef<number | null>(null);

  // Hydrate once on first arrival of settings from the backend.
  useEffect(() => {
    if (!settings || hydratedRef.current) return;

    // If localStorage has legacy state and the corresponding backend
    // fields are still default, push the legacy values to the backend
    // first so the user's pre-upgrade selections aren't lost.
    const legacy = consumeLegacyLocalStorage();
    const merged: Settings = settings;
    const overlay: Partial<Settings> = {};
    if (legacy) {
      if (legacy.planner_selected_location_id != null && merged.planner_selected_location_id == null) {
        overlay.planner_selected_location_id = legacy.planner_selected_location_id;
      }
      if (legacy.planner_selected_horizon_id != null && merged.planner_selected_horizon_id == null) {
        overlay.planner_selected_horizon_id = legacy.planner_selected_horizon_id;
      }
      if (legacy.planner_selected_rig_id != null && merged.planner_selected_rig_id == null) {
        overlay.planner_selected_rig_id = legacy.planner_selected_rig_id;
      }
      if (
        legacy.planner_sort_by &&
        JSON.stringify(merged.planner_sort_by) === JSON.stringify(DEFAULT_SORT)
      ) {
        overlay.planner_sort_by = legacy.planner_sort_by;
      }
      if (
        legacy.planner_filter_intent &&
        legacy.planner_filter_intent.length > 0 &&
        (!merged.planner_filter_intent || merged.planner_filter_intent.length === 0)
      ) {
        overlay.planner_filter_intent = legacy.planner_filter_intent;
      }
      if (Object.keys(overlay).length > 0) void updateSettings(overlay);
    }

    const sortByFromSettings =
      overlay.planner_sort_by ?? merged.planner_sort_by;
    const sortBy = sortByFromSettings && sortByFromSettings.length > 0 ? sortByFromSettings : DEFAULT_SORT;
    const hydrated = {
      selectedLocationId: overlay.planner_selected_location_id ?? merged.planner_selected_location_id,
      selectedHorizonId: overlay.planner_selected_horizon_id ?? merged.planner_selected_horizon_id,
      selectedRigId: overlay.planner_selected_rig_id ?? merged.planner_selected_rig_id,
      activeTab: merged.planner_active_tab,
      sortBy,
      filterIntent: overlay.planner_filter_intent ?? merged.planner_filter_intent,
      typeFilter: merged.planner_type_filter,
      catalogFilter: merged.planner_catalog_filter,
      constellationFilter: merged.planner_constellation_filter,
      detailId: merged.planner_detail_id,
      minHours: merged.planner_min_hours,
      maxMag: merged.planner_max_mag,
      minSize: merged.planner_min_size,
      coverageRange: merged.planner_coverage_range,
      calendarLocationId: merged.planner_calendar_location_id,
      calendarHorizonId: merged.planner_calendar_horizon_id,
      calendarRigId: merged.planner_calendar_rig_id,
    };
    usePlannerStore.setState(hydrated);
    // Seed lastPushedRef with the hydrated payload so the post-hydration
    // save effect doesn't fire a no-op PUT echoing the values that just
    // arrived from the server.
    lastPushedRef.current = JSON.stringify(buildPayload(hydrated));
    hydratedRef.current = true;
  }, [settings, updateSettings]);

  // Push planner-store changes back to settings whenever any tracked
  // field changes — but only after initial hydration, so the very first
  // mount doesn't write the in-memory zustand defaults over the user's
  // saved server state. Each field is selected individually so Zustand's
  // referential-equality check skips renders when the field is unchanged.
  const selectedLocationId = usePlannerStore((s) => s.selectedLocationId);
  const selectedHorizonId = usePlannerStore((s) => s.selectedHorizonId);
  const selectedRigId = usePlannerStore((s) => s.selectedRigId);
  const activeTab = usePlannerStore((s) => s.activeTab);
  const sortBy = usePlannerStore((s) => s.sortBy);
  const filterIntent = usePlannerStore((s) => s.filterIntent);
  const typeFilter = usePlannerStore((s) => s.typeFilter);
  const catalogFilter = usePlannerStore((s) => s.catalogFilter);
  const constellationFilter = usePlannerStore((s) => s.constellationFilter);
  const detailId = usePlannerStore((s) => s.detailId);
  const minHours = usePlannerStore((s) => s.minHours);
  const maxMag = usePlannerStore((s) => s.maxMag);
  const minSize = usePlannerStore((s) => s.minSize);
  const coverageRange = usePlannerStore((s) => s.coverageRange);
  const calendarLocationId = usePlannerStore((s) => s.calendarLocationId);
  const calendarHorizonId = usePlannerStore((s) => s.calendarHorizonId);
  const calendarRigId = usePlannerStore((s) => s.calendarRigId);

  // rAF-coalesced save: a single tick of multiple setters (e.g. Clear
  // filters → 3 sequential setState calls) collapses to one PUT. Skips
  // saves where the payload matches the last one we sent — guards against
  // the post-hydration render echoing server values back, and against
  // back-to-back identical pushes.
  useEffect(() => {
    if (!hydratedRef.current) return;
    if (pendingSaveRef.current != null) return;
    pendingSaveRef.current = requestAnimationFrame(() => {
      pendingSaveRef.current = null;
      const payload = buildPayload({
        selectedLocationId,
        selectedHorizonId,
        selectedRigId,
        activeTab,
        sortBy,
        filterIntent,
        typeFilter,
        catalogFilter,
        constellationFilter,
        detailId,
        minHours,
        maxMag,
        minSize,
        coverageRange,
        calendarLocationId,
        calendarHorizonId,
        calendarRigId,
      });
      const json = JSON.stringify(payload);
      if (json === lastPushedRef.current) return;
      lastPushedRef.current = json;
      void updateSettings(payload);
    });
    return () => {
      if (pendingSaveRef.current != null) {
        cancelAnimationFrame(pendingSaveRef.current);
        pendingSaveRef.current = null;
      }
    };
  }, [
    selectedLocationId,
    selectedHorizonId,
    selectedRigId,
    activeTab,
    sortBy,
    filterIntent,
    typeFilter,
    catalogFilter,
    constellationFilter,
    detailId,
    minHours,
    maxMag,
    minSize,
    coverageRange,
    calendarLocationId,
    calendarHorizonId,
    calendarRigId,
    updateSettings,
  ]);
}

interface PlannerSnapshot {
  selectedLocationId: number | null;
  selectedHorizonId: number | null;
  selectedRigId: number | null;
  activeTab: Settings["planner_active_tab"];
  sortBy: Settings["planner_sort_by"];
  filterIntent: Settings["planner_filter_intent"];
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
}

function buildPayload(s: PlannerSnapshot): Partial<Settings> {
  return {
    planner_selected_location_id: s.selectedLocationId,
    planner_selected_horizon_id: s.selectedHorizonId,
    planner_selected_rig_id: s.selectedRigId,
    planner_active_tab: s.activeTab,
    planner_sort_by: s.sortBy,
    planner_filter_intent: s.filterIntent,
    planner_type_filter: s.typeFilter,
    planner_catalog_filter: s.catalogFilter,
    planner_constellation_filter: s.constellationFilter,
    planner_detail_id: s.detailId,
    planner_min_hours: s.minHours,
    planner_max_mag: s.maxMag,
    planner_min_size: s.minSize,
    planner_coverage_range: s.coverageRange,
    planner_calendar_location_id: s.calendarLocationId,
    planner_calendar_horizon_id: s.calendarHorizonId,
    planner_calendar_rig_id: s.calendarRigId,
  };
}
