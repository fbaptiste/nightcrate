import { apiFetch } from "./client";

// ── Types (mirror services/ingest_models.py) ────────────────────────────────

export interface SourceFolder {
  id: number;
  project_id: number;
  path: string;
  is_primary: boolean;
  /** Which rig shot the frames under this folder — declared by the user, never
   *  inferred. Frames inherit it, sessions split on it, calibration scopes on it. */
  rig_id: number | null;
  rig_name: string | null;
  /** Which target this folder holds — declared by the user, never inferred from
   *  the OBJECT header. null falls back to the project's single target. */
  project_target_id: number | null;
  target_name: string | null;
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
  filter_name: string | null; // the FITS FILTER header value
  object_hint: string | null;
  exposure_seconds: number | null;
  gain: number | null;
  set_temp_c: number | null;
  binning: string | null;
  image_width: number | null;
  image_height: number | null;
  file_size_bytes: number | null;
  date_obs_utc: string | null;
  accepted: boolean | null;
  /** Rig tagged on this frame's source folder. null = "not stated". */
  rig_name: string | null;
  // Classification (v0.41.1) — hand-correctable, guarded by a source flag.
  project_target_id: number | null;
  target_name: string | null;
  frame_type_source: "auto" | "user" | null;
  project_target_source: "auto" | "user" | null;
  // Quality metrics (v0.41.3). All null until the analyze pass has run.
  // hfr/star_count/snr_estimate stay null on calibration frames even after a
  // successful run — only lights carry stars. hfr is in PIXELS.
  hfr: number | null;
  star_count: number | null;
  median_adu: number | null;
  background_adu: number | null;
  snr_estimate: number | null;
  quality_status: QualityStatus | null;
  quality_analyzed_at: string | null;
  /** Derived on read from the tagged rig's optics (or a plate-solved scale). */
  pixel_scale_arcsec: number | null;
  /** hfr in arcseconds — the figure that is comparable across rigs. */
  hfr_arcsec: number | null;
  /** Saturation point of the frame's camera (2^ADC - 1); null if rig untagged. */
  full_scale_adu: number | null;
}

export type QualityStatus = "ok" | "no_stars" | "unreadable";

/** Server-side sort orders for the catalog list (backend allow-list). */
export const CATALOG_SORTS = [
  { value: "path", label: "File path" },
  { value: "date", label: "Date captured" },
  { value: "hfr_arcsec_desc", label: "HFR (arcsec) — worst first" },
  { value: "hfr_arcsec_asc", label: "HFR (arcsec) — best first" },
  { value: "hfr_desc", label: "HFR (px) — worst first" },
  { value: "hfr_asc", label: "HFR (px) — best first" },
  { value: "stars_asc", label: "Fewest stars first" },
  { value: "background_desc", label: "Brightest sky first" },
] as const;

export type CatalogSort = (typeof CATALOG_SORTS)[number]["value"];

export interface QualityPending {
  frame_ids: number[];
  /** Frames in scope overall (analyzed + pending) — the progress bar's total. */
  total: number;
}

export interface QualityCounts {
  total: number;
  /** Includes unreadable — they were attempted. */
  analyzed: number;
  pending: number;
  unreadable: number;
}

export interface QualityAnalyzeResult {
  analyzed: number;
  no_stars: number;
  unreadable: number;
  skipped: number;
  errors: string[];
}

/** The sub_frame.frame_type CHECK vocabulary (migration 0037). */
export const FRAME_TYPES = [
  "light",
  "dark",
  "flat",
  "bias",
  "dark_flat",
  "unknown",
] as const;
export type FrameTypeName = (typeof FRAME_TYPES)[number];

export type CorrectableField = "frame_type" | "project_target_id";

export interface FrameCorrection {
  frame_type?: FrameTypeName | null;
  project_target_id?: number | null;
  reset_to_auto?: CorrectableField[];
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

/** A row from any of the catalog listings. */
export type CatalogItem = CatalogFrame | CatalogMaster | CatalogOther;

/** Frames-tab rows, and the sub frames mixed into the Others tab, carry
 *  `kind: "sub_frame"`. Use this instead of hand-casting `{ kind?: string }` —
 *  the union's shape is then checked once rather than at every call site. */
export function isSubFrame(item: CatalogItem): item is CatalogFrame {
  return "kind" in item && item.kind === "sub_frame";
}

/** Masters are the only row type the API sends with no `kind` field at all. */
export function isMaster(item: CatalogItem): item is CatalogMaster {
  return !("kind" in item);
}

// ── Folder binding ──────────────────────────────────────────────────────────

export function listFolders(projectId: number): Promise<SourceFolder[]> {
  return apiFetch<SourceFolder[]>(`/projects/${projectId}/folders`);
}

/** Tag a source folder with the rig that shot it (null clears it). Re-tags the
 *  frames already cataloged beneath it — no re-scan needed. */
export function setFolderRig(
  projectId: number,
  folderId: number,
  rigId: number | null,
): Promise<SourceFolder> {
  return apiFetch<SourceFolder>(`/projects/${projectId}/folders/${folderId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rig_id: rigId }),
  });
}

/** Declare which target a source folder holds (null = fall back to the
 *  project's single target). Re-tags already-cataloged lights, no re-scan. */
export function setFolderTarget(
  projectId: number,
  folderId: number,
  targetId: number | null,
): Promise<SourceFolder> {
  return apiFetch<SourceFolder>(`/projects/${projectId}/folders/${folderId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    // Only this field is sent, so it can't clear the rig set separately.
    body: JSON.stringify({ project_target_id: targetId }),
  });
}

export function addFolder(
  projectId: number,
  path: string,
  isPrimary = false,
  rigId: number | null = null,
  targetId: number | null = null,
): Promise<SourceFolder> {
  return apiFetch<SourceFolder>(`/projects/${projectId}/folders`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      path,
      is_primary: isPrimary,
      rig_id: rigId,
      project_target_id: targetId,
    }),
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

/** Manually correct a frame's type / target. */
export function correctFrameClassification(
  projectId: number,
  frameId: number,
  body: FrameCorrection,
): Promise<CatalogFrame> {
  return apiFetch<CatalogFrame>(
    `/projects/${projectId}/catalog/frames/${frameId}/classification`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
}

/** Apply one classification correction to several frames (all-or-nothing). */
export function bulkCorrectFrames(
  projectId: number,
  frameIds: number[],
  body: FrameCorrection,
): Promise<{ updated: number }> {
  return apiFetch<{ updated: number }>(
    `/projects/${projectId}/catalog/frames/bulk-classification`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...body, frame_ids: frameIds }),
    },
  );
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
  sort: CatalogSort | null = null,
): Promise<CatalogFramesPage> {
  const qs = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  if (frameType) qs.set("frame_type", frameType);
  if (filterName) qs.set("filter_name", filterName);
  if (sort) qs.set("sort", sort);
  return apiFetch<CatalogFramesPage>(
    `/projects/${projectId}/catalog/frames?${qs}`,
  );
}

/**
 * Frame ids awaiting quality analysis, in the given scope.
 *
 * The whole ordered list, not a page — the caller batches it locally so progress
 * is exact and there's no re-querying a list that shrinks underneath it.
 */
export function fetchQualityPending(
  projectId: number,
  frameType: string | null = null,
  filterName: string | null = null,
  force = false,
): Promise<QualityPending> {
  const qs = new URLSearchParams();
  if (frameType) qs.set("frame_type", frameType);
  if (filterName) qs.set("filter_name", filterName);
  if (force) qs.set("force", "true");
  return apiFetch<QualityPending>(
    `/projects/${projectId}/catalog/analyze/pending?${qs}`,
  );
}

/**
 * How much of a scope has been analyzed — drives the Analyze button's label.
 * Counts only; pulling the full pending id list just to length it would ship
 * ~20 KB of ints on every tab switch.
 */
export function fetchQualityCounts(
  projectId: number,
  frameType: string | null = null,
  filterName: string | null = null,
): Promise<QualityCounts> {
  const qs = new URLSearchParams();
  if (frameType) qs.set("frame_type", frameType);
  if (filterName) qs.set("filter_name", filterName);
  return apiFetch<QualityCounts>(
    `/projects/${projectId}/catalog/analyze/summary?${qs}`,
  );
}

export interface CatalogDeleteResult {
  sub_frames: number;
  processed_images: number;
  files: number;
}

/**
 * Remove items from the catalog. Files on disk are never touched.
 *
 * NOTE a re-scan of a still-bound source folder will catalog them again — the
 * catalog is a view of what lies under the bound folders and nothing records the
 * removal. Warn before confirming.
 */
export function deleteCatalogItems(
  projectId: number,
  body: {
    sub_frame_ids?: number[];
    processed_image_ids?: number[];
    file_ids?: number[];
  },
): Promise<CatalogDeleteResult> {
  return apiFetch<CatalogDeleteResult>(`/projects/${projectId}/catalog/delete`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

/** Analyze one batch of frames. Returns per-outcome counts. */
export function analyzeFrames(
  projectId: number,
  frameIds: number[],
  force = false,
): Promise<QualityAnalyzeResult> {
  return apiFetch<QualityAnalyzeResult>(
    `/projects/${projectId}/catalog/analyze`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ frame_ids: frameIds, force }),
    },
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
  unclassifiedOnly = false,
): Promise<CatalogOthersPage> {
  const qs = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  if (unclassifiedOnly) qs.set("unclassified_only", "true");
  return apiFetch<CatalogOthersPage>(
    `/projects/${projectId}/catalog/others?${qs}`,
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
