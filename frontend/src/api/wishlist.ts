/**
 * Wishlist API client (v0.30.0).
 *
 * Favorites CRUD + plans CRUD for the Target Planner's Wishlist tab.
 */
import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { apiFetch } from "./client";

// ── Types ──────────────────────────────────────────────────────────────────

export interface FavoriteIdsResponse {
  dso_ids: number[];
}

export interface FavoriteDsoSummary {
  dso_id: number;
  primary_designation: string;
  common_name: string | null;
  obj_type: string;
  constellation: string | null;
  ra_deg: number | null;
  dec_deg: number | null;
  mag_v: number | null;
  maj_axis_arcmin: number | null;
}

export interface DateRangeIn {
  start_date: string;
  end_date: string;
}

export interface DateRangeOut {
  id: number;
  start_date: string;
  end_date: string;
}

export interface PlanSummary {
  id: number;
  location_id: number;
  location_name: string;
  horizon_id: number;
  horizon_name: string;
  rig_id: number;
  rig_name: string;
  moon_sep_deg: number;
  moon_filter_enabled: boolean;
  max_illumination_pct: number;
  min_separation_deg: number;
  moon_combine: "and" | "or";
  threshold_hours: number;
  date_ranges: DateRangeOut[];
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface SectionResponse {
  id: number;
  name: string;
  sort_order: number;
}

export interface FavoriteFullItem {
  dso: FavoriteDsoSummary;
  sort_order: number;
  section_id: number | null;
  plan_count: number;
  plans: PlanSummary[];
  created_at: string;
}

export interface FavoritesFullResponse {
  items: FavoriteFullItem[];
  sections: SectionResponse[];
  total: number;
}

export interface PlanResponse {
  id: number;
  dso_id: number;
  primary_designation: string;
  common_name: string | null;
  location_id: number;
  location_name: string;
  horizon_id: number;
  horizon_name: string;
  rig_id: number;
  rig_name: string;
  moon_sep_deg: number;
  moon_filter_enabled: boolean;
  max_illumination_pct: number;
  min_separation_deg: number;
  moon_combine: "and" | "or";
  threshold_hours: number;
  date_ranges: DateRangeOut[];
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface PlanListResponse {
  items: PlanResponse[];
  total: number;
}

export interface CreatePlanParams {
  dso_id: number;
  location_id: number;
  horizon_id: number;
  rig_id: number;
  moon_sep_deg?: number;
  moon_filter_enabled?: boolean;
  max_illumination_pct?: number;
  min_separation_deg?: number;
  moon_combine?: "and" | "or";
  threshold_hours?: number;
  date_ranges?: DateRangeIn[];
  notes?: string | null;
}

export interface UpdatePlanParams {
  location_id?: number;
  horizon_id?: number;
  rig_id?: number;
  moon_sep_deg?: number;
  moon_filter_enabled?: boolean;
  max_illumination_pct?: number;
  min_separation_deg?: number;
  moon_combine?: "and" | "or";
  threshold_hours?: number;
  date_ranges?: DateRangeIn[];
  notes?: string | null;
  clear_notes?: boolean;
}

// ── Fetch functions ────────────────────────────────────────────────────────

const PREFIX = "/planner/wishlist";

async function fetchFavoriteIds(): Promise<FavoriteIdsResponse> {
  return apiFetch<FavoriteIdsResponse>(`${PREFIX}/favorites`);
}

async function fetchFavoritesFull(): Promise<FavoritesFullResponse> {
  return apiFetch<FavoritesFullResponse>(`${PREFIX}/favorites/full`);
}

async function addFavorite(dsoId: number): Promise<FavoriteIdsResponse> {
  return apiFetch<FavoriteIdsResponse>(`${PREFIX}/favorites`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dso_id: dsoId }),
  });
}

async function removeFavorite(dsoId: number): Promise<void> {
  await apiFetch<void>(`${PREFIX}/favorites/${dsoId}`, { method: "DELETE" });
}

export interface ReorderItem {
  dso_id: number;
  section_id: number | null;
  sort_order: number;
}

async function reorderFavorites(items: ReorderItem[]): Promise<FavoriteIdsResponse> {
  return apiFetch<FavoriteIdsResponse>(`${PREFIX}/favorites/reorder`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ items }),
  });
}

export async function createSection(name: string): Promise<SectionResponse> {
  return apiFetch<SectionResponse>(`${PREFIX}/sections`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
}

export async function renameSection(id: number, name: string): Promise<SectionResponse> {
  return apiFetch<SectionResponse>(`${PREFIX}/sections/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
}

export async function deleteSection(id: number): Promise<void> {
  await apiFetch<void>(`${PREFIX}/sections/${id}`, { method: "DELETE" });
}

export async function reorderSections(sectionIds: number[]): Promise<SectionResponse[]> {
  return apiFetch<SectionResponse[]>(`${PREFIX}/sections/reorder`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ section_ids: sectionIds }),
  });
}

export async function moveFavorite(
  dsoId: number,
  sectionId: number | null,
  sortOrder: number = 0,
): Promise<void> {
  await apiFetch<void>(`${PREFIX}/favorites/${dsoId}/move`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ section_id: sectionId, sort_order: sortOrder }),
  });
}

export async function fetchPlans(params?: {
  location_id?: number;
  rig_id?: number;
}): Promise<PlanListResponse> {
  const qs = new URLSearchParams();
  if (params?.location_id != null) qs.set("location_id", String(params.location_id));
  if (params?.rig_id != null) qs.set("rig_id", String(params.rig_id));
  const suffix = qs.toString() ? `?${qs}` : "";
  return apiFetch<PlanListResponse>(`${PREFIX}/plans${suffix}`);
}

export async function createPlan(params: CreatePlanParams): Promise<PlanResponse> {
  return apiFetch<PlanResponse>(`${PREFIX}/plans`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
}

export async function updatePlan(
  planId: number,
  params: UpdatePlanParams,
): Promise<PlanResponse> {
  return apiFetch<PlanResponse>(`${PREFIX}/plans/${planId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
}

export async function deletePlan(planId: number): Promise<void> {
  await apiFetch<void>(`${PREFIX}/plans/${planId}`, { method: "DELETE" });
}

// ── Calendar types ─────────────────────────────────────────────────────────

export interface CalendarTargetRow {
  dso_id: number;
  primary_designation: string;
  common_name: string | null;
  plan_id: number;
  date_ranges: DateRangeOut[];
  notes: string | null;
  monthly_hours: number[];
  section_id: number | null;
  section_name: string | null;
}

export interface MoonPhaseMonth {
  month: string;
  new_moon_date: string;
  full_moon_date: string;
}

export interface CalendarResponse {
  location_id: number;
  location_name: string;
  rig_id: number;
  rig_name: string;
  horizon_id: number;
  horizon_name: string;
  /** Location-tz "tonight" date (ISO) — anchor for the today marker. */
  today: string;
  months: string[];
  targets: CalendarTargetRow[];
  sections: SectionResponse[];
  moon_phases: MoonPhaseMonth[];
}

export async function fetchCalendarData(params: {
  locationId: number;
  horizonId: number;
  rigId: number;
  startMonth?: string;
  months?: number;
}): Promise<CalendarResponse> {
  const qs = new URLSearchParams({
    location_id: String(params.locationId),
    horizon_id: String(params.horizonId),
    rig_id: String(params.rigId),
  });
  if (params.startMonth) qs.set("start_month", params.startMonth);
  if (params.months) qs.set("months", String(params.months));
  return apiFetch<CalendarResponse>(`${PREFIX}/calendar?${qs}`);
}

// ── Query keys ─────────────────────────────────────────────────────────────

export const wishlistKeys = {
  favoriteIds: ["wishlist", "favorite-ids"] as const,
  favoritesFull: ["wishlist", "favorites-full"] as const,
  plans: (filter?: { locationId?: number; rigId?: number }) =>
    filter
      ? (["wishlist", "plans", filter] as const)
      : (["wishlist", "plans"] as const),
  calendar: (params: { locationId: number; horizonId: number; rigId: number; startMonth: string }) =>
    ["wishlist", "calendar", params] as const,
};

// ── Hooks ──────────────────────────────────────────────────────────────────

export function useFavoriteIds() {
  return useQuery({
    queryKey: wishlistKeys.favoriteIds,
    queryFn: fetchFavoriteIds,
    staleTime: 30_000,
    select: (data) => new Set(data.dso_ids),
  });
}

export function useFavoritesFull() {
  return useQuery({
    queryKey: wishlistKeys.favoritesFull,
    queryFn: fetchFavoritesFull,
    staleTime: 30_000,
  });
}

export function useAddFavorite() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: addFavorite,
    onMutate: async (dsoId) => {
      await qc.cancelQueries({ queryKey: wishlistKeys.favoriteIds });
      const prev = qc.getQueryData<FavoriteIdsResponse>(wishlistKeys.favoriteIds);
      if (prev) {
        qc.setQueryData<FavoriteIdsResponse>(wishlistKeys.favoriteIds, {
          dso_ids: [...prev.dso_ids, dsoId],
        });
      }
      return { prev };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.prev) qc.setQueryData(wishlistKeys.favoriteIds, ctx.prev);
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: wishlistKeys.favoriteIds });
      qc.invalidateQueries({ queryKey: wishlistKeys.favoritesFull });
    },
  });
}

export function useRemoveFavorite() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: removeFavorite,
    onMutate: async (dsoId) => {
      await qc.cancelQueries({ queryKey: wishlistKeys.favoriteIds });
      const prev = qc.getQueryData<FavoriteIdsResponse>(wishlistKeys.favoriteIds);
      if (prev) {
        qc.setQueryData<FavoriteIdsResponse>(wishlistKeys.favoriteIds, {
          dso_ids: prev.dso_ids.filter((id) => id !== dsoId),
        });
      }
      return { prev };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.prev) qc.setQueryData(wishlistKeys.favoriteIds, ctx.prev);
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: wishlistKeys.favoriteIds });
      qc.invalidateQueries({ queryKey: wishlistKeys.favoritesFull });
      qc.invalidateQueries({ queryKey: ["wishlist", "plans"] });
      qc.invalidateQueries({ queryKey: ["wishlist", "calendar"] });
    },
  });
}

export function useReorderFavorites() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: reorderFavorites,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["wishlist", "calendar"] });
    },
  });
}

export function useSectionMutations() {
  const qc = useQueryClient();
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: wishlistKeys.favoritesFull });
    qc.invalidateQueries({ queryKey: ["wishlist", "calendar"] });
  };
  const create = useMutation({ mutationFn: createSection, onSuccess: invalidate });
  const rename = useMutation({
    mutationFn: ({ id, name }: { id: number; name: string }) => renameSection(id, name),
    onSuccess: invalidate,
  });
  const remove = useMutation({ mutationFn: deleteSection, onSuccess: invalidate });
  const reorder = useMutation({
    mutationFn: reorderSections,
    onSuccess: invalidate,
  });
  const move = useMutation({
    mutationFn: ({ dsoId, sectionId, sortOrder }: {
      dsoId: number; sectionId: number | null; sortOrder?: number;
    }) => moveFavorite(dsoId, sectionId, sortOrder),
    onSuccess: invalidate,
  });
  return { create, rename, remove, reorder, move };
}

export function usePlans(filter?: { locationId?: number; rigId?: number }) {
  return useQuery({
    queryKey: wishlistKeys.plans(filter),
    queryFn: () =>
      fetchPlans(
        filter
          ? { location_id: filter.locationId, rig_id: filter.rigId }
          : undefined,
      ),
    staleTime: 30_000,
  });
}

export function useCreatePlan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createPlan,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: wishlistKeys.favoriteIds });
      qc.invalidateQueries({ queryKey: wishlistKeys.favoritesFull });
      qc.invalidateQueries({ queryKey: ["wishlist", "plans"] });
      qc.invalidateQueries({ queryKey: ["wishlist", "calendar"] });
    },
  });
}

export function useUpdatePlan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ planId, params }: { planId: number; params: UpdatePlanParams }) =>
      updatePlan(planId, params),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: wishlistKeys.favoritesFull });
      qc.invalidateQueries({ queryKey: ["wishlist", "plans"] });
      qc.invalidateQueries({ queryKey: ["wishlist", "calendar"] });
    },
  });
}

export function useDeletePlan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: deletePlan,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: wishlistKeys.favoritesFull });
      qc.invalidateQueries({ queryKey: ["wishlist", "plans"] });
      qc.invalidateQueries({ queryKey: ["wishlist", "calendar"] });
    },
  });
}

export function useCalendarData(params: {
  locationId: number;
  horizonId: number;
  rigId: number;
  startMonth?: string;
}) {
  return useQuery({
    queryKey: wishlistKeys.calendar({
      locationId: params.locationId,
      horizonId: params.horizonId,
      rigId: params.rigId,
      startMonth: params.startMonth ?? new Date().toISOString().slice(0, 7),
    }),
    queryFn: () => fetchCalendarData(params),
    staleTime: 5 * 60_000,
    enabled: params.locationId > 0 && params.horizonId > 0 && params.rigId > 0,
  });
}
