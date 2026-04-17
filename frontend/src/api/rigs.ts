import { apiFetch } from "./client";

// ── Types ─────────────────────────────────────────────────────────────────

export interface RigFilterSlotIn {
  slot_number: number;
  filter_id: number;
}

export interface RigFilterSlotOut {
  slot_number: number;
  filter_id: number;
  filter_name: string;
  filter_type_name: string;
  passbands: string[];
}

export interface RigWarning {
  field: string;
  message: string;
  severity?: "error" | "info";
}

export interface SamplingAssessment {
  image_scale: number;
  ideal_range_low: number;
  ideal_range_high: number;
  seeing_fwhm_low: number;
  seeing_fwhm_high: number;
  seeing_source: string;
  seeing_location_name: string | null;
  assessment: string;
  recommendation: string;
  binning_recommendations: Record<number, string>;
}

export interface GuideSuitability {
  mode: "guide_scope" | "oag";
  guide_focal_length_mm: number;
  guide_pixel_size_um: number;
  guide_binning: number;
  effective_guide_pixel_size_um: number;
  unbinned_guide_scale_arcsec_per_pixel: number;
  guide_scale_arcsec_per_pixel: number;
  guide_fov_width_arcmin: number;
  guide_fov_height_arcmin: number;
  centroid_accuracy_pixels: number;
  effective_guide_precision_arcsec: number;
  g_ratio: number;
  effective_error_main_pixels: number;
  rating: "excellent" | "good" | "marginal" | "poor";
  rating_reason: "ratio" | "scale_cap";
  recommendation: string;
  caveat: string;
}

export interface SubExposureResult {
  filter_id: number | null;
  filter_label: string;
  filter_slot_number: number | null;
  effective_bandpass_nm: number;
  filter_transmission_pct: number;
  sky_rate_e_per_s_per_pixel: number;
  optimal_sub_seconds: number;
  saturation_sub_seconds: number;
  recommended_sub_seconds: number;
  saturation_capped: boolean;
  standard_sub_seconds: number;
  has_passband_data: boolean;
}

export interface SubExposureCalc {
  location_id: number | null;
  location_name: string | null;
  sky_mag_per_arcsec2: number;
  sky_brightness_source: "sqm" | "bortle" | "default";
  sky_brightness_source_detail: string;
  read_noise_e: number;
  peak_qe_pct: number;
  full_well_capacity_ke: number;
  aperture_mm: number;
  image_scale_arcsec_per_pixel: number;
  k_factor: number;
  results: SubExposureResult[];
}

export interface RigCalculators {
  image_scale_arcsec_per_pixel: number;
  image_scale_arcsec_per_pixel_binned: Record<number, number>;
  field_of_view_arcmin: [number, number];
  field_of_view_deg: [number, number];
  focal_ratio: number;
  dawes_limit_arcsec: number;
  rayleigh_limit_arcsec: number;
  max_useful_magnification: number;
  sensor_diagonal_mm: number | null;
  image_circle_mm: number | null;
  sensor_coverage_pct: number | null;
  sampling_assessment: SamplingAssessment;
  guide_suitability: GuideSuitability | null;
  sub_exposure: SubExposureCalc | null;
}

export interface Rig {
  id: number;
  name: string;
  description: string | null;
  telescope_configuration_id: number;
  telescope_name: string;
  telescope_config_name: string;
  effective_focal_length_mm: number;
  effective_focal_ratio: number;
  aperture_mm: number;
  camera_id: number;
  camera_name: string;
  pixel_size_um: number;
  sensor_resolution_x: number;
  sensor_resolution_y: number;
  sensor_width_mm: number | null;
  sensor_height_mm: number | null;
  sensor_type: string;
  filter_wheel_id: number | null;
  filter_wheel_name: string | null;
  filter_wheel_positions: number | null;
  single_filter_id: number | null;
  single_filter_name: string | null;
  mount_id: number | null;
  mount_name: string | null;
  focuser_id: number | null;
  focuser_name: string | null;
  oag_id: number | null;
  oag_name: string | null;
  guide_scope_id: number | null;
  guide_scope_name: string | null;
  guide_scope_focal_length_mm: number | null;
  guide_camera_id: number | null;
  guide_camera_name: string | null;
  computer_id: number | null;
  computer_name: string | null;
  software: { id: number; name: string; category: string }[];
  filter_slots: RigFilterSlotOut[];
  is_default: boolean;
  active: boolean;
  notes: string | null;
  created_at: string;
  updated_at: string;
  calculators: RigCalculators;
  warnings: RigWarning[];
}

export interface RigCreate {
  name: string;
  description?: string | null;
  telescope_configuration_id: number;
  camera_id: number;
  filter_wheel_id?: number | null;
  single_filter_id?: number | null;
  mount_id?: number | null;
  focuser_id?: number | null;
  oag_id?: number | null;
  guide_scope_id?: number | null;
  guide_camera_id?: number | null;
  computer_id?: number | null;
  software_ids?: number[];
  is_default?: boolean;
  notes?: string | null;
  filter_slots?: RigFilterSlotIn[];
}

export interface TelescopeConfigOption {
  id: number;
  config_name: string;
  effective_focal_length_mm: number;
  effective_focal_ratio: number;
  effective_image_circle_mm: number | null;
}

export interface TelescopeWithConfigs {
  telescope_id: number;
  telescope_name: string;
  manufacturer_name: string;
  aperture_mm: number;
  is_mine: boolean;
  configs: TelescopeConfigOption[];
}

export interface CameraOption {
  id: number;
  model_name: string;
  manufacturer_name: string;
  pixel_size_um: number;
  resolution_x: number;
  resolution_y: number;
  sensor_width_mm: number | null;
  sensor_height_mm: number | null;
  sensor_type: string;
  is_mine: boolean;
}

export interface FilterWheelOption {
  id: number;
  model_name: string;
  manufacturer_name: string;
  num_positions: number;
  is_mine: boolean;
}

export interface FilterOption {
  id: number;
  model_name: string;
  manufacturer_name: string;
  filter_type_name: string;
  is_mine: boolean;
}

export interface SimpleOption {
  id: number;
  model_name: string;
  manufacturer_name: string;
  is_mine: boolean;
}

export interface GuideScopeOption extends SimpleOption {
  focal_length_mm: number | null;
}

export interface SoftwareOption {
  id: number;
  name: string;
  category: string;
  is_mine: boolean;
}

export interface EquipmentOptions {
  telescopes: TelescopeWithConfigs[];
  cameras: CameraOption[];
  filter_wheels: FilterWheelOption[];
  filters: FilterOption[];
  mounts: SimpleOption[];
  focusers: SimpleOption[];
  oags: SimpleOption[];
  guide_scopes: GuideScopeOption[];
  computers: SimpleOption[];
  software: SoftwareOption[];
}

// ── Fetch Functions ──────────────────────────────────────────────────────

export const fetchRigs = (activeOnly = true) =>
  apiFetch<Rig[]>(`/rigs${activeOnly ? "" : "?active_only=false"}`);

export const fetchRig = (id: number, locationId?: number) =>
  apiFetch<Rig>(`/rigs/${id}${locationId ? `?location_id=${locationId}` : ""}`);

export const createRig = (data: RigCreate) =>
  apiFetch<Rig>("/rigs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

export const updateRig = (id: number, data: Partial<RigCreate>) =>
  apiFetch<Rig>(`/rigs/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

export const deleteRig = (id: number) =>
  apiFetch<void>(`/rigs/${id}`, { method: "DELETE" });

export const restoreRig = (id: number) =>
  apiFetch<Rig>(`/rigs/${id}/restore`, { method: "POST" });

export const cloneRig = (id: number) =>
  apiFetch<Rig>(`/rigs/${id}/clone`, { method: "POST" });

export const fetchRigCalculators = (
  id: number,
  params?: {
    location_id?: number;
    seeing_low?: number;
    seeing_high?: number;
    guide_binning?: number;
    centroid_accuracy_pixels?: number;
    k_factor?: number;
  }
) => {
  const query = new URLSearchParams();
  if (params?.location_id) query.set("location_id", String(params.location_id));
  if (params?.seeing_low) query.set("seeing_low", String(params.seeing_low));
  if (params?.seeing_high) query.set("seeing_high", String(params.seeing_high));
  if (params?.guide_binning !== undefined) {
    query.set("guide_binning", String(params.guide_binning));
  }
  if (params?.centroid_accuracy_pixels !== undefined) {
    query.set("centroid_accuracy_pixels", String(params.centroid_accuracy_pixels));
  }
  if (params?.k_factor !== undefined) {
    query.set("k_factor", String(params.k_factor));
  }
  const qs = query.toString();
  return apiFetch<RigCalculators>(`/rigs/${id}/calculators${qs ? `?${qs}` : ""}`);
};

export const fetchEquipmentOptions = () =>
  apiFetch<EquipmentOptions>("/rigs/equipment-options");
