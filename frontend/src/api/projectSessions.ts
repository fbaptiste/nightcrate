import { apiFetch } from "./client";

// ── Types ─────────────────────────────────────────────────────────────────

export interface ProjectSession {
  id: number;
  project_id: number;
  rig_id: number | null;
  rig_name: string | null;
  filter_id: number | null;
  filter_name: string | null;
  filter_label: string | null;
  line_name: string | null;
  exposure_seconds: number;
  gain: number | null;
  num_subs: number;
  binning: number | null;
  session_date: string | null;
  notes: string | null;
  source: "manual" | "auto";
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
  /** Canonical bandpass ("Ha") or, for a filter name that isn't one, the name
   *  itself ("L-eXtreme"). Render verbatim — do not interpret. */
  label: string;
  actual_minutes: number;
  /** Distinct observing nights, not rows — one night split across exposures is one. */
  session_count: number;
  sub_count: number;
}

export interface IntegrationSummary {
  lines: IntegrationLine[];
  total_actual_minutes: number;
  first_session_date: string | null;
  last_session_date: string | null;
}

export interface DerivationSummary {
  project_id: number;
  lights_considered: number;
  /** Lights with a non-positive exposure — no session can represent them. */
  lights_skipped: number;
  sessions_replaced: number;
  sessions_created: number;
  manual_sessions_kept: number;
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

/** Rebuild the project's derived sessions from its cataloged light frames.
 *  Replaces every `source: "auto"` row; manual ones are left alone. */
export function deriveSessions(projectId: number): Promise<DerivationSummary> {
  return apiFetch<DerivationSummary>(`/projects/${projectId}/sessions/derive`, {
    method: "POST",
  });
}

// ── Integration ─────────────────────────────────────────────────────────────

export function getIntegration(projectId: number): Promise<IntegrationSummary> {
  return apiFetch<IntegrationSummary>(`/projects/${projectId}/integration`);
}
