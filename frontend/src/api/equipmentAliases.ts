import { apiFetch } from "./client";

// ── Types (mirror api/equipment_aliases.py) ─────────────────────────────────

export interface UnresolvedObservation {
  id: number;
  equipment_kind: "camera" | "telescope" | "filter";
  normalized_alias: string;
  original_observation: string;
  first_seen_at: string;
  last_seen_at: string;
  seen_count: number;
  source: string;
  resolved_to_equipment_id: number | null;
  resolved_at: string | null;
}

export interface UnresolvedObservationsPage {
  items: UnresolvedObservation[];
  pending_total: number;
  pending_by_kind: Record<string, number>;
}

export interface ConfirmResult {
  alias_id: number;
  observation: UnresolvedObservation;
}

// ── Endpoints ────────────────────────────────────────────────────────────────

export function fetchUnresolvedObservations(): Promise<UnresolvedObservationsPage> {
  return apiFetch<UnresolvedObservationsPage>("/equipment/unresolved");
}

/** Map a pending observation to an equipment row (inserts a confirmed alias). */
export function confirmObservation(
  observationId: number,
  equipmentId: number,
): Promise<ConfirmResult> {
  return apiFetch<ConfirmResult>(
    `/equipment/unresolved/${observationId}/confirm`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ equipment_id: equipmentId }),
    },
  );
}

/** Drop a pending observation (reappears if a later ingest sees it again). */
export function dismissObservation(observationId: number): Promise<void> {
  return apiFetch<void>(`/equipment/unresolved/${observationId}`, {
    method: "DELETE",
  });
}
