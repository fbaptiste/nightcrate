import { apiFetch } from "./client";

// ─── Shared helpers ─────────────────────────────────────────────────────────

function qs(params: Record<string, string | number | boolean | null | undefined>): string {
  const parts: string[] = [];
  for (const [k, v] of Object.entries(params)) {
    if (v === null || v === undefined || v === "") continue;
    parts.push(`${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
  }
  return parts.length ? `?${parts.join("&")}` : "";
}

// ─── Lat / Lon sexagesimal ──────────────────────────────────────────────────

export interface LatLongToSexagesimalResponse {
  latitude_display: string;
  longitude_display: string;
}

export const convertLatLongToSexagesimal = (latitude: number, longitude: number) =>
  apiFetch<LatLongToSexagesimalResponse>(
    `/calculators/lat-long/to-sexagesimal${qs({ latitude, longitude })}`,
  );

export interface LatLongToDecimalRequest {
  /** Free-form input like "33 27 54 N" or "33°27'54\" N". */
  latitude?: string;
  longitude?: string;
  /** Alternative: explicit DMS fields */
  latitude_deg?: number;
  latitude_min?: number;
  latitude_sec?: number;
  latitude_direction?: "N" | "S";
  longitude_deg?: number;
  longitude_min?: number;
  longitude_sec?: number;
  longitude_direction?: "E" | "W";
}

export interface LatLongToDecimalResponse {
  latitude: number | null;
  longitude: number | null;
  latitude_error: string | null;
  longitude_error: string | null;
}

export const convertLatLongToDecimal = (body: LatLongToDecimalRequest) =>
  apiFetch<LatLongToDecimalResponse>("/calculators/lat-long/to-decimal", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

// ─── RA/Dec ↔ Alt/Az ────────────────────────────────────────────────────────

export interface RaDecAltAzRequest {
  direction: "forward" | "reverse";
  /** Required for forward: RA in decimal degrees (0–360). */
  ra_deg?: number;
  /** Required for forward: Dec in decimal degrees (-90 to +90). */
  dec_deg?: number;
  /** Required for reverse: altitude above horizon in degrees. */
  alt_deg?: number;
  /** Required for reverse: azimuth in degrees (0=N, 90=E). */
  az_deg?: number;
  /** ISO-8601 timestamp. If omitted, server uses current UTC. */
  timestamp_iso?: string | null;
  location_id: number;
}

export interface RaDecAltAzResponse {
  ra_deg: number;
  dec_deg: number;
  alt_deg: number;
  az_deg: number;
  airmass: number | null;
  below_horizon: boolean;
}

export const convertRaDecAltAz = (body: RaDecAltAzRequest) =>
  apiFetch<RaDecAltAzResponse>("/calculators/radec-altaz", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

// ─── Sidereal time ──────────────────────────────────────────────────────────

export interface SiderealTimeResponse {
  lst_hours: number;
  lst_hms: string;
  utc_iso: string;
}

export const fetchSiderealTime = (
  locationId: number,
  timestampIso?: string | null,
) =>
  apiFetch<SiderealTimeResponse>(
    `/calculators/sidereal-time${qs({
      location_id: locationId,
      timestamp: timestampIso ?? null,
    })}`,
  );

// ─── Tonight ────────────────────────────────────────────────────────────────

export interface TonightResponse {
  date: string;
  timezone: string;
  sunset: string | null;
  civil_twilight_end: string | null;
  nautical_twilight_end: string | null;
  astronomical_twilight_end: string | null;
  astronomical_twilight_start: string | null;
  nautical_twilight_start: string | null;
  civil_twilight_start: string | null;
  sunrise: string | null;
  moonrise: string | null;
  moonset: string | null;
  moon_illumination_pct: number;
  moon_phase_name: string;
  astronomical_dark_hours: number;
  moonless_dark_hours: number;
}

export const fetchTonight = (locationId: number, date?: string | null) =>
  apiFetch<TonightResponse>(
    `/calculators/tonight${qs({
      location_id: locationId,
      date: date ?? null,
    })}`,
  );

// ─── Angular / Linear unit conversions ──────────────────────────────────────

export type AngularUnit = "rad" | "deg" | "arcmin" | "arcsec" | "mas";

export interface AngularConvertResponse {
  value: number;
  from_unit: AngularUnit;
  to_unit: AngularUnit;
  result: number;
  all_units: Record<AngularUnit, number>;
}

export const convertAngular = (
  value: number,
  fromUnit: AngularUnit,
  toUnit: AngularUnit,
) =>
  apiFetch<AngularConvertResponse>(
    `/calculators/angular-units/convert${qs({
      value,
      from: fromUnit,
      to: toUnit,
    })}`,
  );

export type LinearUnit =
  | "nm"
  | "um"
  | "mm"
  | "cm"
  | "m"
  | "in"
  | "ft"
  | "yd"
  | "km"
  | "mi"
  | "nmi"
  | "au"
  | "ly"
  | "pc"
  | "kpc"
  | "mpc";

export interface LinearConvertResponse {
  value: number;
  from_unit: LinearUnit;
  to_unit: LinearUnit;
  result: number;
  all_units: Record<LinearUnit, number>;
}

export const convertLinear = (
  value: number,
  fromUnit: LinearUnit,
  toUnit: LinearUnit,
) =>
  apiFetch<LinearConvertResponse>(
    `/calculators/linear-units/convert${qs({
      value,
      from: fromUnit,
      to: toUnit,
    })}`,
  );

// ─── Imaging math ───────────────────────────────────────────────────────────

export interface PixelScaleResponse {
  arcsec_per_pixel: number;
  effective_focal_length_mm: number;
}

export const fetchPixelScale = (
  focalLengthMm: number,
  pixelSizeUm: number,
  reducer: number = 1.0,
) =>
  apiFetch<PixelScaleResponse>(
    `/calculators/pixel-scale${qs({
      focal_length_mm: focalLengthMm,
      pixel_size_um: pixelSizeUm,
      reducer,
    })}`,
  );

export interface FovResponse {
  width_deg: number;
  height_deg: number;
  width_arcmin: number;
  height_arcmin: number;
  diagonal_deg: number;
  diagonal_arcmin: number;
}

export interface FovRequest {
  focal_length_mm: number;
  sensor_width_mm?: number;
  sensor_height_mm?: number;
  pixel_count_x?: number;
  pixel_count_y?: number;
  pixel_size_um?: number;
}

export const fetchFov = (req: FovRequest) =>
  apiFetch<FovResponse>(`/calculators/fov${qs({ ...req })}`);

export interface FileSizeResponse {
  bytes_per_frame: number;
  total_bytes: number;
  megapixels: number;
  per_frame_display: string;
  total_display: string;
}

export const fetchFileSize = (
  width: number,
  height: number,
  bitDepth: number = 16,
  frames: number = 1,
  compression: number = 1.0,
) =>
  apiFetch<FileSizeResponse>(
    `/calculators/file-size${qs({
      width,
      height,
      bit_depth: bitDepth,
      frames,
      compression,
    })}`,
  );

export interface AirmassResponse {
  altitude_deg: number;
  airmass: number | null;
  below_horizon: boolean;
  reference_table: Array<{ altitude_deg: number; airmass: number }>;
}

export const fetchAirmass = (altitudeDeg: number) =>
  apiFetch<AirmassResponse>(
    `/calculators/airmass${qs({ altitude_deg: altitudeDeg })}`,
  );

// ─── Sky conditions ─────────────────────────────────────────────────────────

export interface SqmBortleResponse {
  sqm: number | null;
  bortle: number | null;
  nelm: number | null;
  /** Non-fatal note if any input was out of range. */
  note: string | null;
}

export const fetchSqmBortle = (input: {
  sqm?: number | null;
  bortle?: number | null;
  nelm?: number | null;
}) =>
  apiFetch<SqmBortleResponse>(
    `/calculators/sqm-bortle${qs({
      sqm: input.sqm ?? null,
      bortle: input.bortle ?? null,
      nelm: input.nelm ?? null,
    })}`,
  );

export type TemperatureUnit = "C" | "F" | "K";

export interface TemperatureResponse {
  celsius: number;
  fahrenheit: number;
  kelvin: number;
}

export const fetchTemperature = (value: number, fromUnit: TemperatureUnit) =>
  apiFetch<TemperatureResponse>(
    `/calculators/temperature${qs({ value, from: fromUnit })}`,
  );
