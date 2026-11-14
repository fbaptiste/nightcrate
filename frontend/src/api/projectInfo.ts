import type {
  GalleryRig,
  GalleryTarget,
  ImagingRun,
  OtherObjectDistance,
} from "./gallery";
import { apiFetch } from "./client";
import type { QueryClient } from "@tanstack/react-query";

export interface OtherObject {
  dso_id: number;
  name: string;
  designation: string;
  obj_type: string;
  constellation: string | null;
  distance_pc: number | null;
  distance_estimated: boolean;
  wikipedia_url: string | null;
}

export interface SolveField {
  constellation: string;
  centre_ra_hms: string | null;
  centre_dec_dms: string | null;
  centre_ra_deg: number;
  centre_dec_deg: number;
  fov_width_deg: number | null;
  fov_height_deg: number | null;
  rotation_deg: number | null;
}

export interface ProjectInfo {
  project_id: number;
  name: string;
  status: string;
  retired: boolean;
  solved: boolean;
  targets: GalleryTarget[];
  other_objects: OtherObject[];
  other_distances: OtherObjectDistance[];
  field: SolveField | null;
  first_date: string | null;
  last_date: string | null;
  nights: number;
  imaging_runs: ImagingRun[];
  integration_minutes: number;
  rigs: GalleryRig[];
}

export function projectInfoKey(projectId: number) {
  return ["project-info", projectId] as const;
}

export function invalidateProjectInfo(queryClient: QueryClient, projectId?: number) {
  return queryClient.invalidateQueries({
    queryKey: projectId == null ? ["project-info"] : projectInfoKey(projectId),
  });
}

export function fetchProjectInfo(projectId: number): Promise<ProjectInfo> {
  return apiFetch<ProjectInfo>(`/projects/${projectId}/info`);
}
