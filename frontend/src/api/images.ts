import { apiFetch } from "./client";

export interface ExtensionInfo {
  index: number;
  name: string;
  type: string;
  has_image: boolean;
  linear?: boolean;
}

export interface HeaderCard {
  key: string;
  value: string;
  comment: string;
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
  stf: StfParams;
}

export interface ImageStats {
  color: boolean;
  channels: ChannelStats[];
  linked_stf: StfParams | null;
}

export interface StretchParams {
  stretch: "stf" | "linear";
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
  stretch: "stf",
  shadow: 0,
  midtone: 0.5,
  highlight: 1.0,
};

export function stfToStretch(stf: StfParams): StretchParams {
  return { ...DEFAULT_STRETCH, ...stf };
}

// File type detection
const STRETCH_EXTENSIONS = new Set([".fits", ".fit", ".fts", ".xisf", ".tif", ".tiff"]);

export function isVirtualPath(path: string): boolean {
  return path.includes("::");
}

export function supportsStretch(path: string): boolean {
  if (isVirtualPath(path)) return true;
  const dotIdx = path.lastIndexOf(".");
  if (dotIdx === -1) return false;
  return STRETCH_EXTENSIONS.has(path.slice(dotIdx).toLowerCase());
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

export function imageUrl(
  path: string,
  hdu: number,
  linked?: StretchParams,
  perChannel?: [StretchParams, StretchParams, StretchParams],
): string {
  const q = new URLSearchParams({ path, hdu: String(hdu) });

  if (linked) {
    q.set("stretch", linked.stretch);
    q.set("shadow", String(linked.shadow));
    q.set("midtone", String(linked.midtone));
    q.set("highlight", String(linked.highlight));
  }

  if (perChannel) {
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

  return `/api/images/image?${q.toString()}`;
}

export function fetchRecentFiles(): Promise<RecentFile[]> {
  return apiFetch<RecentFile[]>("/images/recent");
}

export function recordRecentFile(path: string): Promise<void> {
  return apiFetch(`/images/recent?path=${encodeURIComponent(path)}`, { method: "POST" });
}
