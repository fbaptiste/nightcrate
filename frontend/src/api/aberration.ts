import { apiFetch, getActivity } from "./client";

export interface StarMeasurement {
  x: number;
  y: number;
  fwhm: number;
  hfr: number;
  eccentricity: number;
  elongation_angle_deg: number;
  peak_adu: number;
  flux: number;
  snr: number;
  semi_major: number;
  semi_minor: number;
  flag: number;
}

export interface AnalysisResult {
  stars: StarMeasurement[];
  star_count: number;
  image_width: number;
  image_height: number;
  median_fwhm: number | null;
  median_hfr: number | null;
  median_eccentricity: number | null;
}

export interface SampleSquare {
  row: number;
  col: number;
  x0: number;
  y0: number;
  x1: number;
  y1: number;
  star_count: number;
  star_indices: number[];
  median_fwhm: number | null;
  mean_fwhm: number | null;
  std_fwhm: number | null;
  median_eccentricity: number | null;
  median_hfr: number | null;
  median_elongation_angle: number | null;
}

export interface SampleGridResult {
  samples_across: number;
  rows: number;
  cols: number;
  square_size: number;
  squares: SampleSquare[];
}

export type AberrationMetric = "eccentricity" | "fwhm" | "hfr" | "peak_adu" | "elongation_angle";

export interface StarFilters {
  minSnr: number;
  minFwhm: number;
  maxFwhm: number;
}

export const DEFAULT_STAR_FILTERS: StarFilters = {
  minSnr: 10,
  minFwhm: 3,
  maxFwhm: 30,
};

function filterParams(f: StarFilters): string {
  return `&min_snr=${f.minSnr}&min_fwhm=${f.minFwhm}&max_fwhm=${f.maxFwhm}`;
}

export function analyzeFrame(path: string, hdu: number, filters: StarFilters): Promise<AnalysisResult> {
  return apiFetch<AnalysisResult>(
    `/aberration/analyze?path=${encodeURIComponent(path)}&hdu=${hdu}${filterParams(filters)}`,
    { method: "POST" },
  );
}

export function fetchSamples(
  path: string,
  hdu: number,
  samplesAcross: number,
  filters: StarFilters,
): Promise<SampleGridResult> {
  return apiFetch<SampleGridResult>(
    `/aberration/samples?path=${encodeURIComponent(path)}&hdu=${hdu}&samples_across=${samplesAcross}${filterParams(filters)}`,
    { method: "POST" },
  );
}

export function regionCropUrl(path: string, hdu: number, x0: number, y0: number, x1: number, y1: number): string {
  const q = new URLSearchParams({
    path, hdu: String(hdu),
    x0: String(x0), y0: String(y0), x1: String(x1), y1: String(y1),
  });
  const activity = getActivity();
  if (activity) q.set("_activity", activity);
  return `/api/aberration/crop?${q.toString()}`;
}

/** Re-aggregate stars into a square after it has been repositioned (client-side). */
export function reaggregateSquare(
  sq: SampleSquare,
  allStars: StarMeasurement[],
): SampleSquare {
  const indices: number[] = [];
  for (let i = 0; i < allStars.length; i++) {
    const s = allStars[i];
    if (s.x >= sq.x0 && s.x < sq.x1 && s.y >= sq.y0 && s.y < sq.y1) {
      indices.push(i);
    }
  }
  if (indices.length === 0) {
    return { ...sq, star_count: 0, star_indices: [], median_fwhm: null, mean_fwhm: null, std_fwhm: null, median_eccentricity: null, median_hfr: null, median_elongation_angle: null };
  }
  const stars = indices.map((i) => allStars[i]);
  const sorted = (arr: number[]) => [...arr].sort((a, b) => a - b);
  const median = (arr: number[]) => {
    const s = sorted(arr);
    const mid = Math.floor(s.length / 2);
    return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
  };
  const mean = (arr: number[]) => arr.reduce((a, b) => a + b, 0) / arr.length;
  const std = (arr: number[]) => {
    const m = mean(arr);
    return Math.sqrt(arr.reduce((s, v) => s + (v - m) ** 2, 0) / arr.length);
  };
  const fwhms = stars.map((s) => s.fwhm);
  const eccs = stars.map((s) => s.eccentricity);
  const hfrs = stars.map((s) => s.hfr);
  const angles = stars.map((s) => s.elongation_angle_deg);
  return {
    ...sq,
    star_count: indices.length,
    star_indices: indices,
    median_fwhm: +median(fwhms).toFixed(3),
    mean_fwhm: +mean(fwhms).toFixed(3),
    std_fwhm: fwhms.length > 1 ? +std(fwhms).toFixed(3) : 0,
    median_eccentricity: +median(eccs).toFixed(4),
    median_hfr: +median(hfrs).toFixed(3),
    median_elongation_angle: +median(angles).toFixed(1),
  };
}

export interface CacheSize {
  bytes: number;
}

export function fetchCacheSize(): Promise<CacheSize> {
  return apiFetch<CacheSize>("/aberration/cache/size");
}

export function clearCache(): Promise<{ status: string }> {
  return apiFetch("/aberration/cache", { method: "DELETE" });
}
