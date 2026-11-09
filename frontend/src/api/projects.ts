import { apiFetch } from "./client";
import type { RigParts, RigPartsInput } from "./rigs";

// ── Types ─────────────────────────────────────────────────────────────────

export type ProjectStatus = "active" | "paused" | "complete" | "abandoned";
export type CropSize = "small" | "medium" | "large";

export interface ProjectImage {
  id: number;
  project_id: number;
  file_path: string;
  display_order: number;
  is_main: boolean;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface ThumbnailCrop {
  size: CropSize;
  source_image_id: number | null;
  crop_x: number;
  crop_y: number;
  crop_w: number;
  crop_h: number;
}

export interface ThumbnailCropDef {
  source_image_id: number | null;
  crop_x: number;
  crop_y: number;
  crop_w: number;
  crop_h: number;
}

export interface ProjectRigRef {
  id: number;
  name: string;
  active: boolean;
}

export interface ProjectSoftwareRef {
  id: number;
  software_id: number;
  name: string;
  category: string;
  manufacturer_name: string | null;
  software_version_id: number | null;
  version: string | null;
  active: boolean;
}

export interface ProjectRigSetupParts extends RigParts {
  effective_focal_length_mm: number;
  effective_focal_ratio: number;
  pixel_size_um: number;
  sensor_resolution_x: number;
  sensor_resolution_y: number;
  image_scale_arcsec_per_pixel: number;
  field_of_view_deg: [number, number];
}

export interface ProjectSetup {
  rig_setup_id: number | null;
  until_at: string | null;
  since_at: string | null;
  night_count: number;
  parts: ProjectRigSetupParts;
}

export interface ProjectSetupOption {
  rig_setup_id: number | null;
  until_at: string | null;
  camera_name: string;
  image_scale_arcsec_per_pixel: number;
}

export interface ProjectRigSetups {
  rig_id: number;
  rig_name: string;
  declared: boolean;
  setups: ProjectSetup[];
  setup_options: ProjectSetupOption[];
  base_parts: RigPartsInput;
  change: RigPartsInput | null;
  changed_groups: string[];
}

export interface Project {
  id: number;
  name: string;
  description: string | null;
  notes: string | null;
  status: ProjectStatus;
  active: boolean;
  location_id: number | null;
  location_name: string | null;
  rigs: ProjectRigRef[];
  software: ProjectSoftwareRef[];
  images: ProjectImage[];
  thumbnail_crops: ThumbnailCrop[];
  solved_at: string | null;
  workspace_key: string;
  created_at: string;
  updated_at: string;
}

export interface ProjectListItem {
  id: number;
  name: string;
  description: string | null;
  status: ProjectStatus;
  active: boolean;
  image_count: number;
  main_image_path: string | null;
  thumbnail_version: string;
  workspace_key: string;
  created_at: string;
  updated_at: string;
}

export interface ProjectCreate {
  name: string;
  description?: string | null;
  notes?: string | null;
  status?: ProjectStatus;
}

export interface ProjectUpdate {
  name?: string;
  description?: string;
  notes?: string;
  status?: ProjectStatus;
  location_id?: number | null;
}

// ── Fetch functions ───────────────────────────────────────────────────────

export interface ProjectListParams {
  q?: string;
  sort?: string;
  desc?: boolean;
  include_retired?: boolean;
}

export async function fetchProjects(
  params?: ProjectListParams,
): Promise<ProjectListItem[]> {
  const sp = new URLSearchParams();
  if (params?.q) sp.set("q", params.q);
  if (params?.sort) sp.set("sort", params.sort);
  if (params?.desc !== undefined) sp.set("desc", String(params.desc));
  if (params?.include_retired) sp.set("include_retired", "true");
  const qs = sp.toString();
  return apiFetch<ProjectListItem[]>(`/projects${qs ? `?${qs}` : ""}`);
}

export async function fetchProject(id: number): Promise<Project> {
  return apiFetch<Project>(`/projects/${id}`);
}

export async function createProject(data: ProjectCreate): Promise<Project> {
  return apiFetch<Project>("/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function updateProject(
  id: number,
  data: ProjectUpdate,
): Promise<Project> {
  return apiFetch<Project>(`/projects/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function setProjectRigs(
  id: number,
  rigIds: number[],
): Promise<Project> {
  return apiFetch<Project>(`/projects/${id}/rigs`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rig_ids: rigIds }),
  });
}

export async function fetchProjectRigSetups(id: number): Promise<ProjectRigSetups[]> {
  return apiFetch<ProjectRigSetups[]>(`/projects/${id}/rig-setups`);
}

export async function setProjectRigChange(
  projectId: number,
  rigId: number,
  parts: RigPartsInput,
): Promise<ProjectRigSetups> {
  return apiFetch<ProjectRigSetups>(`/projects/${projectId}/rigs/${rigId}/change`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(parts),
  });
}

export async function deleteProjectRigChange(
  projectId: number,
  rigId: number,
): Promise<void> {
  return apiFetch<void>(`/projects/${projectId}/rigs/${rigId}/change`, {
    method: "DELETE",
  });
}

export async function setProjectSoftware(
  projectId: number,
  entries: { software_id: number; software_version_id: number | null }[],
): Promise<Project> {
  return apiFetch<Project>(`/projects/${projectId}/software`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ entries }),
  });
}

export async function deleteProject(id: number): Promise<void> {
  return apiFetch<void>(`/projects/${id}`, { method: "DELETE" });
}

export async function restoreProject(id: number): Promise<Project> {
  return apiFetch<Project>(`/projects/${id}/restore`, { method: "POST" });
}

export async function permanentlyDeleteProject(id: number): Promise<void> {
  return apiFetch<void>(`/projects/${id}/permanent`, { method: "DELETE" });
}

export async function addImages(
  projectId: number,
  filePaths: string[],
): Promise<ProjectImage[]> {
  return apiFetch<ProjectImage[]>(`/projects/${projectId}/images`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ file_paths: filePaths }),
  });
}

export async function removeImage(
  projectId: number,
  imageId: number,
): Promise<void> {
  return apiFetch<void>(`/projects/${projectId}/images/${imageId}`, {
    method: "DELETE",
  });
}

export async function reorderImages(
  projectId: number,
  imageIds: number[],
): Promise<Project> {
  return apiFetch<Project>(`/projects/${projectId}/images/order`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ image_ids: imageIds }),
  });
}

export async function setMainImage(
  projectId: number,
  imageId: number,
): Promise<Project> {
  return apiFetch<Project>(`/projects/${projectId}/images/${imageId}/main`, {
    method: "POST",
  });
}

export async function updateImageNotes(
  projectId: number,
  imageId: number,
  notes: string | null,
): Promise<ProjectImage> {
  return apiFetch<ProjectImage>(`/projects/${projectId}/images/${imageId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ notes }),
  });
}

export async function saveThumbnailCrops(
  projectId: number,
  crops: Partial<Record<CropSize, ThumbnailCropDef>>,
): Promise<Project> {
  return apiFetch<Project>(`/projects/${projectId}/thumbnails`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ crops }),
  });
}

export function projectThumbnailUrl(
  projectId: number,
  size: CropSize,
  version: string,
  workspaceKey: string,
): string {
  const sp = new URLSearchParams();
  sp.set("size", size);
  sp.set("v", version);
  sp.set("ws", workspaceKey);
  return `/api/projects/${projectId}/thumbnail?${sp.toString()}`;
}

export function renderedImageUrl(
  projectId: number,
  imageId: number,
  variant: "full" | "thumb_lg" | "thumb_md" | "thumb_sm",
  workspaceKey: string,
): string {
  const sp = new URLSearchParams({ ws: workspaceKey });
  return `/api/projects/${projectId}/images/${imageId}/rendered/${variant}?${sp.toString()}`;
}

export const PROJECT_STATUS_COLORS: Record<
  string,
  "default" | "warning" | "info"
> = {
  active: "default",
  paused: "warning",
  complete: "info",
  abandoned: "default",
};
