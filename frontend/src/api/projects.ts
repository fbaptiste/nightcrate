import { apiFetch } from "./client";

// ── Types ─────────────────────────────────────────────────────────────────

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
  size: string;
  source_image_id: number | null;
  crop_x: number;
  crop_y: number;
  crop_w: number;
  crop_h: number;
}

export interface ThumbnailCropDef {
  source_image_id?: number | null;
  crop_x?: number;
  crop_y?: number;
  crop_w?: number;
  crop_h?: number;
}

export interface Project {
  id: number;
  name: string;
  description: string | null;
  notes: string | null;
  status: string;
  active: boolean;
  images: ProjectImage[];
  thumbnail_crops: ThumbnailCrop[];
  created_at: string;
  updated_at: string;
}

export interface ProjectListItem {
  id: number;
  name: string;
  description: string | null;
  status: string;
  active: boolean;
  image_count: number;
  main_image_path: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectCreate {
  name: string;
  description?: string | null;
  notes?: string | null;
  status?: string;
}

export interface ProjectUpdate {
  name?: string;
  description?: string;
  notes?: string;
  status?: string;
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
  crops: Record<string, ThumbnailCropDef>,
): Promise<Project> {
  return apiFetch<Project>(`/projects/${projectId}/thumbnails`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ crops }),
  });
}

export function projectThumbnailUrl(
  projectId: number,
  size?: "small" | "medium" | "large",
  updatedAt?: string,
): string {
  const sp = new URLSearchParams();
  if (size && size !== "small") sp.set("size", size);
  if (updatedAt) sp.set("_v", updatedAt);
  const qs = sp.toString();
  return `/api/projects/${projectId}/thumbnail${qs ? `?${qs}` : ""}`;
}

export function renderedImageUrl(
  projectId: number,
  imageId: number,
  variant: "full" | "thumb_lg" | "thumb_md" | "thumb_sm",
): string {
  return `/api/projects/${projectId}/images/${imageId}/rendered/${variant}`;
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
