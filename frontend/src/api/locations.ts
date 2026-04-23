import { apiFetch } from "./client";

export interface Location {
  id: number;
  name: string;
  latitude: number;
  longitude: number;
  latitude_display: string;
  longitude_display: string;
  elevation_m: number | null;
  timezone: string;
  geo_timezone: string | null;
  bortle_class: number | null;
  sqm_reading: number | null;
  city: string | null;
  state_province: string | null;
  country: string | null;
  postal_code: string | null;
  typical_seeing_low_arcsec: number | null;
  typical_seeing_high_arcsec: number | null;
  is_default: boolean;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface LocationCreate {
  name: string;
  latitude: number;
  longitude: number;
  elevation_m?: number | null;
  timezone: string;
  geo_timezone?: string | null;
  bortle_class?: number | null;
  sqm_reading?: number | null;
  city?: string | null;
  state_province?: string | null;
  country?: string | null;
  postal_code?: string | null;
  typical_seeing_low_arcsec?: number | null;
  typical_seeing_high_arcsec?: number | null;
  is_default?: boolean;
  notes?: string | null;
  /** Optional: when provided (non-empty) the server creates the
   *  location + all listed horizons in one transaction and skips the
   *  usual 0° default auto-seed. Exactly one entry must be
   *  ``is_default=true``; at most one may be ``type='custom'``. When
   *  omitted, legacy auto-seed behavior applies. Used by the Location
   *  editor dialog's staged-save flow for new locations. */
  horizons?: LocationCreateHorizonSeed[];
}

export interface LocationCreateHorizonPoint {
  azimuth_deg: number;
  altitude_deg: number;
}

export interface LocationCreateHorizonSeed {
  name: string;
  type: "artificial" | "custom";
  flat_altitude_deg?: number | null;
  points?: LocationCreateHorizonPoint[];
  source?: "drawn" | "imported" | null;
  source_filename?: string | null;
  notes?: string | null;
  is_default: boolean;
}

export const fetchLocations = () => apiFetch<Location[]>("/locations");

export const fetchTimezones = () => apiFetch<string[]>("/locations/timezones");

export const fetchGeoTimezone = (latitude: number, longitude: number) =>
  apiFetch<{ geo_timezone: string | null }>(
    `/locations/geo-timezone?latitude=${latitude}&longitude=${longitude}`
  );

export interface ClearOutsideLookup {
  sqm: number | null;
  bortle: number | null;
  source_url: string;
}

export const lookupClearOutside = (latitude: number, longitude: number) =>
  apiFetch<ClearOutsideLookup>(
    `/locations/clear-outside?latitude=${latitude}&longitude=${longitude}`
  );

export const fetchLocation = (id: number) =>
  apiFetch<Location>(`/locations/${id}`);

export const fetchDefaultLocation = () =>
  apiFetch<Location | null>("/locations/default");

export const createLocation = (data: LocationCreate) =>
  apiFetch<Location>("/locations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

export const updateLocation = (id: number, data: Partial<LocationCreate>) =>
  apiFetch<Location>(`/locations/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

export const setDefaultLocation = (id: number) =>
  apiFetch<Location>(`/locations/${id}/set-default`, { method: "POST" });

export const deleteLocation = (id: number) =>
  apiFetch<{ ok: boolean }>(`/locations/${id}`, { method: "DELETE" });
