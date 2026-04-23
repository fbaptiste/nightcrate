import { apiFetch } from "./client";

export interface HorizonPoint {
  azimuth_deg: number;
  altitude_deg: number;
}

export type HorizonSource = "imported" | "drawn";
export type HorizonType = "artificial" | "custom";

/** One horizon on a location. Multiple horizons per location are
 *  allowed (one optional ``custom`` polyline + zero-or-more
 *  ``artificial`` flat-altitude rows); ``is_default`` marks the one
 *  the planner uses by default. */
export interface Horizon {
  id: number;
  location_id: number;
  name: string;
  type: HorizonType;
  flat_altitude_deg: number | null;
  source: HorizonSource | null;
  source_filename: string | null;
  notes: string | null;
  points: HorizonPoint[];
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface HorizonImportResponse {
  horizon: Horizon;
  warnings: string[];
}

export interface HorizonCreateBody {
  name: string;
  type: HorizonType;
  flat_altitude_deg?: number | null;
  points?: HorizonPoint[] | null;
  source?: HorizonSource | null;
  source_filename?: string | null;
  notes?: string | null;
  is_default?: boolean;
}

export interface HorizonUpdateBody {
  name?: string;
  flat_altitude_deg?: number | null;
  points?: HorizonPoint[] | null;
  notes?: string | null;
  is_default?: boolean;
}

export const fetchHorizons = (locationId: number): Promise<Horizon[]> =>
  apiFetch<Horizon[]>(`/locations/${locationId}/horizons`);

export const createHorizon = (locationId: number, body: HorizonCreateBody) =>
  apiFetch<Horizon>(`/locations/${locationId}/horizons`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

export const updateHorizon = (
  locationId: number,
  horizonId: number,
  body: HorizonUpdateBody,
) =>
  apiFetch<Horizon>(`/locations/${locationId}/horizons/${horizonId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

export const deleteHorizon = (locationId: number, horizonId: number) =>
  apiFetch<void>(`/locations/${locationId}/horizons/${horizonId}`, { method: "DELETE" });

export const importHorizon = async (
  locationId: number,
  file: File,
): Promise<HorizonImportResponse> => {
  const form = new FormData();
  form.append("file", file);
  return apiFetch<HorizonImportResponse>(`/locations/${locationId}/horizons/import`, {
    method: "POST",
    body: form,
  });
};

export interface HorizonParseResponse {
  points: HorizonPoint[];
  warnings: string[];
  source_filename: string | null;
}

/** Stateless file parse — no DB write. The custom-horizon editor uses
 *  this so users can iterate on an imported polyline before committing. */
export const parseHorizonFile = async (file: File): Promise<HorizonParseResponse> => {
  const form = new FormData();
  form.append("file", file);
  return apiFetch<HorizonParseResponse>(`/horizons/parse`, {
    method: "POST",
    body: form,
  });
};

export type HorizonExportFormat = "nina" | "stellarium" | "csv";

const EXPORT_PATHS: Record<HorizonExportFormat, string> = {
  nina: "nina.hrz",
  stellarium: "stellarium.zip",
  csv: "csv",
};

/** Triggers a browser download of the chosen export format for a
 *  specific custom horizon. Artificial horizons can't be exported. */
export function downloadHorizonExport(
  locationId: number,
  horizonId: number,
  format: HorizonExportFormat,
): void {
  const url = `/api/locations/${locationId}/horizons/${horizonId}/export/${EXPORT_PATHS[format]}`;
  const a = document.createElement("a");
  a.href = url;
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
}

/** One item in the atomic ``replaceLocationHorizons`` payload. Same
 *  shape as ``HorizonCreateBody`` but with an optional ``id`` field —
 *  present when the caller wants to UPDATE an existing row, absent
 *  when the caller wants to CREATE a new one. */
export interface HorizonReplaceItem {
  id?: number | null;
  name: string;
  type: HorizonType;
  flat_altitude_deg?: number | null;
  points?: HorizonPoint[];
  source?: HorizonSource | null;
  source_filename?: string | null;
  notes?: string | null;
  is_default: boolean;
}

/** Atomically replace the horizon set for a location. The server
 *  diff-applies creates / updates / deletes in one SQL transaction so
 *  partial network failures mid-save can't corrupt the dirty-state
 *  invariant ("Save commits everything, Cancel discards everything").
 *  Returns the fresh full horizon list. */
export const replaceLocationHorizons = (
  locationId: number,
  horizons: HorizonReplaceItem[],
): Promise<Horizon[]> =>
  apiFetch<Horizon[]>(`/locations/${locationId}/horizons`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ horizons }),
  });
