import { apiFetch } from "./client";

export interface ProjectTarget {
  /** Project-level link between this project and one catalog object. */
  id: number;
  dso_id: number;
  active: boolean;
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
