import { apiFetch } from "./client";

// ── Types (mirror services/ingest_models.py) ────────────────────────────────

export interface SourceFolder {
  id: number;
  project_id: number;
  path: string;
  is_primary: boolean;
  added_at: string;
}

export interface IngestStatus {
  run_id: number;
  project_id: number;
  status: string; // running | completed | failed | cancelled
  files_scanned: number;
  subs_inserted: number;
  subs_updated: number;
  subs_skipped: number;
  errors_count: number;
  started_at: string | null;
  finished_at: string | null;
  message: string | null;
}

export interface CatalogSummary {
  lights: number;
  darks: number;
  flats: number;
  bias: number;
  dark_flats: number;
  unknown_frames: number;
  processed: number;
  pxiprojects: number;
  logs: number;
  other: number;
  sessions: number;
  total_files: number;
}

export interface CatalogFrame {
  id: number;
  kind: string;
  frame_type: string | null;
  path: string | null;
  filter_name: string | null;
  object_hint: string | null;
  exposure_seconds: number | null;
  gain: number | null;
  set_temp_c: number | null;
  binning: string | null;
  image_width: number | null;
  image_height: number | null;
  file_size_bytes: number | null;
  date_obs_utc: string | null;
  camera_id: number | null;
  telescope_id: number | null;
  accepted: boolean | null;
}

export interface CatalogFramesPage {
  rows: CatalogFrame[];
  total: number;
  timezone: string;
}

export interface CatalogFilterStat {
  filter_name: string | null;
  count: number;
  total_seconds: number;
}

export interface CatalogMaster {
  id: number;
  type_label: string;
  frame_type: string | null;
  filter_name: string | null;
  ncombine: number | null;
  total_exposure_seconds: number | null;
  dimensions: string | null;
  file_size_bytes: number | null;
  date_obs_utc: string | null;
  path: string | null;
}

export interface CatalogMastersPage {
  rows: CatalogMaster[];
  total: number;
  timezone: string;
}

export interface CatalogOther {
  id: number;
  kind: string;
  type_label: string;
  path: string | null;
  size_bytes: number | null;
  date: string | null;
}

export interface CatalogOthersPage {
  rows: CatalogOther[];
  total: number;
  timezone: string;
}

// ── Folder binding ──────────────────────────────────────────────────────────

export function listFolders(projectId: number): Promise<SourceFolder[]> {
  return apiFetch<SourceFolder[]>(`/projects/${projectId}/folders`);
}

export function addFolder(
  projectId: number,
  path: string,
  isPrimary = false,
): Promise<SourceFolder> {
  return apiFetch<SourceFolder>(`/projects/${projectId}/folders`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, is_primary: isPrimary }),
  });
}

export function setPrimaryFolder(
  projectId: number,
  folderId: number,
): Promise<SourceFolder> {
  return apiFetch<SourceFolder>(
    `/projects/${projectId}/folders/${folderId}/primary`,
    {
      method: "PUT",
    },
  );
}

export function removeFolder(
  projectId: number,
  folderId: number,
): Promise<void> {
  return apiFetch<void>(`/projects/${projectId}/folders/${folderId}`, {
    method: "DELETE",
  });
}

// ── Ingest + catalog ────────────────────────────────────────────────────────

export function startIngest(
  projectId: number,
  folderId?: number,
): Promise<IngestStatus> {
  const q = folderId != null ? `?folder_id=${folderId}` : "";
  return apiFetch<IngestStatus>(`/projects/${projectId}/ingest${q}`, {
    method: "POST",
  });
}

export function fetchCatalogSummary(
  projectId: number,
): Promise<CatalogSummary> {
  return apiFetch<CatalogSummary>(`/projects/${projectId}/catalog/summary`);
}

export function fetchCatalogFrames(
  projectId: number,
  limit = 100,
  offset = 0,
  frameType: string | null = null,
  filterName: string | null = null,
): Promise<CatalogFramesPage> {
  const ft = frameType ? `&frame_type=${encodeURIComponent(frameType)}` : "";
  const fn = filterName
    ? `&filter_name=${encodeURIComponent(filterName)}`
    : "";
  return apiFetch<CatalogFramesPage>(
    `/projects/${projectId}/catalog/frames?limit=${limit}&offset=${offset}${ft}${fn}`,
  );
}

export function fetchCatalogFilterSummary(
  projectId: number,
  frameType: "light" | "flat",
): Promise<CatalogFilterStat[]> {
  return apiFetch<CatalogFilterStat[]>(
    `/projects/${projectId}/catalog/filter-summary?frame_type=${frameType}`,
  );
}

export function fetchCatalogMasters(
  projectId: number,
  limit = 100,
  offset = 0,
): Promise<CatalogMastersPage> {
  return apiFetch<CatalogMastersPage>(
    `/projects/${projectId}/catalog/masters?limit=${limit}&offset=${offset}`,
  );
}

export function fetchCatalogOthers(
  projectId: number,
  limit = 200,
  offset = 0,
): Promise<CatalogOthersPage> {
  return apiFetch<CatalogOthersPage>(
    `/projects/${projectId}/catalog/others?limit=${limit}&offset=${offset}`,
  );
}

/** URL of a cataloged frame's cached thumbnail (small auto-stretched JPEG). */
export function catalogThumbnailUrl(
  projectId: number,
  frameId: number,
): string {
  return `/api/projects/${projectId}/catalog/frames/${frameId}/thumbnail`;
}

/** URL of a processed/master image's cached thumbnail. */
export function masterThumbnailUrl(
  projectId: number,
  masterId: number,
): string {
  return `/api/projects/${projectId}/catalog/masters/${masterId}/thumbnail`;
}
