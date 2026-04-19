import { apiFetch } from "./client";

export interface DsoDesignation {
  catalog: string;
  identifier: string;
  display_form: string;
  is_primary: boolean;
}

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
  ned_notes: string | null;
  openngc_notes: string | null;
  raw_other_id: string | null;
  designations: DsoDesignation[];
  source: CatalogSource;
}

export interface DsoFacets {
  obj_types: { value: string; count: number }[];
  constellations: { value: string; count: number }[];
}

export interface DsoListParams {
  q?: string | null;
  type?: string[];
  constellation?: string | null;
  limit?: number;
  offset?: number;
  sort?: string;
  sort_dir?: "asc" | "desc";
}

export function fetchDsos(params: DsoListParams): Promise<DsoListResponse> {
  const qs = new URLSearchParams();
  if (params.q) qs.set("q", params.q);
  if (params.type?.length) qs.set("type", params.type.join(","));
  if (params.constellation) qs.set("constellation", params.constellation);
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

export const fetchDsoFacets = () => apiFetch<DsoFacets>(`/dso/facets`);

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
