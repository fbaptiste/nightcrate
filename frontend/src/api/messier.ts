import { apiFetch } from "./client";
import type { ImagingRun } from "./gallery";
import type { CropSize } from "./projects";

export interface PictureField {
  width_deg: number;
  height_deg: number;
}

export interface MessierLocation {
  id: number;
  name: string;
  latitude_deg: number;
}

export interface MessierRig {
  id: number;
  name: string;
  fov_major_deg: number | null;
  fov_minor_deg: number | null;
}

export interface MessierObject {
  dso_id: number;
  designation: string;
  common_name: string | null;
  other_names: string[];
  obj_type: string;
  constellation: string | null;
  mag_v: number | null;
  maj_axis_arcmin: number | null;
  min_axis_arcmin: number | null;
  active: boolean;
}

export interface SlotProject {
  project_id: number;
  name: string;
  status: string;
  main_image_id: number | null;
  crops: Partial<Record<CropSize, { id: number; image_id: number }>>;
  first_date: string | null;
  last_date: string | null;
  nights: number;
  imaging_runs: ImagingRun[];
  picture_fields: Partial<Record<CropSize, PictureField | null>> | null;
}

export interface MessierSlot {
  number: number;
  object: MessierObject | null;
  state: "imaged" | "project" | "none" | "missing";
  never_rises: boolean;
  projects: SlotProject[];
  survey: { field_deg: number; render_key: string } | null;
}

export interface MessierResponse {
  catalog_status: "ready" | "not_downloaded";
  location: MessierLocation | null;
  rig: MessierRig | null;
  counts: { imaged: number; project: number; never_rises: number; missing: number };
  slots: MessierSlot[];
  workspace_key: string;
}

export interface MessierParams {
  location: number | "default" | "none";
  rigId: number | null;
}

export function fetchMessier(params: MessierParams): Promise<MessierResponse> {
  const query = new URLSearchParams({ location: String(params.location) });
  if (params.rigId != null) query.set("rig_id", String(params.rigId));
  return apiFetch<MessierResponse>(`/messier?${query.toString()}`);
}
