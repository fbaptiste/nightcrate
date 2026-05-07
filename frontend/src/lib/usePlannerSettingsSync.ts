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

  // Hydrate once on first arrival of settings from the backend.
  useEffect(() => {
    if (!settings || hydratedRef.current) return;

    // If localStorage has legacy state and the corresponding backend
    // fields are still default, push the legacy values to the backend
    // first so the user's pre-upgrade selections aren't lost.
    const legacy = consumeLegacyLocalStorage();
    if (legacy) {
      // Only forward fields the backend hasn't already saved (default).
      const filtered: Partial<Settings> = {};
      if (legacy.planner_selected_location_id != null && settings.planner_selected_location_id == null) {
        filtered.planner_selected_location_id = legacy.planner_selected_location_id;
      }
      if (legacy.planner_selected_horizon_id != null && settings.planner_selected_horizon_id == null) {
        filtered.planner_selected_horizon_id = legacy.planner_selected_horizon_id;
      }
      if (legacy.planner_selected_rig_id != null && settings.planner_selected_rig_id == null) {
        filtered.planner_selected_rig_id = legacy.planner_selected_rig_id;
      }
      if (
        legacy.planner_sort_by &&
        JSON.stringify(settings.planner_sort_by) === JSON.stringify(DEFAULT_SORT)
      ) {
        filtered.planner_sort_by = legacy.planner_sort_by;
      }
      if (
        legacy.planner_filter_intent &&
        legacy.planner_filter_intent.length > 0 &&
        (!settings.planner_filter_intent || settings.planner_filter_intent.length === 0)
      ) {
        filtered.planner_filter_intent = legacy.planner_filter_intent;
      }
      if (Object.keys(filtered).length > 0) {
        void updateSettings(filtered);
        // Apply the legacy values to the live settings object for the
        // hydration below so the user sees them immediately.
        Object.assign(settings, filtered);
      }
    }

    usePlannerStore.setState({
      selectedLocationId: settings.planner_selected_location_id,
      selectedHorizonId: settings.planner_selected_horizon_id,
      selectedRigId: settings.planner_selected_rig_id,
      activeTab: settings.planner_active_tab,
      sortBy:
        settings.planner_sort_by && settings.planner_sort_by.length > 0
          ? settings.planner_sort_by
          : DEFAULT_SORT,
      filterIntent: settings.planner_filter_intent,
      typeFilter: settings.planner_type_filter,
      catalogFilter: settings.planner_catalog_filter,
      constellationFilter: settings.planner_constellation_filter,
      detailId: settings.planner_detail_id,
      minHours: settings.planner_min_hours,
      maxMag: settings.planner_max_mag,
      minSize: settings.planner_min_size,
      coverageRange: settings.planner_coverage_range,
      calendarLocationId: settings.planner_calendar_location_id,
      calendarHorizonId: settings.planner_calendar_horizon_id,
      calendarRigId: settings.planner_calendar_rig_id,
    });
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

  useEffect(() => {
    if (!hydratedRef.current) return;
    void updateSettings({
      planner_selected_location_id: selectedLocationId,
      planner_selected_horizon_id: selectedHorizonId,
      planner_selected_rig_id: selectedRigId,
      planner_active_tab: activeTab,
      planner_sort_by: sortBy,
      planner_filter_intent: filterIntent,
      planner_type_filter: typeFilter,
      planner_catalog_filter: catalogFilter,
      planner_constellation_filter: constellationFilter,
      planner_detail_id: detailId,
      planner_min_hours: minHours,
      planner_max_mag: maxMag,
      planner_min_size: minSize,
      planner_coverage_range: coverageRange,
      planner_calendar_location_id: calendarLocationId,
      planner_calendar_horizon_id: calendarHorizonId,
      planner_calendar_rig_id: calendarRigId,
    });
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
