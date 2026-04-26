import { apiFetch } from "./client";

export interface PlateSolveRequest {
  image_path: string;
  hdu?: number;
  mode?: "auto" | "near" | "blind" | "extract";
  ra_hint?: number;
  dec_hint?: number;
  fov_hint?: number;
  timeout?: number;
}

export interface PlateSolveResult {
  solved: boolean;
  ra_deg: number | null;
  dec_deg: number | null;
  ra_hms: string | null;
  dec_dms: string | null;
  pixel_scale_arcsec: number | null;
  rotation_deg: number | null;
  fov_width_arcmin: number | null;
  fov_height_arcmin: number | null;
  image_width: number | null;
  image_height: number | null;
  cd1_1: number | null;
  cd1_2: number | null;
  cd2_1: number | null;
  cd2_2: number | null;
  crpix1: number | null;
  crpix2: number | null;
  error_message: string | null;
  warning: string | null;
  solve_time_seconds: number | null;
}

export interface AstapValidation {
  valid: boolean;
  resolved_path: string | null;
  error: string | null;
}

export function plateSolve(req: PlateSolveRequest): Promise<PlateSolveResult> {
  return apiFetch<PlateSolveResult>("/plate-solve/solve", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
}

export function fetchSolveProgress(): Promise<{ message: string }> {
  return apiFetch<{ message: string }>("/plate-solve/progress");
}

export function cancelSolve(): Promise<{ cancelled: boolean }> {
  return apiFetch<{ cancelled: boolean }>("/plate-solve/cancel", { method: "POST" });
}

export function validateAstapPath(path: string): Promise<AstapValidation> {
  return apiFetch<AstapValidation>(
    `/plate-solve/validate-path?path=${encodeURIComponent(path)}`,
    { method: "POST" },
  );
}

// ── Image annotation types ──────────────────────────────────────────

export interface WcsParams {
  crval1: number;
  crval2: number;
  cd1_1: number;
  cd1_2: number;
  cd2_1: number;
  cd2_2: number;
  crpix1: number;
  crpix2: number;
  naxis1: number;
  naxis2: number;
}

export interface AnnotatedDso {
  id: number;
  primary_designation: string;
  obj_type: string;
  type_group: string;
  common_name: string | null;
  constellation: string | null;
  ra_deg: number;
  dec_deg: number;
  pixel_x: number;
  pixel_y: number;
  ellipse_semi_major_px: number | null;
  ellipse_semi_minor_px: number | null;
  ellipse_angle_deg: number | null;
  maj_axis_arcmin: number | null;
  min_axis_arcmin: number | null;
  distance_pc: number | null;
  distance_method: string | null;
  mag_b: number | null;
}

export interface ImageAnnotationResult {
  wcs: WcsParams;
  center_ra_deg: number;
  center_dec_deg: number;
  fov_width_arcmin: number;
  fov_height_arcmin: number;
  pixel_scale_arcsec: number;
  rotation_deg: number;
  dsos: AnnotatedDso[];
}

export function detectWcs(path: string, hdu: number = 0): Promise<WcsParams | null> {
  return apiFetch<WcsParams | null>(
    `/plate-solve/detect-wcs?path=${encodeURIComponent(path)}&hdu=${hdu}`,
  );
}

export function fetchAnnotations(
  path: string,
  hdu: number = 0,
  wcsOverride?: Partial<WcsParams>,
): Promise<ImageAnnotationResult> {
  const qs = new URLSearchParams({ path, hdu: String(hdu) });
  if (wcsOverride) {
    for (const [k, v] of Object.entries(wcsOverride)) {
      if (v != null) qs.set(k, String(v));
    }
  }
  return apiFetch<ImageAnnotationResult>(`/plate-solve/annotate?${qs.toString()}`);
}
