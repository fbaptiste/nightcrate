import { apiFetch } from "./client";

export interface HorizonPoint {
  azimuth_deg: number;
  altitude_deg: number;
}

export type HorizonSource = "imported" | "drawn";

export interface HorizonResponse {
  location_id: number;
  source: HorizonSource;
  source_filename: string | null;
  notes: string | null;
  points: HorizonPoint[];
  created_at: string;
  updated_at: string;
}

export interface HorizonImportResponse {
  horizon: HorizonResponse;
  warnings: string[];
}

export interface HorizonPutBody {
  source: "drawn";
  points: HorizonPoint[];
  notes?: string | null;
}

export const fetchHorizon = async (locationId: number): Promise<HorizonResponse | null> => {
  try {
    return await apiFetch<HorizonResponse>(`/locations/${locationId}/horizon`);
  } catch (e) {
    if (e instanceof Error && /404/.test(e.message)) return null;
    throw e;
  }
};

export const saveHorizon = (locationId: number, body: HorizonPutBody) =>
  apiFetch<HorizonResponse>(`/locations/${locationId}/horizon`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

export const deleteHorizon = (locationId: number) =>
  apiFetch<void>(`/locations/${locationId}/horizon`, { method: "DELETE" });

export const importHorizon = async (
  locationId: number,
  file: File,
): Promise<HorizonImportResponse> => {
  const form = new FormData();
  form.append("file", file);
  return apiFetch<HorizonImportResponse>(`/locations/${locationId}/horizon/import`, {
    method: "POST",
    body: form,
  });
};

export interface HorizonParseResponse {
  points: HorizonPoint[];
  warnings: string[];
  source_filename: string | null;
}

/**
 * Stateless file parse — no DB write. Used by the staged-save flow in
 * the Location editor: import a file, load points into the editor, and
 * defer persistence to the outer Location save.
 */
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

/**
 * Triggers a browser download of the chosen export format. Uses a
 * plain anchor click so the browser streams the response directly
 * to disk without the frontend reading the bytes.
 */
export function downloadHorizonExport(locationId: number, format: HorizonExportFormat): void {
  const url = `/api/locations/${locationId}/horizon/export/${EXPORT_PATHS[format]}`;
  const a = document.createElement("a");
  a.href = url;
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
}
