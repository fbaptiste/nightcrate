"""Pydantic models for equipment API request/response shapes."""

from pydantic import BaseModel

# ── Lookup tables ────────────────────────────────────────────────────────────


class ManufacturerCreate(BaseModel):
    name: str
    website: str | None = None
    notes: str | None = None


class ManufacturerUpdate(BaseModel):
    name: str | None = None
    website: str | None = None
    notes: str | None = None


class ManufacturerResponse(BaseModel):
    id: int
    name: str
    website: str | None
    notes: str | None
    active: bool
    created_at: str
    updated_at: str


class OpticalDesignCreate(BaseModel):
    name: str
    description: str | None = None


class OpticalDesignUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class OpticalDesignResponse(BaseModel):
    id: int
    name: str
    description: str | None
    active: bool
    created_at: str
    updated_at: str


class MountTypeCreate(BaseModel):
    name: str
    description: str | None = None


class MountTypeUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class MountTypeResponse(BaseModel):
    id: int
    name: str
    description: str | None
    active: bool
    created_at: str
    updated_at: str


class ConnectionInterfaceCreate(BaseModel):
    name: str
    category: str  # CHECK 'data','control','power','wireless'
    notes: str | None = None


class ConnectionInterfaceUpdate(BaseModel):
    name: str | None = None
    category: str | None = None
    notes: str | None = None


class ConnectionInterfaceResponse(BaseModel):
    id: int
    name: str
    category: str
    notes: str | None
    active: bool
    created_at: str
    updated_at: str


class ConnectorSizeCreate(BaseModel):
    name: str
    diameter_mm: float | None = None
    notes: str | None = None


class ConnectorSizeUpdate(BaseModel):
    name: str | None = None
    diameter_mm: float | None = None
    notes: str | None = None


class ConnectorSizeResponse(BaseModel):
    id: int
    name: str
    diameter_mm: float | None
    notes: str | None
    active: bool
    created_at: str
    updated_at: str


class FilterSizeCreate(BaseModel):
    name: str
    description: str | None = None


class FilterSizeUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class FilterSizeResponse(BaseModel):
    id: int
    name: str
    description: str | None
    active: bool
    created_at: str
    updated_at: str


class FormFactorCreate(BaseModel):
    name: str
    description: str | None = None


class FormFactorUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class FormFactorResponse(BaseModel):
    id: int
    name: str
    description: str | None
    active: bool
    created_at: str
    updated_at: str


class FocuserTypeCreate(BaseModel):
    name: str
    notes: str | None = None


class FocuserTypeUpdate(BaseModel):
    name: str | None = None
    notes: str | None = None


class FocuserTypeResponse(BaseModel):
    id: int
    name: str
    notes: str | None
    active: bool
    created_at: str
    updated_at: str


class FilterTypeCreate(BaseModel):
    name: str
    display_name: str
    description: str | None = None


class FilterTypeUpdate(BaseModel):
    name: str | None = None
    display_name: str | None = None
    description: str | None = None


class FilterTypeResponse(BaseModel):
    id: int
    name: str
    display_name: str
    description: str | None
    active: bool
    created_at: str
    updated_at: str


# ── Sensor ───────────────────────────────────────────────────────────────────


class SensorCreate(BaseModel):
    manufacturer_id: int
    model_name: str
    sensor_type: str  # 'mono' or 'color'
    pixel_size_um: float
    resolution_x: int
    resolution_y: int
    sensor_width_mm: float | None = None
    sensor_height_mm: float | None = None
    adc_bit_depth: int | None = None
    full_well_capacity_ke: float | None = None
    read_noise_e: float | None = None
    peak_qe_pct: float | None = None
    bayer_pattern: str | None = None
    dual_gain: bool = False
    notes: str | None = None
    source_url: str | None = None


class SensorUpdate(BaseModel):
    manufacturer_id: int | None = None
    model_name: str | None = None
    sensor_type: str | None = None
    pixel_size_um: float | None = None
    resolution_x: int | None = None
    resolution_y: int | None = None
    sensor_width_mm: float | None = None
    sensor_height_mm: float | None = None
    adc_bit_depth: int | None = None
    full_well_capacity_ke: float | None = None
    read_noise_e: float | None = None
    peak_qe_pct: float | None = None
    bayer_pattern: str | None = None
    dual_gain: bool | None = None
    notes: str | None = None
    source_url: str | None = None


class SensorResponse(BaseModel):
    id: int
    manufacturer: ManufacturerResponse
    model_name: str
    sensor_type: str
    pixel_size_um: float
    resolution_x: int
    resolution_y: int
    sensor_width_mm: float | None
    sensor_height_mm: float | None
    adc_bit_depth: int | None
    full_well_capacity_ke: float | None
    read_noise_e: float | None
    peak_qe_pct: float | None
    bayer_pattern: str | None
    dual_gain: bool
    notes: str | None
    source_url: str | None
    active: bool
    created_at: str
    updated_at: str


# ── Camera ───────────────────────────────────────────────────────────────────


class CameraCreate(BaseModel):
    manufacturer_id: int
    sensor_id: int
    guide_sensor_id: int | None = None
    connector_size_id: int | None = None
    model_name: str
    cooled: bool = False
    cooling_delta_c: float | None = None
    back_focus_mm: float | None = None
    weight_g: float | None = None
    tilt_adapter: bool = False
    has_usb_hub: bool = False
    usb_hub_interface_id: int | None = None
    unity_gain: int | None = None
    effective_full_well_ke: float | None = None
    effective_read_noise_lcg_e: float | None = None
    effective_read_noise_hcg_e: float | None = None
    effective_peak_qe_pct: float | None = None
    hcg_threshold_gain: int | None = None
    notes: str | None = None
    source_url: str | None = None
    interface_ids: list[int] = []


class CameraUpdate(BaseModel):
    manufacturer_id: int | None = None
    sensor_id: int | None = None
    guide_sensor_id: int | None = None
    connector_size_id: int | None = None
    model_name: str | None = None
    cooled: bool | None = None
    cooling_delta_c: float | None = None
    back_focus_mm: float | None = None
    weight_g: float | None = None
    tilt_adapter: bool | None = None
    has_usb_hub: bool | None = None
    usb_hub_interface_id: int | None = None
    unity_gain: int | None = None
    effective_full_well_ke: float | None = None
    effective_read_noise_lcg_e: float | None = None
    effective_read_noise_hcg_e: float | None = None
    effective_peak_qe_pct: float | None = None
    hcg_threshold_gain: int | None = None
    notes: str | None = None
    source_url: str | None = None
    interface_ids: list[int] | None = None


class CameraResponse(BaseModel):
    id: int
    manufacturer: ManufacturerResponse
    sensor: SensorResponse
    guide_sensor: SensorResponse | None
    connector_size: ConnectorSizeResponse | None
    model_name: str
    cooled: bool
    cooling_delta_c: float | None
    back_focus_mm: float | None
    weight_g: float | None
    tilt_adapter: bool
    has_usb_hub: bool
    usb_hub_interface: ConnectionInterfaceResponse | None
    unity_gain: int | None
    effective_full_well_ke: float | None
    effective_read_noise_lcg_e: float | None
    effective_read_noise_hcg_e: float | None
    effective_peak_qe_pct: float | None
    hcg_threshold_gain: int | None
    notes: str | None
    source_url: str | None
    interfaces: list[ConnectionInterfaceResponse]
    active: bool
    created_at: str
    updated_at: str


# ── Telescope ────────────────────────────────────────────────────────────────


class TelescopeConfigurationCreate(BaseModel):
    telescope_id: int
    config_name: str
    accessory_name: str | None = None
    reduction_factor: float | None = None
    effective_focal_length_mm: float
    effective_focal_ratio: float
    effective_image_circle_mm: float | None = None
    effective_back_focus_mm: float | None = None
    is_native: bool = False
    notes: str | None = None


class TelescopeConfigurationUpdate(BaseModel):
    telescope_id: int | None = None
    config_name: str | None = None
    accessory_name: str | None = None
    reduction_factor: float | None = None
    effective_focal_length_mm: float | None = None
    effective_focal_ratio: float | None = None
    effective_image_circle_mm: float | None = None
    effective_back_focus_mm: float | None = None
    is_native: bool | None = None
    notes: str | None = None


class TelescopeConfigurationResponse(BaseModel):
    id: int
    telescope_id: int
    config_name: str
    accessory_name: str | None
    reduction_factor: float | None
    effective_focal_length_mm: float
    effective_focal_ratio: float
    effective_image_circle_mm: float | None
    effective_back_focus_mm: float | None
    is_native: bool
    notes: str | None
    created_at: str
    updated_at: str


class TelescopeCreate(BaseModel):
    manufacturer_id: int
    optical_design_id: int | None = None
    model_name: str
    aperture_mm: float
    image_circle_mm: float | None = None
    weight_kg: float | None = None
    obstruction_pct: float | None = None
    notes: str | None = None
    source_url: str | None = None
    connector_size_ids: list[int] = []


class TelescopeUpdate(BaseModel):
    manufacturer_id: int | None = None
    optical_design_id: int | None = None
    model_name: str | None = None
    aperture_mm: float | None = None
    image_circle_mm: float | None = None
    weight_kg: float | None = None
    obstruction_pct: float | None = None
    notes: str | None = None
    source_url: str | None = None
    connector_size_ids: list[int] | None = None


class TelescopeResponse(BaseModel):
    id: int
    manufacturer: ManufacturerResponse
    optical_design: OpticalDesignResponse | None
    model_name: str
    aperture_mm: float
    image_circle_mm: float | None
    weight_kg: float | None
    obstruction_pct: float | None
    notes: str | None
    source_url: str | None
    connectors: list[ConnectorSizeResponse]
    configurations: list[TelescopeConfigurationResponse]
    active: bool
    created_at: str
    updated_at: str


# ── Filter ───────────────────────────────────────────────────────────────────


class FilterPassbandCreate(BaseModel):
    filter_id: int
    line_name: str | None = None
    central_wavelength_nm: float
    bandwidth_nm: float | None = None
    peak_transmission_pct: float | None = None


class FilterPassbandUpdate(BaseModel):
    filter_id: int | None = None
    line_name: str | None = None
    central_wavelength_nm: float | None = None
    bandwidth_nm: float | None = None
    peak_transmission_pct: float | None = None


class FilterPassbandResponse(BaseModel):
    id: int
    filter_id: int
    line_name: str | None
    central_wavelength_nm: float
    bandwidth_nm: float | None
    peak_transmission_pct: float | None


class FilterSizeOptionCreate(BaseModel):
    filter_id: int
    filter_size_id: int
    mounted_thickness_mm: float | None = None
    notes: str | None = None


class FilterSizeOptionUpdate(BaseModel):
    filter_size_id: int | None = None
    mounted_thickness_mm: float | None = None
    notes: str | None = None


class FilterSizeOptionResponse(BaseModel):
    id: int
    filter_id: int
    filter_size: FilterSizeResponse
    mounted_thickness_mm: float | None
    notes: str | None


class FilterCreate(BaseModel):
    manufacturer_id: int
    filter_type_id: int
    model_name: str
    peak_transmission_pct: float | None = None
    notes: str | None = None
    source_url: str | None = None


class FilterUpdate(BaseModel):
    manufacturer_id: int | None = None
    filter_type_id: int | None = None
    model_name: str | None = None
    peak_transmission_pct: float | None = None
    notes: str | None = None
    source_url: str | None = None


class FilterResponse(BaseModel):
    id: int
    manufacturer: ManufacturerResponse
    filter_type: FilterTypeResponse
    model_name: str
    peak_transmission_pct: float | None
    notes: str | None
    source_url: str | None
    passbands: list[FilterPassbandResponse]
    size_options: list[FilterSizeOptionResponse]
    active: bool
    created_at: str
    updated_at: str


# ── Mount ────────────────────────────────────────────────────────────────────


class MountCreate(BaseModel):
    manufacturer_id: int
    mount_type_id: int | None = None
    model_name: str
    payload_capacity_kg: float | None = None
    mount_weight_kg: float | None = None
    counterweight_required: bool = True
    goto_capable: bool = True
    periodic_error_arcsec: float | None = None
    drive_type: str | None = None
    notes: str | None = None
    source_url: str | None = None
    interface_ids: list[int] = []


class MountUpdate(BaseModel):
    manufacturer_id: int | None = None
    mount_type_id: int | None = None
    model_name: str | None = None
    payload_capacity_kg: float | None = None
    mount_weight_kg: float | None = None
    counterweight_required: bool | None = None
    goto_capable: bool | None = None
    periodic_error_arcsec: float | None = None
    drive_type: str | None = None
    notes: str | None = None
    source_url: str | None = None
    interface_ids: list[int] | None = None


class MountResponse(BaseModel):
    id: int
    manufacturer: ManufacturerResponse
    mount_type: MountTypeResponse | None
    model_name: str
    payload_capacity_kg: float | None
    mount_weight_kg: float | None
    counterweight_required: bool
    goto_capable: bool
    periodic_error_arcsec: float | None
    drive_type: str | None
    notes: str | None
    source_url: str | None
    interfaces: list[ConnectionInterfaceResponse]
    active: bool
    created_at: str
    updated_at: str


# ── Focuser ──────────────────────────────────────────────────────────────────


class FocuserCreate(BaseModel):
    manufacturer_id: int
    focuser_type_id: int | None = None
    model_name: str
    motorized: bool = True
    travel_range_mm: float | None = None
    step_size_um: float | None = None
    total_steps: int | None = None
    temperature_compensation: bool = False
    backlash_steps: int | None = None
    notes: str | None = None
    source_url: str | None = None
    interface_ids: list[int] = []


class FocuserUpdate(BaseModel):
    manufacturer_id: int | None = None
    focuser_type_id: int | None = None
    model_name: str | None = None
    motorized: bool | None = None
    travel_range_mm: float | None = None
    step_size_um: float | None = None
    total_steps: int | None = None
    temperature_compensation: bool | None = None
    backlash_steps: int | None = None
    notes: str | None = None
    source_url: str | None = None
    interface_ids: list[int] | None = None


class FocuserResponse(BaseModel):
    id: int
    manufacturer: ManufacturerResponse
    focuser_type: FocuserTypeResponse | None
    model_name: str
    motorized: bool
    travel_range_mm: float | None
    step_size_um: float | None
    total_steps: int | None
    temperature_compensation: bool
    backlash_steps: int | None
    notes: str | None
    source_url: str | None
    interfaces: list[ConnectionInterfaceResponse]
    active: bool
    created_at: str
    updated_at: str


# ── Filter wheel ─────────────────────────────────────────────────────────────


class FilterWheelCreate(BaseModel):
    manufacturer_id: int
    filter_size_id: int | None = None
    camera_side_connector_id: int | None = None
    telescope_side_connector_id: int | None = None
    model_name: str
    num_positions: int
    back_focus_contribution_mm: float | None = None
    notes: str | None = None
    source_url: str | None = None
    interface_ids: list[int] = []


class FilterWheelUpdate(BaseModel):
    manufacturer_id: int | None = None
    filter_size_id: int | None = None
    camera_side_connector_id: int | None = None
    telescope_side_connector_id: int | None = None
    model_name: str | None = None
    num_positions: int | None = None
    back_focus_contribution_mm: float | None = None
    notes: str | None = None
    source_url: str | None = None
    interface_ids: list[int] | None = None


class FilterWheelResponse(BaseModel):
    id: int
    manufacturer: ManufacturerResponse
    filter_size: FilterSizeResponse | None
    camera_side_connector: ConnectorSizeResponse | None
    telescope_side_connector: ConnectorSizeResponse | None
    model_name: str
    num_positions: int
    back_focus_contribution_mm: float | None
    notes: str | None
    source_url: str | None
    interfaces: list[ConnectionInterfaceResponse]
    active: bool
    created_at: str
    updated_at: str


# ── OAG ──────────────────────────────────────────────────────────────────────


class OagCreate(BaseModel):
    manufacturer_id: int
    imaging_side_connector_id: int | None = None
    guide_camera_connector_id: int | None = None
    model_name: str
    prism_size_mm: float | None = None
    back_focus_contribution_mm: float | None = None
    weight_g: float | None = None
    notes: str | None = None
    source_url: str | None = None


class OagUpdate(BaseModel):
    manufacturer_id: int | None = None
    imaging_side_connector_id: int | None = None
    guide_camera_connector_id: int | None = None
    model_name: str | None = None
    prism_size_mm: float | None = None
    back_focus_contribution_mm: float | None = None
    weight_g: float | None = None
    notes: str | None = None
    source_url: str | None = None


class OagResponse(BaseModel):
    id: int
    manufacturer: ManufacturerResponse
    imaging_side_connector: ConnectorSizeResponse | None
    guide_camera_connector: ConnectorSizeResponse | None
    model_name: str
    prism_size_mm: float | None
    back_focus_contribution_mm: float | None
    weight_g: float | None
    notes: str | None
    source_url: str | None
    active: bool
    created_at: str
    updated_at: str


# ── Guide scope ───────────────────────────────────────────────────────────────


class GuideScopeCreate(BaseModel):
    manufacturer_id: int
    guide_camera_connector_id: int | None = None
    model_name: str
    aperture_mm: float | None = None
    focal_length_mm: float | None = None
    weight_g: float | None = None
    notes: str | None = None
    source_url: str | None = None


class GuideScopeUpdate(BaseModel):
    manufacturer_id: int | None = None
    guide_camera_connector_id: int | None = None
    model_name: str | None = None
    aperture_mm: float | None = None
    focal_length_mm: float | None = None
    weight_g: float | None = None
    notes: str | None = None
    source_url: str | None = None


class GuideScopeResponse(BaseModel):
    id: int
    manufacturer: ManufacturerResponse
    guide_camera_connector: ConnectorSizeResponse | None
    model_name: str
    aperture_mm: float | None
    focal_length_mm: float | None
    weight_g: float | None
    notes: str | None
    source_url: str | None
    active: bool
    created_at: str
    updated_at: str


# ── Computer ─────────────────────────────────────────────────────────────────


class ComputerCreate(BaseModel):
    manufacturer_id: int
    form_factor_id: int | None = None
    model_name: str
    notes: str | None = None
    source_url: str | None = None


class ComputerUpdate(BaseModel):
    manufacturer_id: int | None = None
    form_factor_id: int | None = None
    model_name: str | None = None
    notes: str | None = None
    source_url: str | None = None


class ComputerResponse(BaseModel):
    id: int
    manufacturer: ManufacturerResponse
    form_factor: FormFactorResponse | None
    model_name: str
    notes: str | None
    source_url: str | None
    active: bool
    created_at: str
    updated_at: str


# ── Software ─────────────────────────────────────────────────────────────────


class SoftwareCreate(BaseModel):
    manufacturer_id: int | None = None
    name: str
    # CHECK 'capture','guiding','planetarium','processing','utility',
    # 'focuser','mount_control','observatory','plate_solver',
    # 'polar_alignment','weather','other'
    category: str
    website: str | None = None
    notes: str | None = None


class SoftwareUpdate(BaseModel):
    manufacturer_id: int | None = None
    name: str | None = None
    category: str | None = None
    website: str | None = None
    notes: str | None = None


class SoftwareResponse(BaseModel):
    id: int
    manufacturer: ManufacturerResponse | None
    name: str
    category: str
    website: str | None
    notes: str | None
    active: bool
    created_at: str
    updated_at: str
