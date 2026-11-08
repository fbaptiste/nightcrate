import { apiFetch } from "./client";
import type { PlateSolver, SolveAttempt, WcsParams } from "./plateSolve";

export interface IdentifiedDso {
  dso_id: number;
  active: boolean;
  primary_designation: string;
  common_name: string | null;
  other_names: string[];
  obj_type: string;
  type_group: string;
  constellation: string | null;
  ra_deg: number;
  dec_deg: number;
  maj_axis_arcmin: number | null;
  min_axis_arcmin: number | null;
  distance_pc: number | null;
  mag_b: number | null;
  is_main: boolean;
  pixel_x: number;
  pixel_y: number;
  ellipse_semi_major_px: number | null;
  ellipse_semi_minor_px: number | null;
  ellipse_angle_deg: number | null;
}

export interface FocalLengthEstimate {
  rig_id: number;
  rig_name: string;
  camera_name: string;
  pixel_size_um: number;
  rig_focal_length_mm: number;
  estimated_focal_length_mm: number;
}

export interface ProjectSolve {
  id: number;
  project_id: number;
  image_path: string;
  image_width: number;
  image_height: number;
  center_ra_deg: number;
  center_dec_deg: number;
  ra_hms: string | null;
  dec_dms: string | null;
  pixel_scale_arcsec: number | null;
  rotation_deg: number | null;
  fov_width_arcmin: number | null;
  fov_height_arcmin: number | null;
  solved_at: string;
  solver: PlateSolver;
  star_catalog: string | null;
  stars_detected: number | null;
  stars_matched: number | null;
  rms_px: number | null;
  rms_arcsec: number | null;
  log_odds: number | null;
  solve_path: "near_index" | "near_catalog" | "blind" | null;
  scale_stage: string | null;
  attempts: SolveAttempt[];
  wcs: WcsParams;
  objects: IdentifiedDso[];
  focal_length_estimates: FocalLengthEstimate[];
}

export interface CreateSolveRequest {
  image_path: string;
  hdu?: number;
  operation_id: string;
  replace?: boolean;
  ra_hint?: number;
  dec_hint?: number;
  fov_hint?: number;
  scale_hint_arcsec?: number;
  position?: "auto" | "none";
  scale?: "auto" | "none";
  solver?: PlateSolver;
}

export async function getProjectSolve(projectId: number): Promise<ProjectSolve | null> {
  return (await apiFetch<ProjectSolve | null>(`/projects/${projectId}/solve`)) ?? null;
}

export async function createProjectSolve(
  projectId: number,
  body: CreateSolveRequest,
): Promise<ProjectSolve> {
  return apiFetch<ProjectSolve>(`/projects/${projectId}/solve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function setProjectObjectMain(
  projectId: number,
  dsoId: number,
  isMain: boolean,
): Promise<ProjectSolve> {
  return apiFetch<ProjectSolve>(`/projects/${projectId}/solve/objects/${dsoId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ is_main: isMain }),
  });
}

export async function deleteProjectSolve(projectId: number): Promise<void> {
  return apiFetch<void>(`/projects/${projectId}/solve`, { method: "DELETE" });
}

export function projectSolveImageUrl(
  projectId: number,
  variant: "full" | "thumb_lg" | "thumb_md" | "thumb_sm" = "full",
  solveId?: number,
): string {
  const v = solveId != null ? `?_v=${solveId}` : "";
  return `/api/projects/${projectId}/solve/image/${variant}${v}`;
}
