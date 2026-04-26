import { apiFetch } from "./client";

export interface PlateSolveRequest {
  image_path: string;
  hdu?: number;
  mode?: "auto" | "near" | "blind";
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

export function validateAstapPath(path: string): Promise<AstapValidation> {
  return apiFetch<AstapValidation>(
    `/plate-solve/validate-path?path=${encodeURIComponent(path)}`,
    { method: "POST" },
  );
}
