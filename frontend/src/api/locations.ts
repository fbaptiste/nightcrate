import { apiFetch } from "./client";

export interface Location {
  id: number;
  name: string;
  latitude: number;
  longitude: number;
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
}

export const fetchLocations = () => apiFetch<Location[]>("/locations");

export const fetchTimezones = () => apiFetch<string[]>("/locations/timezones");

export const fetchGeoTimezone = (latitude: number, longitude: number) =>
  apiFetch<{ geo_timezone: string | null }>(
    `/locations/geo-timezone?latitude=${latitude}&longitude=${longitude}`
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
