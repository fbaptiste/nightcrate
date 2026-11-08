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
  found_in_image: string[];
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
