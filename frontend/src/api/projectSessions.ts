import { apiFetch } from "./client";

// ── Types ─────────────────────────────────────────────────────────────────

export interface ProjectSession {
  id: number;
  project_id: number;
  rig_id: number | null;
  rig_name: string | null;
  filter_id: number | null;
  filter_name: string | null;
  line_name: string | null;
  exposure_seconds: number;
  gain: number | null;
  num_subs: number;
  binning: number | null;
  session_date: string | null;
  notes: string | null;
  source: string;
  integration_minutes: number;
  created_at: string;
  updated_at: string;
}

export interface SessionCreate {
  rig_id?: number | null;
  filter_id?: number | null;
  line_name?: string | null;
  exposure_seconds: number;
  gain?: number | null;
  num_subs: number;
  binning?: number | null;
  session_date?: string | null;
  notes?: string | null;
}

export type SessionUpdate = Partial<SessionCreate>;

export interface IntegrationLine {
  line_name: string;
  actual_minutes: number;
  goal_minutes: number | null;
  session_count: number;
  sub_count: number;
}

export interface IntegrationSummary {
  lines: IntegrationLine[];
  total_actual_minutes: number;
  first_session_date: string | null;
  last_session_date: string | null;
}

export interface FilterGoal {
  line_name: string;
  goal_minutes: number;
}

// ── Sessions ──────────────────────────────────────────────────────────────

export function listSessions(projectId: number): Promise<ProjectSession[]> {
  return apiFetch<ProjectSession[]>(`/projects/${projectId}/sessions`);
}

export function createSession(
  projectId: number,
  body: SessionCreate,
): Promise<ProjectSession> {
  return apiFetch<ProjectSession>(`/projects/${projectId}/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function updateSession(
  projectId: number,
  sessionId: number,
  body: SessionUpdate,
): Promise<ProjectSession> {
  return apiFetch<ProjectSession>(`/projects/${projectId}/sessions/${sessionId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function deleteSession(projectId: number, sessionId: number): Promise<void> {
  return apiFetch<void>(`/projects/${projectId}/sessions/${sessionId}`, {
    method: "DELETE",
  });
}

// ── Integration + goals ─────────────────────────────────────────────────────

export function getIntegration(projectId: number): Promise<IntegrationSummary> {
  return apiFetch<IntegrationSummary>(`/projects/${projectId}/integration`);
}

export function setFilterGoals(
  projectId: number,
  goals: FilterGoal[],
): Promise<IntegrationSummary> {
  return apiFetch<IntegrationSummary>(`/projects/${projectId}/integration/goals`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ goals }),
  });
}
