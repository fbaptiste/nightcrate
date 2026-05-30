import { apiFetch } from "./client";

export interface ProjectTarget {
  dso_id: number;
  primary_designation: string;
  common_name: string | null;
  obj_type: string;
  ra_deg: number | null;
  dec_deg: number | null;
  created_at: string;
}

export function listProjectTargets(projectId: number): Promise<ProjectTarget[]> {
  return apiFetch<ProjectTarget[]>(`/projects/${projectId}/targets`);
}

export function addProjectTarget(projectId: number, dsoId: number): Promise<ProjectTarget> {
  return apiFetch<ProjectTarget>(`/projects/${projectId}/targets`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dso_id: dsoId }),
  });
}

export function removeProjectTarget(projectId: number, dsoId: number): Promise<void> {
  return apiFetch<void>(`/projects/${projectId}/targets/${dsoId}`, {
    method: "DELETE",
  });
}
