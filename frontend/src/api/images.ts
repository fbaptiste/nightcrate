import { apiFetch } from "./client";

export interface ExtensionInfo {
  index: number;
  name: string;
  type: string;
  has_image: boolean;
  linear?: boolean;
  supports_stretch?: boolean;
}

export interface HeaderCard {
  key: string;
  value: string;
  comment: string;
  description: string | null;
}

export interface StfParams {
  shadow: number;
  midtone: number;
  highlight: number;
}

export interface ChannelStats {
  min: number;
  max: number;
  median: number;
  mad: number;
  avg_dev: number;
  snr: number;
  stf: StfParams;
}

export interface ImageStats {
  color: boolean;
  channels: ChannelStats[];
  linked_stf: StfParams | null;
  background_delta: number[] | null;
  lab_a_median: number | null;
  mid_range_fraction: number;
}

export interface StretchParams {
  stretch: "auto" | "stf" | "linear";
  shadow: number;
  midtone: number;
  highlight: number;
}

export interface RecentFile {
  path: string;
  name: string;
  opened_at: string;
}

export const DEFAULT_STRETCH: StretchParams = {
  stretch: "auto",
  shadow: 0,
  midtone: 0.5,
  highlight: 1.0,
};

export function stfToStretch(stf: StfParams): StretchParams {
  return { ...DEFAULT_STRETCH, stretch: "stf", ...stf };
}

export function isVirtualPath(path: string): boolean {
  return path.includes("::");
}

export type VirtualKind = "plain" | "pxiproject" | "archive";

export interface ParsedPath {
  kind: VirtualKind;
  /** The file or directory before `::` — the archive or the project. */
  container: string;
  /** The part after `::` — an entry path, or the image index for a project. */
  entry: string;
}

/**
 * Classify a path, telling the two `::` conventions apart.
 *
 * `::` means BOTH "image N of a PixInsight project" and "this entry inside this
 * archive", so `isVirtualPath` alone cannot say what a path is — treating every
 * `::` path as a project is what made a `.fit` inside a zip display as "PXI".
 *
 * The test mirrors `services/path_resolver.py` exactly: a pxiproject path ends
 * in an **integer image index**; anything else with a `::` is an archive entry.
 * Matching the backend's own rule rather than sniffing extensions keeps the two
 * from drifting as more archive formats are supported.
 */
export function parsePath(path: string): ParsedPath {
  const i = path.lastIndexOf("::");
  if (i < 0) return { kind: "plain", container: path, entry: "" };
  const container = path.slice(0, i);
  const entry = path.slice(i + 2);
  const isIndex = entry !== "" && /^\d+$/.test(entry);
  return { kind: isIndex ? "pxiproject" : "archive", container, entry };
}

/** Uppercase extension of *name*, or "" — e.g. "…/x.fit" -> "FIT". */
export function extLabel(name: string): string {
  const base = name.slice(name.lastIndexOf("/") + 1);
  const dot = base.lastIndexOf(".");
  return dot > 0 ? base.slice(dot + 1).toUpperCase() : "";
}

const FITS_EXTENSIONS = new Set([".fits", ".fit", ".fts"]);

export function isFitsPath(path: string): boolean {
  const lower = path.toLowerCase();
  return FITS_EXTENSIONS.has(lower.slice(lower.lastIndexOf(".")));
}

export function fetchExtensions(path: string): Promise<ExtensionInfo[]> {
  return apiFetch<ExtensionInfo[]>(`/images/extensions?path=${encodeURIComponent(path)}`);
}

export function fetchHeader(path: string, hdu: number): Promise<HeaderCard[]> {
  return apiFetch<HeaderCard[]>(`/images/header?path=${encodeURIComponent(path)}&hdu=${hdu}`);
}

export function fetchImageStats(path: string, hdu: number): Promise<ImageStats> {
  return apiFetch<ImageStats>(`/images/stats?path=${encodeURIComponent(path)}&hdu=${hdu}`);
}

// ── Pixel inspector ──────────────────────────────────────────────────────────

export interface PixelData {
  x: number;
  y: number;
  color: boolean;
  R?: number;
  G?: number;
  B?: number;
  K: number;
}

export function fetchPixel(path: string, hdu: number, x: number, y: number): Promise<PixelData> {
  return apiFetch<PixelData>(`/images/pixel?path=${encodeURIComponent(path)}&hdu=${hdu}&x=${x}&y=${y}`);
}

// ── Histogram ────────────────────────────────────────────────────────────────

export interface HistogramChannel {
  name: string;
  bins: number[];
}

export interface HistogramData {
  color: boolean;
  channels: HistogramChannel[];
  luminosity: number[] | null;
  bin_edges: number[];
}

export function fetchHistogram(path: string, hdu: number): Promise<HistogramData> {
  return apiFetch<HistogramData>(`/images/histogram?path=${encodeURIComponent(path)}&hdu=${hdu}`);
}

// ── Combined stats + histogram ──────────────────────────────────────────────

export interface StatsAndHistogram {
  stats: ImageStats;
  histogram: HistogramData;
}

export function fetchStatsAndHistogram(path: string, hdu: number): Promise<StatsAndHistogram> {
  return apiFetch<StatsAndHistogram>(
    `/images/stats-histogram?path=${encodeURIComponent(path)}&hdu=${hdu}`,
  );
}

// ── Star + level quality ─────────────────────────────────────────────────────

/**
 * Star-based quality for the loaded image, in the same 16-bit-equivalent ADU
 * scale and with the same frozen detection settings the catalog uses — so these
 * numbers match a cataloged frame's stored values exactly.
 */
export interface ImageQuality {
  /** Median per-star half-flux radius, in PIXELS (comparable only within a rig). */
  hfr: number | null;
  star_count: number | null;
  /** Median per-star SNR — NOT the Statistics panel's median/σ. */
  snr_estimate: number | null;
  median_adu: number | null;
  background_adu: number | null;
  status: "ok" | "no_stars";
}

/**
 * Fetched separately from stats on purpose: detection costs ~0.36 s on a 26 MP
 * frame against ~0.07 s for all of /stats, so the two run in parallel and the
 * star block fills in without holding up the rest of the panel.
 */
export function fetchImageQuality(path: string, hdu: number): Promise<ImageQuality> {
  return apiFetch<ImageQuality>(
    `/images/quality?path=${encodeURIComponent(path)}&hdu=${hdu}`,
  );
}

// ── Image rendering ──────────────────────────────────────────────────────────

export function imageUrl(
  path: string,
  hdu: number,
  linked?: StretchParams,
  perChannel?: [StretchParams, StretchParams, StretchParams],
  activity?: string,
): string {
  const q = new URLSearchParams({ path, hdu: String(hdu) });

  if (linked) {
    q.set("stretch", linked.stretch);
    // For auto stretch, the backend computes params — don't include them in the URL
    // so that slider value updates don't trigger a re-fetch.
    if (linked.stretch !== "auto") {
      q.set("shadow", String(linked.shadow));
      q.set("midtone", String(linked.midtone));
      q.set("highlight", String(linked.highlight));
    }
  }

  if (perChannel && linked?.stretch !== "auto") {
    const [r, g, b] = perChannel;
    q.set("r_shadow", String(r.shadow));
    q.set("r_midtone", String(r.midtone));
    q.set("r_highlight", String(r.highlight));
    q.set("g_shadow", String(g.shadow));
    q.set("g_midtone", String(g.midtone));
    q.set("g_highlight", String(g.highlight));
    q.set("b_shadow", String(b.shadow));
    q.set("b_midtone", String(b.midtone));
    q.set("b_highlight", String(b.highlight));
  }

  if (activity) q.set("_activity", activity);

  return `/api/images/image?${q.toString()}`;
}

export function fetchRecentFiles(): Promise<RecentFile[]> {
  return apiFetch<RecentFile[]>("/images/recent");
}

export function recordRecentFile(path: string): Promise<void> {
  return apiFetch(`/images/recent?path=${encodeURIComponent(path)}`, { method: "POST" });
}

// ── Metadata ────────────────────────────────────────────────────────────────

export interface ImageMetadata {
  canonical: Record<string, string | number | null>;
  unrecognized_keywords: string[];
}

export function fetchMetadata(path: string, hdu: number): Promise<ImageMetadata> {
  return apiFetch<ImageMetadata>(`/images/metadata?path=${encodeURIComponent(path)}&hdu=${hdu}`);
}

// ── Header editing ──────────────────────────────────────────────────────────

export interface HeaderOperation {
  op: "update" | "add" | "delete";
  key: string;
  value?: string;
  comment?: string;
}

export function patchHeader(
  path: string,
  hdu: number,
  operations: HeaderOperation[],
): Promise<HeaderCard[]> {
  return apiFetch<HeaderCard[]>("/images/header", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, hdu, operations }),
  });
}
