import { apiFetch } from "./client";

export interface DsoDesignation {
  catalog: string;
  identifier: string;
  display_form: string;
  is_primary: boolean;
}

export type DistanceMethod = "50mgc" | "curated" | "redshift";

export interface DsoListItem {
  id: number;
  primary_designation: string;
  obj_type: string;
  ra_deg: number | null;
  dec_deg: number | null;
  constellation: string | null;
  maj_axis_arcmin: number | null;
  min_axis_arcmin: number | null;
  mag_v: number | null;
  mag_b: number | null;
  distance_pc: number | null;
  distance_method: DistanceMethod | null;
  common_name: string | null;
  designations: DsoDesignation[];
}

export interface DsoListResponse {
  total: number;
  offset: number;
  limit: number;
  items: DsoListItem[];
}

export interface CatalogSource {
  id: number;
  source_id: string;
  category: string;
  display_name: string;
  version: string | null;
  source_url: string | null;
  license: string | null;
  attribution: string | null;
  loaded_at: string;
  row_count: number;
}

export interface DsoDetail extends Omit<DsoListItem, "designations"> {
  raw_obj_type: string | null;
  position_angle_deg: number | null;
  mag_j: number | null;
  mag_h: number | null;
  mag_k: number | null;
  surface_brightness: number | null;
  hubble_type: string | null;
  pm_ra: number | null;
  pm_dec: number | null;
  redshift: number | null;
  radial_velocity: number | null;
  cstar_mag_u: number | null;
  cstar_mag_b: number | null;
  cstar_mag_v: number | null;
  cstar_id: string | null;
  common_name_augmented: boolean;
  surface_brightness_augmented: boolean;
  ned_notes: string | null;
  openngc_notes: string | null;
  raw_other_id: string | null;
  designations: DsoDesignation[];
  source: CatalogSource;
}

export interface TypeGroupFacet {
  name: string;
  display_order: number;
  count: number;
  raw_types: string[];
}

export interface RawTypeFacet {
  code: string;
  count: number;
}

export interface ConstellationFacet {
  code: string;
  count: number;
}

export interface DsoFacets {
  type_groups: TypeGroupFacet[];
  raw_types: RawTypeFacet[];
  constellations: ConstellationFacet[];
}

export interface DsoListParams {
  q?: string | null;
  type?: string[];
  type_group?: string[];
  constellation?: string | null;
  has_distance?: boolean | null;
  limit?: number;
  offset?: number;
  sort?: string;
  sort_dir?: "asc" | "desc";
}

export function fetchDsos(params: DsoListParams): Promise<DsoListResponse> {
  const qs = new URLSearchParams();
  if (params.q) qs.set("q", params.q);
  if (params.type?.length) qs.set("type", params.type.join(","));
  if (params.type_group?.length) qs.set("type_group", params.type_group.join(","));
  if (params.constellation) qs.set("constellation", params.constellation);
  if (params.has_distance != null) qs.set("has_distance", String(params.has_distance));
  if (params.limit != null) qs.set("limit", String(params.limit));
  if (params.offset != null) qs.set("offset", String(params.offset));
  if (params.sort) qs.set("sort", params.sort);
  if (params.sort_dir) qs.set("sort_dir", params.sort_dir);
  const query = qs.toString();
  return apiFetch<DsoListResponse>(`/dso${query ? `?${query}` : ""}`);
}

export const fetchDso = (id: number) => apiFetch<DsoDetail>(`/dso/${id}`);

export const lookupDso = (q: string) =>
  apiFetch<DsoDetail | null>(`/dso/lookup?q=${encodeURIComponent(q)}`);

export interface DsoFacetsParams {
  q?: string | null;
  constellation?: string | null;
  has_distance?: boolean | null;
  /** Raw ``obj_type`` codes — comma-joined by the caller. */
  type?: string[];
  /** Type-group names — comma-joined by the caller. */
  type_group?: string[];
}

/** Fetch facet counts. When any filter param is set, counts are
 *  faceted — each chip's tally reflects the filter state with that
 *  chip's own dimension excluded. When no params are passed, the
 *  endpoint returns classic full-catalog totals. */
export function fetchDsoFacets(params: DsoFacetsParams = {}): Promise<DsoFacets> {
  const qs = new URLSearchParams();
  if (params.q) qs.set("q", params.q);
  if (params.constellation) qs.set("constellation", params.constellation);
  if (params.has_distance === true) qs.set("has_distance", "true");
  else if (params.has_distance === false) qs.set("has_distance", "false");
  if (params.type?.length) qs.set("type", params.type.join(","));
  if (params.type_group?.length) qs.set("type_group", params.type_group.join(","));
  const query = qs.toString();
  return apiFetch<DsoFacets>(query ? `/dso/facets?${query}` : "/dso/facets");
}

export const fetchCatalogSources = () =>
  apiFetch<CatalogSource[]>(`/dso/catalog-sources`);

export interface ReloadCatalogsResponse {
  total_dsos: number;
  total_designations: number;
  per_source: {
    source_id: string;
    status: string;
    dso_count: number;
    designation_count: number;
    unresolved_duplicates: number;
    error: string | null;
  }[];
}

export const reloadCatalogs = () =>
  apiFetch<ReloadCatalogsResponse>("/admin/catalogs/reload", { method: "POST" });

export interface RemoteCatalogStatus {
  latest_tag: string;
  latest_published_at: string | null;
  release_url: string;
  installed_version: string | null;
  has_update: boolean;
}

export const fetchRemoteVersion = () =>
  apiFetch<RemoteCatalogStatus>("/admin/catalogs/remote-version");

export interface FetchFromGitHubResponse extends ReloadCatalogsResponse {
  /** The GitHub tag that was downloaded, or null when the call was a
   *  local re-parse (reloadCatalogs) presented through the same UI. */
  fetched_version: string | null;
}

export const fetchCatalogsFromGitHub = () =>
  apiFetch<FetchFromGitHubResponse>("/admin/catalogs/fetch-from-github", {
    method: "POST",
  });

// ── VizieR per-source endpoints (v0.15.0) ────────────────────────────────────

export type VizierSourceShortId = "sharpless" | "barnard";

export interface VizierRemoteVersion {
  source_id: string;
  catalog_id: string;
  display_name: string;
  latest_tag: string;
  installed_version: string | null;
  release_url: string;
  has_update: boolean;
}

export interface VizierFetchResponse {
  source_id: string;
  fetched_at: string;
  size_bytes: number;
  total_dsos: number;
  total_designations: number;
  per_source: FetchFromGitHubResponse["per_source"];
}

export const fetchVizierRemoteVersion = (shortId: VizierSourceShortId) =>
  apiFetch<VizierRemoteVersion>(`/admin/catalogs/vizier/${shortId}/remote-version`);

export const fetchVizierCatalog = (shortId: VizierSourceShortId) =>
  apiFetch<VizierFetchResponse>(`/admin/catalogs/vizier/${shortId}/fetch`, {
    method: "POST",
  });

export const reloadNightcrateCatalogs = () =>
  apiFetch<ReloadCatalogsResponse>("/admin/catalogs/nightcrate/reload", {
    method: "POST",
  });

// ── 50 MGC (GitHub, not VizieR) — v0.15.0 ───────────────────────────────────

export interface Mgc50RemoteVersion {
  source_id: string;
  display_name: string;
  repository_url: string;
  raw_url: string;
  installed_fetched_at: string | null;
  installed_sha256: string | null;
  has_update: boolean;
}

export interface Mgc50FetchResponse extends ReloadCatalogsResponse {
  source_id: string;
  fetched_at: string;
  size_bytes: number;
  sha256: string;
}

export const fetch50mgcRemoteVersion = () =>
  apiFetch<Mgc50RemoteVersion>("/admin/catalogs/50mgc/remote-version");

export const fetch50mgcFromGitHub = () =>
  apiFetch<Mgc50FetchResponse>("/admin/catalogs/50mgc/fetch", {
    method: "POST",
  });
