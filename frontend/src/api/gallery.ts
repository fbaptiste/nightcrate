import { apiFetch } from "./client";
import type { CropSize } from "./projects";

export interface ImagingRun {
  start: string;
  end: string;
}

export interface GalleryTarget {
  dso_id: number;
  name: string;
  also_known_as: string[];
}

export interface GalleryRig {
  id: number;
  name: string;
}

export interface GalleryMark {
  dso_id: number;
  designation: string;
  common_name: string | null;
  pixel_x: number;
  pixel_y: number;
  semi_major_px: number | null;
  semi_minor_px: number | null;
  angle_deg: number | null;
  inset_radius_px: number;
  main_target: boolean;
}

export interface GallerySolveMarks {
  solve_id: number;
  width: number;
  height: number;
  pixel_scale_arcsec: number;
  marks: GalleryMark[];
}

export interface GallerySearchObject {
  dso_id: number;
  designation: string;
  common_name: string | null;
  alias: string | null;
}

export interface GallerySuggestion {
  dso_id: number;
  designation: string;
  detail: string | null;
  project_count: number;
}

export interface GalleryItem {
  project_id: number;
  name: string;
  status: string;
  retired: boolean;
  main_image_id: number | null;
  crops: Partial<Record<CropSize, { id: number; image_id: number }>>;
  targets: GalleryTarget[];
  first_date: string | null;
  last_date: string | null;
  nights: number;
  imaging_runs: ImagingRun[];
  integration_minutes: number;
  rigs: GalleryRig[];
  match_main_target: boolean;
  match_in_image: boolean;
  solve: GallerySolveMarks | null;
  has_solve: boolean;
}

export interface FacetCount {
  code: string;
  count: number;
}

export interface RigFacetCount {
  id: number;
  name: string;
  count: number;
}

export interface GalleryFacets {
  catalogs: FacetCount[];
  type_groups: FacetCount[];
  constellations: FacetCount[];
  statuses: FacetCount[];
  rigs: RigFacetCount[];
}

export interface GalleryResponse {
  items: GalleryItem[];
  facets: GalleryFacets;
  library_total: number;
  workspace_key: string;
  search_object: GallerySearchObject | null;
}

export interface GalleryParams {
  q?: string;
  catalog?: string[];
  type_group?: string[];
  constellation?: string[];
  status?: string[];
  rig?: number[];
  imaged_from?: string;
  imaged_to?: string;
  include_undated?: boolean;
  include_retired?: boolean;
  search_images?: boolean;
  sort?: "latest" | "first" | "name";
  desc?: boolean;
}

export async function fetchGallery(params: GalleryParams): Promise<GalleryResponse> {
  const searchParams = new URLSearchParams();
  if (params.q) searchParams.set("q", params.q);

  const listParams = [
    ["catalog", params.catalog],
    ["type_group", params.type_group],
    ["constellation", params.constellation],
    ["status", params.status],
  ] as const;
  for (const [key, values] of listParams) {
    if (values?.length) searchParams.set(key, values.join(","));
  }

  if (params.rig?.length) searchParams.set("rig", params.rig.join(","));
  if (params.imaged_from) searchParams.set("imaged_from", params.imaged_from);
  if (params.imaged_to) searchParams.set("imaged_to", params.imaged_to);
  if (params.include_undated) searchParams.set("include_undated", "true");
  if (params.include_retired) searchParams.set("include_retired", "true");
  if (params.search_images) searchParams.set("search_images", "true");
  if (params.sort) searchParams.set("sort", params.sort);
  if (params.desc !== undefined) searchParams.set("desc", String(params.desc));

  return apiFetch<GalleryResponse>(`/gallery?${searchParams.toString()}`);
}

export async function fetchGallerySuggestions(
  q: string,
  searchImages: boolean,
  includeRetired: boolean,
): Promise<GallerySuggestion[]> {
  const params = new URLSearchParams({ q });
  if (searchImages) params.set("search_images", "true");
  if (includeRetired) params.set("include_retired", "true");
  return apiFetch<GallerySuggestion[]>(`/gallery/suggest?${params.toString()}`);
}
