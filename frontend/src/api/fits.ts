import { apiFetch } from "./client";

export interface HduInfo {
  index: number;
  name: string;
  type: string;
  has_image: boolean;
}

export interface HeaderCard {
  key: string;
  value: string;
  comment: string;
}

export interface StfParams {
  shadow: number;     // 0–1
  midtone: number;    // 0–1
  highlight: number;  // 0–1
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
  channels: ChannelStats[];    // 1 for mono, 3 (R/G/B) for color
  linked_stf: StfParams | null; // for color: STF from dimmest channel
}

export interface StretchParams {
  stretch: "stf" | "linear";
  // STF
  shadow: number;
  midtone: number;
  highlight: number;
}

export const DEFAULT_STRETCH: StretchParams = {
  stretch: "stf",
  shadow: 0,
  midtone: 0.5,
  highlight: 1.0,
};

/** Build a StretchParams from auto-computed STF values. */
export function stfToStretch(stf: StfParams): StretchParams {
  return { ...DEFAULT_STRETCH, ...stf };
}

export function fetchHdus(path: string): Promise<HduInfo[]> {
  return apiFetch<HduInfo[]>(`/fits/hdus?path=${encodeURIComponent(path)}`);
}

export function fetchHeader(path: string, hdu: number): Promise<HeaderCard[]> {
  return apiFetch<HeaderCard[]>(`/fits/header?path=${encodeURIComponent(path)}&hdu=${hdu}`);
}

export function fetchImageStats(path: string, hdu: number): Promise<ImageStats> {
  return apiFetch<ImageStats>(`/fits/stats?path=${encodeURIComponent(path)}&hdu=${hdu}`);
}

export function fitsImageUrl(
  path: string,
  hdu: number,
  linked: StretchParams,
  perChannel?: [StretchParams, StretchParams, StretchParams],
): string {
  const q = new URLSearchParams({
    path,
    hdu: String(hdu),
    stretch: linked.stretch,
    shadow: String(linked.shadow),
    midtone: String(linked.midtone),
    highlight: String(linked.highlight),
  });

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

  return `/api/fits/image?${q.toString()}`;
}
