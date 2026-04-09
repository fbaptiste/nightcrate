import { apiFetch } from "./client";

// ---------------------------------------------------------------------------
// Lookup table interfaces
// ---------------------------------------------------------------------------

export interface Manufacturer {
  id: number;
  name: string;
  website: string | null;
  notes: string | null;
  active: boolean;
  created_at: string;
  updated_at: string;
}

export interface OpticalDesign {
  id: number;
  name: string;
  description: string | null;
  active: boolean;
  created_at: string;
  updated_at: string;
}

export interface MountType {
  id: number;
  name: string;
  description: string | null;
  active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ConnectionInterface {
  id: number;
  name: string;
  category: string;
  notes: string | null;
  active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ConnectorSize {
  id: number;
  name: string;
  diameter_mm: number | null;
  notes: string | null;
  active: boolean;
  created_at: string;
  updated_at: string;
}

export interface FilterSize {
  id: number;
  name: string;
  description: string | null;
  active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ComputerType {
  id: number;
  name: string;
  description: string | null;
  active: boolean;
  created_at: string;
  updated_at: string;
}

export interface FilterType {
  id: number;
  name: string;
  display_name: string;
  description: string | null;
  active: boolean;
  created_at: string;
  updated_at: string;
}

// ---------------------------------------------------------------------------
// Equipment interfaces
// ---------------------------------------------------------------------------

export interface Sensor {
  id: number;
  manufacturer: Manufacturer;
  model_name: string;
  sensor_type: "mono" | "color";
  pixel_size_um: number;
  resolution_x: number;
  resolution_y: number;
  sensor_width_mm: number | null;
  sensor_height_mm: number | null;
  adc_bit_depth: number | null;
  full_well_capacity_ke: number | null;
  read_noise_e: number | null;
  peak_qe_pct: number | null;
  bayer_pattern: string | null;
  dual_gain: boolean;
  hcg_threshold_gain: number | null;
  notes: string | null;
  active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Camera {
  id: number;
  manufacturer: Manufacturer;
  sensor: Sensor;
  guide_sensor: Sensor | null;
  connector_size: ConnectorSize | null;
  model_name: string;
  cooled: boolean;
  cooling_delta_c: number | null;
  back_focus_mm: number | null;
  weight_g: number | null;
  tilt_adapter: boolean;
  has_usb_hub: boolean;
  usb_hub_interface: ConnectionInterface | null;
  unity_gain: number | null;
  notes: string | null;
  interfaces: ConnectionInterface[];
  active: boolean;
  created_at: string;
  updated_at: string;
}

export interface TelescopeConfiguration {
  id: number;
  telescope_id: number;
  config_name: string;
  accessory_name: string | null;
  reduction_factor: number | null;
  effective_focal_length_mm: number;
  effective_focal_ratio: number;
  effective_image_circle_mm: number | null;
  effective_back_focus_mm: number | null;
  is_native: boolean;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface Telescope {
  id: number;
  manufacturer: Manufacturer;
  optical_design: OpticalDesign | null;
  model_name: string;
  aperture_mm: number;
  image_circle_mm: number | null;
  weight_kg: number | null;
  obstruction_pct: number | null;
  notes: string | null;
  connectors: ConnectorSize[];
  configurations: TelescopeConfiguration[];
  active: boolean;
  created_at: string;
  updated_at: string;
}

export interface FilterPassband {
  id: number;
  filter_id: number;
  line_name: string | null;
  central_wavelength_nm: number;
  bandwidth_nm: number | null;
  peak_transmission_pct: number | null;
}

export interface Filter {
  id: number;
  manufacturer: Manufacturer;
  filter_type: FilterType;
  filter_size: FilterSize | null;
  model_name: string;
  peak_transmission_pct: number | null;
  mounted_thickness_mm: number | null;
  notes: string | null;
  passbands: FilterPassband[];
  active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Mount {
  id: number;
  manufacturer: Manufacturer;
  mount_type: MountType | null;
  model_name: string;
  payload_capacity_kg: number | null;
  mount_weight_kg: number | null;
  counterweight_required: boolean;
  goto_capable: boolean;
  periodic_error_arcsec: number | null;
  drive_type: string | null;
  notes: string | null;
  interfaces: ConnectionInterface[];
  active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Focuser {
  id: number;
  manufacturer: Manufacturer;
  model_name: string;
  motorized: boolean;
  travel_range_mm: number | null;
  step_size_um: number | null;
  total_steps: number | null;
  temperature_compensation: boolean;
  backlash_steps: number | null;
  notes: string | null;
  interfaces: ConnectionInterface[];
  active: boolean;
  created_at: string;
  updated_at: string;
}

export interface FilterWheel {
  id: number;
  manufacturer: Manufacturer;
  filter_size: FilterSize | null;
  camera_side_connector: ConnectorSize | null;
  telescope_side_connector: ConnectorSize | null;
  model_name: string;
  num_positions: number;
  back_focus_contribution_mm: number | null;
  notes: string | null;
  interfaces: ConnectionInterface[];
  active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Oag {
  id: number;
  manufacturer: Manufacturer;
  imaging_side_connector: ConnectorSize | null;
  guide_camera_connector: ConnectorSize | null;
  model_name: string;
  prism_size_mm: number | null;
  back_focus_contribution_mm: number | null;
  weight_g: number | null;
  notes: string | null;
  active: boolean;
  created_at: string;
  updated_at: string;
}

export interface GuideScope {
  id: number;
  manufacturer: Manufacturer;
  guide_camera_connector: ConnectorSize | null;
  model_name: string;
  aperture_mm: number | null;
  focal_length_mm: number | null;
  weight_g: number | null;
  notes: string | null;
  active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Computer {
  id: number;
  manufacturer: Manufacturer;
  computer_type: ComputerType | null;
  model_name: string;
  notes: string | null;
  active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Software {
  id: number;
  manufacturer: Manufacturer | null;
  name: string;
  category: string;
  website: string | null;
  notes: string | null;
  active: boolean;
  created_at: string;
  updated_at: string;
}

// ---------------------------------------------------------------------------
// Create interfaces (for form submissions)
// ---------------------------------------------------------------------------

export interface ManufacturerCreate {
  name: string;
  website?: string | null;
  notes?: string | null;
}

export interface OpticalDesignCreate {
  name: string;
  description?: string | null;
}

export interface MountTypeCreate {
  name: string;
  description?: string | null;
}

export interface ConnectionInterfaceCreate {
  name: string;
  category: string;
  notes?: string | null;
}

export interface ConnectorSizeCreate {
  name: string;
  diameter_mm?: number | null;
  notes?: string | null;
}

export interface FilterSizeCreate {
  name: string;
  description?: string | null;
}

export interface ComputerTypeCreate {
  name: string;
  description?: string | null;
}

export interface SensorCreate {
  manufacturer_id: number;
  model_name: string;
  sensor_type: "mono" | "color";
  pixel_size_um: number;
  resolution_x: number;
  resolution_y: number;
  sensor_width_mm?: number | null;
  sensor_height_mm?: number | null;
  adc_bit_depth?: number | null;
  full_well_capacity_ke?: number | null;
  read_noise_e?: number | null;
  peak_qe_pct?: number | null;
  bayer_pattern?: string | null;
  dual_gain?: boolean;
  hcg_threshold_gain?: number | null;
  notes?: string | null;
}

export interface CameraCreate {
  manufacturer_id: number;
  sensor_id: number;
  guide_sensor_id?: number | null;
  connector_size_id?: number | null;
  model_name: string;
  cooled?: boolean;
  cooling_delta_c?: number | null;
  back_focus_mm?: number | null;
  weight_g?: number | null;
  tilt_adapter?: boolean;
  has_usb_hub?: boolean;
  usb_hub_interface_id?: number | null;
  unity_gain?: number | null;
  notes?: string | null;
  interface_ids?: number[];
}

export interface TelescopeConfigurationCreate {
  telescope_id: number;
  config_name: string;
  accessory_name?: string | null;
  reduction_factor?: number | null;
  effective_focal_length_mm: number;
  effective_focal_ratio: number;
  effective_image_circle_mm?: number | null;
  effective_back_focus_mm?: number | null;
  is_native?: boolean;
  notes?: string | null;
}

export interface TelescopeCreate {
  manufacturer_id: number;
  optical_design_id?: number | null;
  model_name: string;
  aperture_mm: number;
  image_circle_mm?: number | null;
  weight_kg?: number | null;
  obstruction_pct?: number | null;
  notes?: string | null;
  connector_size_ids?: number[];
}

export interface FilterPassbandCreate {
  filter_id: number;
  line_name?: string | null;
  central_wavelength_nm: number;
  bandwidth_nm?: number | null;
  peak_transmission_pct?: number | null;
}

export interface FilterCreate {
  manufacturer_id: number;
  filter_type_id: number;
  filter_size_id?: number | null;
  model_name: string;
  peak_transmission_pct?: number | null;
  mounted_thickness_mm?: number | null;
  notes?: string | null;
}

export interface MountCreate {
  manufacturer_id: number;
  mount_type_id?: number | null;
  model_name: string;
  payload_capacity_kg?: number | null;
  mount_weight_kg?: number | null;
  counterweight_required?: boolean;
  goto_capable?: boolean;
  periodic_error_arcsec?: number | null;
  drive_type?: string | null;
  notes?: string | null;
  interface_ids?: number[];
}

export interface FocuserCreate {
  manufacturer_id: number;
  model_name: string;
  motorized?: boolean;
  travel_range_mm?: number | null;
  step_size_um?: number | null;
  total_steps?: number | null;
  temperature_compensation?: boolean;
  backlash_steps?: number | null;
  notes?: string | null;
  interface_ids?: number[];
}

export interface FilterWheelCreate {
  manufacturer_id: number;
  filter_size_id?: number | null;
  camera_side_connector_id?: number | null;
  telescope_side_connector_id?: number | null;
  model_name: string;
  num_positions: number;
  back_focus_contribution_mm?: number | null;
  notes?: string | null;
  interface_ids?: number[];
}

export interface OagCreate {
  manufacturer_id: number;
  imaging_side_connector_id?: number | null;
  guide_camera_connector_id?: number | null;
  model_name: string;
  prism_size_mm?: number | null;
  back_focus_contribution_mm?: number | null;
  weight_g?: number | null;
  notes?: string | null;
}

export interface GuideScopeCreate {
  manufacturer_id: number;
  guide_camera_connector_id?: number | null;
  model_name: string;
  aperture_mm?: number | null;
  focal_length_mm?: number | null;
  weight_g?: number | null;
  notes?: string | null;
}

export interface ComputerCreate {
  manufacturer_id: number;
  computer_type_id?: number | null;
  model_name: string;
  notes?: string | null;
}

export interface SoftwareCreate {
  manufacturer_id?: number | null;
  name: string;
  category: string;
  website?: string | null;
  notes?: string | null;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const JSON_HEADERS = { "Content-Type": "application/json" };

function retiredParam(includeRetired: boolean): string {
  return includeRetired ? "?include_retired=true" : "";
}

// ---------------------------------------------------------------------------
// Manufacturer
// ---------------------------------------------------------------------------

export const fetchManufacturers = (includeRetired = false) =>
  apiFetch<Manufacturer[]>(`/equipment/manufacturer${retiredParam(includeRetired)}`);

export const fetchManufacturer = (id: number) =>
  apiFetch<Manufacturer>(`/equipment/manufacturer/${id}`);

export const createManufacturer = (data: ManufacturerCreate) =>
  apiFetch<Manufacturer>("/equipment/manufacturer", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(data),
  });

export const updateManufacturer = (id: number, data: Partial<ManufacturerCreate>) =>
  apiFetch<Manufacturer>(`/equipment/manufacturer/${id}`, {
    method: "PUT",
    headers: JSON_HEADERS,
    body: JSON.stringify(data),
  });

export const deleteManufacturer = (id: number) =>
  apiFetch<{ ok: boolean }>(`/equipment/manufacturer/${id}`, { method: "DELETE" });

// ---------------------------------------------------------------------------
// Optical Design
// ---------------------------------------------------------------------------

export const fetchOpticalDesigns = (includeRetired = false) =>
  apiFetch<OpticalDesign[]>(`/equipment/optical-design${retiredParam(includeRetired)}`);

export const fetchOpticalDesign = (id: number) =>
  apiFetch<OpticalDesign>(`/equipment/optical-design/${id}`);

export const createOpticalDesign = (data: OpticalDesignCreate) =>
  apiFetch<OpticalDesign>("/equipment/optical-design", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(data),
  });

export const updateOpticalDesign = (id: number, data: Partial<OpticalDesignCreate>) =>
  apiFetch<OpticalDesign>(`/equipment/optical-design/${id}`, {
    method: "PUT",
    headers: JSON_HEADERS,
    body: JSON.stringify(data),
  });

export const deleteOpticalDesign = (id: number) =>
  apiFetch<{ ok: boolean }>(`/equipment/optical-design/${id}`, { method: "DELETE" });

// ---------------------------------------------------------------------------
// Mount Type
// ---------------------------------------------------------------------------

export const fetchMountTypes = (includeRetired = false) =>
  apiFetch<MountType[]>(`/equipment/mount-type${retiredParam(includeRetired)}`);

export const fetchMountType = (id: number) =>
  apiFetch<MountType>(`/equipment/mount-type/${id}`);

export const createMountType = (data: MountTypeCreate) =>
  apiFetch<MountType>("/equipment/mount-type", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(data),
  });

export const updateMountType = (id: number, data: Partial<MountTypeCreate>) =>
  apiFetch<MountType>(`/equipment/mount-type/${id}`, {
    method: "PUT",
    headers: JSON_HEADERS,
    body: JSON.stringify(data),
  });

export const deleteMountType = (id: number) =>
  apiFetch<{ ok: boolean }>(`/equipment/mount-type/${id}`, { method: "DELETE" });

// ---------------------------------------------------------------------------
// Connection Interface
// ---------------------------------------------------------------------------

export const fetchConnectionInterfaces = (includeRetired = false) =>
  apiFetch<ConnectionInterface[]>(`/equipment/connection-interface${retiredParam(includeRetired)}`);

export const fetchConnectionInterface = (id: number) =>
  apiFetch<ConnectionInterface>(`/equipment/connection-interface/${id}`);

export const createConnectionInterface = (data: ConnectionInterfaceCreate) =>
  apiFetch<ConnectionInterface>("/equipment/connection-interface", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(data),
  });

export const updateConnectionInterface = (id: number, data: Partial<ConnectionInterfaceCreate>) =>
  apiFetch<ConnectionInterface>(`/equipment/connection-interface/${id}`, {
    method: "PUT",
    headers: JSON_HEADERS,
    body: JSON.stringify(data),
  });

export const deleteConnectionInterface = (id: number) =>
  apiFetch<{ ok: boolean }>(`/equipment/connection-interface/${id}`, { method: "DELETE" });

// ---------------------------------------------------------------------------
// Connector Size
// ---------------------------------------------------------------------------

export const fetchConnectorSizes = (includeRetired = false) =>
  apiFetch<ConnectorSize[]>(`/equipment/connector-size${retiredParam(includeRetired)}`);

export const fetchConnectorSize = (id: number) =>
  apiFetch<ConnectorSize>(`/equipment/connector-size/${id}`);

export const createConnectorSize = (data: ConnectorSizeCreate) =>
  apiFetch<ConnectorSize>("/equipment/connector-size", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(data),
  });

export const updateConnectorSize = (id: number, data: Partial<ConnectorSizeCreate>) =>
  apiFetch<ConnectorSize>(`/equipment/connector-size/${id}`, {
    method: "PUT",
    headers: JSON_HEADERS,
    body: JSON.stringify(data),
  });

export const deleteConnectorSize = (id: number) =>
  apiFetch<{ ok: boolean }>(`/equipment/connector-size/${id}`, { method: "DELETE" });

// ---------------------------------------------------------------------------
// Filter Size
// ---------------------------------------------------------------------------

export const fetchFilterSizes = (includeRetired = false) =>
  apiFetch<FilterSize[]>(`/equipment/filter-size${retiredParam(includeRetired)}`);

export const fetchFilterSize = (id: number) =>
  apiFetch<FilterSize>(`/equipment/filter-size/${id}`);

export const createFilterSize = (data: FilterSizeCreate) =>
  apiFetch<FilterSize>("/equipment/filter-size", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(data),
  });

export const updateFilterSize = (id: number, data: Partial<FilterSizeCreate>) =>
  apiFetch<FilterSize>(`/equipment/filter-size/${id}`, {
    method: "PUT",
    headers: JSON_HEADERS,
    body: JSON.stringify(data),
  });

export const deleteFilterSize = (id: number) =>
  apiFetch<{ ok: boolean }>(`/equipment/filter-size/${id}`, { method: "DELETE" });

// ---------------------------------------------------------------------------
// Computer Type
// ---------------------------------------------------------------------------

export const fetchComputerTypes = (includeRetired = false) =>
  apiFetch<ComputerType[]>(`/equipment/computer-type${retiredParam(includeRetired)}`);

export const fetchComputerType = (id: number) =>
  apiFetch<ComputerType>(`/equipment/computer-type/${id}`);

export const createComputerType = (data: ComputerTypeCreate) =>
  apiFetch<ComputerType>("/equipment/computer-type", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(data),
  });

export const updateComputerType = (id: number, data: Partial<ComputerTypeCreate>) =>
  apiFetch<ComputerType>(`/equipment/computer-type/${id}`, {
    method: "PUT",
    headers: JSON_HEADERS,
    body: JSON.stringify(data),
  });

export const deleteComputerType = (id: number) =>
  apiFetch<{ ok: boolean }>(`/equipment/computer-type/${id}`, { method: "DELETE" });

// ---------------------------------------------------------------------------
// Filter Type (read-only)
// ---------------------------------------------------------------------------

export const fetchFilterTypes = (includeRetired = false) =>
  apiFetch<FilterType[]>(`/equipment/filter-type${retiredParam(includeRetired)}`);

export const fetchFilterType = (id: number) =>
  apiFetch<FilterType>(`/equipment/filter-type/${id}`);

// ---------------------------------------------------------------------------
// Sensor
// ---------------------------------------------------------------------------

export const fetchSensors = (includeRetired = false) =>
  apiFetch<Sensor[]>(`/equipment/sensor${retiredParam(includeRetired)}`);

export const fetchSensor = (id: number) =>
  apiFetch<Sensor>(`/equipment/sensor/${id}`);

export const createSensor = (data: SensorCreate) =>
  apiFetch<Sensor>("/equipment/sensor", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(data),
  });

export const updateSensor = (id: number, data: Partial<SensorCreate>) =>
  apiFetch<Sensor>(`/equipment/sensor/${id}`, {
    method: "PUT",
    headers: JSON_HEADERS,
    body: JSON.stringify(data),
  });

export const deleteSensor = (id: number) =>
  apiFetch<{ ok: boolean }>(`/equipment/sensor/${id}`, { method: "DELETE" });

// ---------------------------------------------------------------------------
// Camera
// ---------------------------------------------------------------------------

export const fetchCameras = (includeRetired = false) =>
  apiFetch<Camera[]>(`/equipment/camera${retiredParam(includeRetired)}`);

export const fetchCamera = (id: number) =>
  apiFetch<Camera>(`/equipment/camera/${id}`);

export const createCamera = (data: CameraCreate) =>
  apiFetch<Camera>("/equipment/camera", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(data),
  });

export const updateCamera = (id: number, data: Partial<CameraCreate>) =>
  apiFetch<Camera>(`/equipment/camera/${id}`, {
    method: "PUT",
    headers: JSON_HEADERS,
    body: JSON.stringify(data),
  });

export const deleteCamera = (id: number) =>
  apiFetch<{ ok: boolean }>(`/equipment/camera/${id}`, { method: "DELETE" });

// ---------------------------------------------------------------------------
// Telescope
// ---------------------------------------------------------------------------

export const fetchTelescopes = (includeRetired = false) =>
  apiFetch<Telescope[]>(`/equipment/telescope${retiredParam(includeRetired)}`);

export const fetchTelescope = (id: number) =>
  apiFetch<Telescope>(`/equipment/telescope/${id}`);

export const createTelescope = (data: TelescopeCreate) =>
  apiFetch<Telescope>("/equipment/telescope", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(data),
  });

export const updateTelescope = (id: number, data: Partial<TelescopeCreate>) =>
  apiFetch<Telescope>(`/equipment/telescope/${id}`, {
    method: "PUT",
    headers: JSON_HEADERS,
    body: JSON.stringify(data),
  });

export const deleteTelescope = (id: number) =>
  apiFetch<{ ok: boolean }>(`/equipment/telescope/${id}`, { method: "DELETE" });

export const createTelescopeConfig = (telescopeId: number, data: TelescopeConfigurationCreate) =>
  apiFetch<TelescopeConfiguration>(`/equipment/telescope/${telescopeId}/configuration`, {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(data),
  });

export const updateTelescopeConfig = (
  telescopeId: number,
  configId: number,
  data: Partial<TelescopeConfigurationCreate>,
) =>
  apiFetch<TelescopeConfiguration>(
    `/equipment/telescope/${telescopeId}/configuration/${configId}`,
    {
      method: "PUT",
      headers: JSON_HEADERS,
      body: JSON.stringify(data),
    },
  );

export const deleteTelescopeConfig = (telescopeId: number, configId: number) =>
  apiFetch<{ ok: boolean }>(
    `/equipment/telescope/${telescopeId}/configuration/${configId}`,
    { method: "DELETE" },
  );

// ---------------------------------------------------------------------------
// Filter
// ---------------------------------------------------------------------------

export const fetchFilters = (includeRetired = false) =>
  apiFetch<Filter[]>(`/equipment/filter${retiredParam(includeRetired)}`);

export const fetchFilter = (id: number) =>
  apiFetch<Filter>(`/equipment/filter/${id}`);

export const createFilter = (data: FilterCreate) =>
  apiFetch<Filter>("/equipment/filter", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(data),
  });

export const updateFilter = (id: number, data: Partial<FilterCreate>) =>
  apiFetch<Filter>(`/equipment/filter/${id}`, {
    method: "PUT",
    headers: JSON_HEADERS,
    body: JSON.stringify(data),
  });

export const deleteFilter = (id: number) =>
  apiFetch<{ ok: boolean }>(`/equipment/filter/${id}`, { method: "DELETE" });

export const createFilterPassband = (filterId: number, data: FilterPassbandCreate) =>
  apiFetch<FilterPassband>(`/equipment/filter/${filterId}/passband`, {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(data),
  });

export const updateFilterPassband = (
  filterId: number,
  passbandId: number,
  data: Partial<FilterPassbandCreate>,
) =>
  apiFetch<FilterPassband>(`/equipment/filter/${filterId}/passband/${passbandId}`, {
    method: "PUT",
    headers: JSON_HEADERS,
    body: JSON.stringify(data),
  });

export const deleteFilterPassband = (filterId: number, passbandId: number) =>
  apiFetch<{ ok: boolean }>(
    `/equipment/filter/${filterId}/passband/${passbandId}`,
    { method: "DELETE" },
  );

// ---------------------------------------------------------------------------
// Mount
// ---------------------------------------------------------------------------

export const fetchMounts = (includeRetired = false) =>
  apiFetch<Mount[]>(`/equipment/mount${retiredParam(includeRetired)}`);

export const fetchMount = (id: number) =>
  apiFetch<Mount>(`/equipment/mount/${id}`);

export const createMount = (data: MountCreate) =>
  apiFetch<Mount>("/equipment/mount", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(data),
  });

export const updateMount = (id: number, data: Partial<MountCreate>) =>
  apiFetch<Mount>(`/equipment/mount/${id}`, {
    method: "PUT",
    headers: JSON_HEADERS,
    body: JSON.stringify(data),
  });

export const deleteMount = (id: number) =>
  apiFetch<{ ok: boolean }>(`/equipment/mount/${id}`, { method: "DELETE" });

// ---------------------------------------------------------------------------
// Focuser
// ---------------------------------------------------------------------------

export const fetchFocusers = (includeRetired = false) =>
  apiFetch<Focuser[]>(`/equipment/focuser${retiredParam(includeRetired)}`);

export const fetchFocuser = (id: number) =>
  apiFetch<Focuser>(`/equipment/focuser/${id}`);

export const createFocuser = (data: FocuserCreate) =>
  apiFetch<Focuser>("/equipment/focuser", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(data),
  });

export const updateFocuser = (id: number, data: Partial<FocuserCreate>) =>
  apiFetch<Focuser>(`/equipment/focuser/${id}`, {
    method: "PUT",
    headers: JSON_HEADERS,
    body: JSON.stringify(data),
  });

export const deleteFocuser = (id: number) =>
  apiFetch<{ ok: boolean }>(`/equipment/focuser/${id}`, { method: "DELETE" });

// ---------------------------------------------------------------------------
// Filter Wheel
// ---------------------------------------------------------------------------

export const fetchFilterWheels = (includeRetired = false) =>
  apiFetch<FilterWheel[]>(`/equipment/filter-wheel${retiredParam(includeRetired)}`);

export const fetchFilterWheel = (id: number) =>
  apiFetch<FilterWheel>(`/equipment/filter-wheel/${id}`);

export const createFilterWheel = (data: FilterWheelCreate) =>
  apiFetch<FilterWheel>("/equipment/filter-wheel", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(data),
  });

export const updateFilterWheel = (id: number, data: Partial<FilterWheelCreate>) =>
  apiFetch<FilterWheel>(`/equipment/filter-wheel/${id}`, {
    method: "PUT",
    headers: JSON_HEADERS,
    body: JSON.stringify(data),
  });

export const deleteFilterWheel = (id: number) =>
  apiFetch<{ ok: boolean }>(`/equipment/filter-wheel/${id}`, { method: "DELETE" });

// ---------------------------------------------------------------------------
// OAG
// ---------------------------------------------------------------------------

export const fetchOags = (includeRetired = false) =>
  apiFetch<Oag[]>(`/equipment/oag${retiredParam(includeRetired)}`);

export const fetchOag = (id: number) =>
  apiFetch<Oag>(`/equipment/oag/${id}`);

export const createOag = (data: OagCreate) =>
  apiFetch<Oag>("/equipment/oag", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(data),
  });

export const updateOag = (id: number, data: Partial<OagCreate>) =>
  apiFetch<Oag>(`/equipment/oag/${id}`, {
    method: "PUT",
    headers: JSON_HEADERS,
    body: JSON.stringify(data),
  });

export const deleteOag = (id: number) =>
  apiFetch<{ ok: boolean }>(`/equipment/oag/${id}`, { method: "DELETE" });

// ---------------------------------------------------------------------------
// Guide Scope
// ---------------------------------------------------------------------------

export const fetchGuideScopes = (includeRetired = false) =>
  apiFetch<GuideScope[]>(`/equipment/guide-scope${retiredParam(includeRetired)}`);

export const fetchGuideScope = (id: number) =>
  apiFetch<GuideScope>(`/equipment/guide-scope/${id}`);

export const createGuideScope = (data: GuideScopeCreate) =>
  apiFetch<GuideScope>("/equipment/guide-scope", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(data),
  });

export const updateGuideScope = (id: number, data: Partial<GuideScopeCreate>) =>
  apiFetch<GuideScope>(`/equipment/guide-scope/${id}`, {
    method: "PUT",
    headers: JSON_HEADERS,
    body: JSON.stringify(data),
  });

export const deleteGuideScope = (id: number) =>
  apiFetch<{ ok: boolean }>(`/equipment/guide-scope/${id}`, { method: "DELETE" });

// ---------------------------------------------------------------------------
// Computer
// ---------------------------------------------------------------------------

export const fetchComputers = (includeRetired = false) =>
  apiFetch<Computer[]>(`/equipment/computer${retiredParam(includeRetired)}`);

export const fetchComputer = (id: number) =>
  apiFetch<Computer>(`/equipment/computer/${id}`);

export const createComputer = (data: ComputerCreate) =>
  apiFetch<Computer>("/equipment/computer", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(data),
  });

export const updateComputer = (id: number, data: Partial<ComputerCreate>) =>
  apiFetch<Computer>(`/equipment/computer/${id}`, {
    method: "PUT",
    headers: JSON_HEADERS,
    body: JSON.stringify(data),
  });

export const deleteComputer = (id: number) =>
  apiFetch<{ ok: boolean }>(`/equipment/computer/${id}`, { method: "DELETE" });

// ---------------------------------------------------------------------------
// Software
// ---------------------------------------------------------------------------

export const fetchSoftwares = (includeRetired = false) =>
  apiFetch<Software[]>(`/equipment/software${retiredParam(includeRetired)}`);

export const fetchSoftware = (id: number) =>
  apiFetch<Software>(`/equipment/software/${id}`);

export const createSoftware = (data: SoftwareCreate) =>
  apiFetch<Software>("/equipment/software", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(data),
  });

export const updateSoftware = (id: number, data: Partial<SoftwareCreate>) =>
  apiFetch<Software>(`/equipment/software/${id}`, {
    method: "PUT",
    headers: JSON_HEADERS,
    body: JSON.stringify(data),
  });

export const deleteSoftware = (id: number) =>
  apiFetch<{ ok: boolean }>(`/equipment/software/${id}`, { method: "DELETE" });
