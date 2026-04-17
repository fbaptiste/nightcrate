import { useQueries, useQuery } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";
import {
  fetchCamera,
  fetchComputer,
  fetchFilter,
  fetchFilterWheel,
  fetchFocuser,
  fetchGuideScope,
  fetchMount,
  fetchOag,
  fetchTelescope,
  type Camera,
  type Computer,
  type Filter,
  type FilterWheel,
  type Focuser,
  type GuideScope,
  type Mount,
  type Oag,
  type Sensor,
  type Telescope,
  type TelescopeConfiguration,
} from "@/api/equipment";
import type { Rig } from "@/api/rigs";

interface EquipmentTabProps {
  rig: Rig;
}

export default function EquipmentTab({ rig }: EquipmentTabProps) {
  const { data: telescope, isLoading: tLoading } = useQuery({
    queryKey: ["rig-equipment", "telescope", rig.telescope_id],
    queryFn: async (): Promise<{ telescope: Telescope; config: TelescopeConfiguration }> => {
      const full = await fetchTelescope(rig.telescope_id);
      const config = full.configurations.find(
        (c) => c.id === rig.telescope_configuration_id,
      );
      if (!config) throw new Error("Telescope configuration not found on rig");
      return { telescope: full, config };
    },
  });

  const { data: camera, isLoading: cLoading } = useQuery({
    queryKey: ["rig-equipment", "camera", rig.camera_id],
    queryFn: () => fetchCamera(rig.camera_id),
  });

  const { data: filterWheel } = useQuery<FilterWheel>({
    queryKey: ["rig-equipment", "filter-wheel", rig.filter_wheel_id],
    queryFn: () => fetchFilterWheel(rig.filter_wheel_id!),
    enabled: rig.filter_wheel_id != null,
  });

  // Collect filter IDs: slot filters + single filter.
  const filterIds: number[] = [];
  for (const slot of rig.filter_slots) filterIds.push(slot.filter_id);
  if (rig.single_filter_id != null) filterIds.push(rig.single_filter_id);

  const filterQueries = useQueries({
    queries: filterIds.map((id) => ({
      queryKey: ["rig-equipment", "filter", id],
      queryFn: () => fetchFilter(id),
    })),
  });
  const filtersById = new Map<number, Filter>();
  for (const q of filterQueries) {
    if (q.data) filtersById.set(q.data.id, q.data);
  }

  const { data: mount } = useQuery<Mount>({
    queryKey: ["rig-equipment", "mount", rig.mount_id],
    queryFn: () => fetchMount(rig.mount_id!),
    enabled: rig.mount_id != null,
  });

  const { data: focuser } = useQuery<Focuser>({
    queryKey: ["rig-equipment", "focuser", rig.focuser_id],
    queryFn: () => fetchFocuser(rig.focuser_id!),
    enabled: rig.focuser_id != null,
  });

  const { data: oag } = useQuery<Oag>({
    queryKey: ["rig-equipment", "oag", rig.oag_id],
    queryFn: () => fetchOag(rig.oag_id!),
    enabled: rig.oag_id != null,
  });

  const { data: guideScope } = useQuery<GuideScope>({
    queryKey: ["rig-equipment", "guide-scope", rig.guide_scope_id],
    queryFn: () => fetchGuideScope(rig.guide_scope_id!),
    enabled: rig.guide_scope_id != null,
  });

  const { data: guideCamera } = useQuery<Camera>({
    queryKey: ["rig-equipment", "guide-camera", rig.guide_camera_id],
    queryFn: () => fetchCamera(rig.guide_camera_id!),
    enabled: rig.guide_camera_id != null,
  });

  const { data: computer } = useQuery<Computer>({
    queryKey: ["rig-equipment", "computer", rig.computer_id],
    queryFn: () => fetchComputer(rig.computer_id!),
    enabled: rig.computer_id != null,
  });

  const coreLoading = tLoading || cLoading;

  return (
    <Box>
      {coreLoading && (
        <Box sx={{ display: "flex", justifyContent: "center", py: 4 }}>
          <CircularProgress size={28} />
        </Box>
      )}

      {!coreLoading && (
        <Box
          sx={{
            display: "grid",
            gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" },
            gap: 2.5,
            alignItems: "start",
          }}
        >
          {/* Column-flowing sections — MUI grid will pack them into two columns on md+ */}
          {rig.description && (
            <Card title="Description" fullWidth>
              <Typography variant="body2">{rig.description}</Typography>
            </Card>
          )}

          {telescope && (
            <Card title="Optical Train">
              <OpticalTrainBody
                telescope={telescope.telescope}
                config={telescope.config}
                allConfigs={telescope.telescope.configurations}
              />
            </Card>
          )}

          {camera && (
            <Card title="Imaging Camera">
              <CameraBody camera={camera} />
            </Card>
          )}

          {(filterWheel || rig.filter_slots.length > 0 || rig.single_filter_id) && (
            <Card title="Filtration">
              <FiltrationBody
                wheel={filterWheel ?? null}
                slots={rig.filter_slots.map((s) => ({
                  slotNumber: s.slot_number,
                  filter: filtersById.get(s.filter_id) ?? null,
                }))}
                singleFilter={
                  rig.single_filter_id != null
                    ? filtersById.get(rig.single_filter_id) ?? null
                    : null
                }
              />
            </Card>
          )}

          {(oag || guideScope || guideCamera) && (
            <Card title="Guide System">
              <GuideSystemBody
                oag={oag ?? null}
                guideScope={guideScope ?? null}
                guideCamera={guideCamera ?? null}
              />
            </Card>
          )}

          {mount && (
            <Card title="Mount">
              <MountBody mount={mount} />
            </Card>
          )}

          {focuser && (
            <Card title="Focuser">
              <FocuserBody focuser={focuser} />
            </Card>
          )}

          {(computer || rig.software.length > 0) && (
            <Card title="Computing">
              <ComputingBody
                computer={computer ?? null}
                software={rig.software}
              />
            </Card>
          )}

          {rig.notes && (
            <Card title="Notes" fullWidth>
              <Typography
                variant="body2"
                sx={{ whiteSpace: "pre-wrap", color: "text.secondary" }}
              >
                {rig.notes}
              </Typography>
            </Card>
          )}
        </Box>
      )}
    </Box>
  );
}

// ── Section card shell ──────────────────────────────────────────────────────

function Card({
  title,
  children,
  fullWidth = false,
}: {
  title: string;
  children: React.ReactNode;
  fullWidth?: boolean;
}) {
  return (
    <Paper
      variant="outlined"
      sx={{ p: 2, gridColumn: fullWidth ? { md: "1 / -1" } : undefined }}
    >
      <Typography variant="body2" sx={{ fontWeight: 600, mb: 1 }}>
        {title}
      </Typography>
      <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
        {children}
      </Box>
    </Paper>
  );
}

function Field({
  label,
  value,
}: {
  label: string;
  value: React.ReactNode;
}) {
  if (value === null || value === undefined || value === "") return null;
  return (
    <Box sx={{ display: "flex", gap: 1 }}>
      <Typography
        variant="body2"
        color="text.secondary"
        sx={{ minWidth: 150, flexShrink: 0 }}
      >
        {label}
      </Typography>
      <Typography variant="body2" component="div">
        {value}
      </Typography>
    </Box>
  );
}

function Subsection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <Box sx={{ mt: 0.5 }}>
      <Typography
        variant="caption"
        color="text.secondary"
        sx={{
          textTransform: "uppercase",
          letterSpacing: 0.5,
          fontWeight: 600,
          display: "block",
          mb: 0.5,
        }}
      >
        {title}
      </Typography>
      <Box sx={{ display: "flex", flexDirection: "column", gap: 0.5, pl: 1 }}>
        {children}
      </Box>
    </Box>
  );
}

function InterfacePills({ interfaces }: { interfaces: { name: string }[] }) {
  if (!interfaces.length) return null;
  return (
    <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5 }}>
      {interfaces.map((i) => (
        <Chip key={i.name} label={i.name} size="small" variant="outlined" />
      ))}
    </Box>
  );
}

// ── Body components ────────────────────────────────────────────────────────

function OpticalTrainBody({
  telescope,
  config,
  allConfigs,
}: {
  telescope: Telescope;
  config: TelescopeConfiguration;
  allConfigs: TelescopeConfiguration[];
}) {
  return (
    <>
      <Field
        label="Telescope"
        value={`${telescope.manufacturer.name} ${telescope.model_name}`}
      />
      <Field label="Aperture" value={`${telescope.aperture_mm} mm`} />
      <Field
        label="Optical Design"
        value={telescope.optical_design?.name ?? null}
      />
      <Field
        label="Image Circle (native)"
        value={telescope.image_circle_mm != null ? `${telescope.image_circle_mm} mm` : null}
      />
      <Field
        label="Weight"
        value={telescope.weight_kg != null ? `${telescope.weight_kg} kg` : null}
      />
      <Field
        label="Central Obstruction"
        value={
          telescope.obstruction_pct != null ? `${telescope.obstruction_pct}%` : null
        }
      />
      <Field
        label="Connectors"
        value={
          telescope.connectors.length
            ? telescope.connectors.map((c) => c.name).join(", ")
            : null
        }
      />
      {telescope.notes && <Field label="Notes" value={telescope.notes} />}
      <Subsection title="Active Configuration">
        <Field label="Name" value={config.config_name} />
        {config.accessory_name && (
          <Field label="Accessory" value={config.accessory_name} />
        )}
        <Field
          label="Focal Length"
          value={`${config.effective_focal_length_mm} mm`}
        />
        <Field label="Focal Ratio" value={`f/${config.effective_focal_ratio}`} />
        {config.reduction_factor != null && (
          <Field label="Reduction Factor" value={`${config.reduction_factor}x`} />
        )}
        {config.effective_image_circle_mm != null && (
          <Field
            label="Effective Image Circle"
            value={`${config.effective_image_circle_mm} mm`}
          />
        )}
        {config.effective_back_focus_mm != null && (
          <Field
            label="Back Focus Target"
            value={`${config.effective_back_focus_mm} mm`}
          />
        )}
        <Field label="Native?" value={config.is_native ? "Yes" : "No"} />
        {config.notes && <Field label="Notes" value={config.notes} />}
      </Subsection>
      {allConfigs.length > 1 && (
        <Subsection title="Other Configurations">
          {allConfigs
            .filter((c) => c.id !== config.id)
            .map((c) => (
              <Field
                key={c.id}
                label={c.config_name}
                value={`${c.effective_focal_length_mm} mm, f/${c.effective_focal_ratio}`}
              />
            ))}
        </Subsection>
      )}
    </>
  );
}

function SensorBody({ sensor, label }: { sensor: Sensor; label?: string }) {
  return (
    <Subsection title={label ?? "Sensor"}>
      <Field
        label="Model"
        value={`${sensor.manufacturer.name} ${sensor.model_name}`}
      />
      <Field label="Type" value={sensor.sensor_type} />
      {sensor.bayer_pattern && (
        <Field label="Bayer Pattern" value={sensor.bayer_pattern} />
      )}
      <Field label="Pixel Size" value={`${sensor.pixel_size_um} µm`} />
      <Field
        label="Resolution"
        value={`${sensor.resolution_x} × ${sensor.resolution_y}`}
      />
      {sensor.sensor_width_mm != null && sensor.sensor_height_mm != null && (
        <Field
          label="Sensor Size"
          value={`${sensor.sensor_width_mm} × ${sensor.sensor_height_mm} mm`}
        />
      )}
      {sensor.adc_bit_depth != null && (
        <Field label="ADC Bit Depth" value={`${sensor.adc_bit_depth}-bit`} />
      )}
      {sensor.full_well_capacity_ke != null && (
        <Field
          label="Full Well"
          value={`${sensor.full_well_capacity_ke} ke⁻`}
        />
      )}
      {sensor.read_noise_e != null && (
        <Field label="Read Noise" value={`${sensor.read_noise_e} e⁻`} />
      )}
      {sensor.peak_qe_pct != null && (
        <Field label="Peak QE" value={`${sensor.peak_qe_pct}%`} />
      )}
      <Field label="Dual Gain" value={sensor.dual_gain ? "Yes" : "No"} />
      {sensor.notes && <Field label="Notes" value={sensor.notes} />}
    </Subsection>
  );
}

function CameraBody({ camera }: { camera: Camera }) {
  return (
    <>
      <Field
        label="Camera"
        value={`${camera.manufacturer.name} ${camera.model_name}`}
      />
      <Field label="Cooled" value={camera.cooled ? "Yes" : "No"} />
      {camera.cooling_delta_c != null && (
        <Field label="Cooling Delta" value={`Δ${camera.cooling_delta_c}°C`} />
      )}
      {camera.back_focus_mm != null && (
        <Field label="Back Focus" value={`${camera.back_focus_mm} mm`} />
      )}
      {camera.weight_g != null && (
        <Field label="Weight" value={`${camera.weight_g} g`} />
      )}
      <Field label="Tilt Adapter" value={camera.tilt_adapter ? "Yes" : "No"} />
      <Field label="USB Hub" value={camera.has_usb_hub ? "Yes" : "No"} />
      {camera.usb_hub_interface && (
        <Field label="USB Hub Interface" value={camera.usb_hub_interface.name} />
      )}
      {camera.connector_size && (
        <Field label="Connector" value={camera.connector_size.name} />
      )}
      {camera.unity_gain != null && (
        <Field label="Unity Gain" value={camera.unity_gain} />
      )}
      {(camera.effective_read_noise_lcg_e != null ||
        camera.effective_read_noise_hcg_e != null ||
        camera.effective_full_well_ke != null ||
        camera.effective_peak_qe_pct != null ||
        camera.hcg_threshold_gain != null) && (
        <Subsection title="Vendor-tuned Specs">
          {camera.effective_read_noise_lcg_e != null && (
            <Field
              label="Read Noise (LCG)"
              value={`${camera.effective_read_noise_lcg_e} e⁻`}
            />
          )}
          {camera.effective_read_noise_hcg_e != null && (
            <Field
              label="Read Noise (HCG)"
              value={`${camera.effective_read_noise_hcg_e} e⁻`}
            />
          )}
          {camera.hcg_threshold_gain != null && (
            <Field
              label="HCG Threshold Gain"
              value={camera.hcg_threshold_gain}
            />
          )}
          {camera.effective_full_well_ke != null && (
            <Field
              label="Effective Full Well"
              value={`${camera.effective_full_well_ke} ke⁻`}
            />
          )}
          {camera.effective_peak_qe_pct != null && (
            <Field
              label="Effective Peak QE"
              value={`${camera.effective_peak_qe_pct}%`}
            />
          )}
        </Subsection>
      )}
      {camera.interfaces.length > 0 && (
        <Subsection title="Interfaces">
          <InterfacePills interfaces={camera.interfaces} />
        </Subsection>
      )}
      {camera.notes && <Field label="Notes" value={camera.notes} />}
      <SensorBody sensor={camera.sensor} />
      {camera.guide_sensor && (
        <SensorBody sensor={camera.guide_sensor} label="Built-in Guide Sensor" />
      )}
    </>
  );
}

function FilterPassbandLine({
  p,
}: {
  p: {
    line_name: string | null;
    central_wavelength_nm: number;
    bandwidth_nm: number | null;
    peak_transmission_pct: number | null;
  };
}) {
  const parts: string[] = [];
  parts.push(`${p.central_wavelength_nm.toFixed(1)} nm`);
  if (p.bandwidth_nm != null) parts.push(`${p.bandwidth_nm} nm wide`);
  if (p.peak_transmission_pct != null) parts.push(`${p.peak_transmission_pct}% peak`);
  return (
    <Typography variant="body2" component="div">
      {p.line_name ? <strong>{p.line_name}: </strong> : null}
      {parts.join(" · ")}
    </Typography>
  );
}

function FilterDetailLine({
  filter,
  slotNumber,
}: {
  filter: Filter;
  slotNumber?: number;
}) {
  const sizes = filter.size_options.map((s) => {
    const suffix =
      s.mounted_thickness_mm != null ? ` (${s.mounted_thickness_mm} mm thick)` : "";
    return `${s.filter_size.name}${suffix}`;
  });
  return (
    <Box sx={{ py: 0.5, borderBottom: 1, borderColor: "divider" }}>
      <Typography variant="body2" sx={{ fontWeight: 500 }}>
        {slotNumber != null ? `Slot ${slotNumber}: ` : ""}
        {filter.manufacturer.name} {filter.model_name}
      </Typography>
      <Box sx={{ pl: 2, mt: 0.25 }}>
        <Field label="Type" value={filter.filter_type.display_name ?? filter.filter_type.name} />
        {filter.peak_transmission_pct != null && (
          <Field
            label="Peak Transmission"
            value={`${filter.peak_transmission_pct}%`}
          />
        )}
        {sizes.length > 0 && <Field label="Sizes" value={sizes.join(", ")} />}
        {filter.passbands.length > 0 && (
          <Box sx={{ mt: 0.25 }}>
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ display: "block" }}
            >
              Passbands:
            </Typography>
            <Box sx={{ pl: 1 }}>
              {filter.passbands.map((p) => (
                <FilterPassbandLine key={p.id} p={p} />
              ))}
            </Box>
          </Box>
        )}
        {filter.notes && <Field label="Notes" value={filter.notes} />}
      </Box>
    </Box>
  );
}

function FiltrationBody({
  wheel,
  slots,
  singleFilter,
}: {
  wheel: FilterWheel | null;
  slots: { slotNumber: number; filter: Filter | null }[];
  singleFilter: Filter | null;
}) {
  return (
    <>
      {wheel ? (
        <Subsection title="Filter Wheel">
          <Field
            label="Model"
            value={`${wheel.manufacturer.name} ${wheel.model_name}`}
          />
          <Field label="Positions" value={wheel.num_positions} />
          {wheel.filter_size && (
            <Field label="Filter Size" value={wheel.filter_size.name} />
          )}
          {wheel.camera_side_connector && (
            <Field
              label="Camera-side Connector"
              value={wheel.camera_side_connector.name}
            />
          )}
          {wheel.telescope_side_connector && (
            <Field
              label="Scope-side Connector"
              value={wheel.telescope_side_connector.name}
            />
          )}
          {wheel.back_focus_contribution_mm != null && (
            <Field
              label="Back Focus Contribution"
              value={`${wheel.back_focus_contribution_mm} mm`}
            />
          )}
          {wheel.interfaces.length > 0 && (
            <Field
              label="Interfaces"
              value={<InterfacePills interfaces={wheel.interfaces} />}
            />
          )}
          {wheel.notes && <Field label="Notes" value={wheel.notes} />}
        </Subsection>
      ) : null}

      {slots.length > 0 && (
        <Subsection title="Slots">
          {slots.map((s) =>
            s.filter ? (
              <FilterDetailLine
                key={s.slotNumber}
                filter={s.filter}
                slotNumber={s.slotNumber}
              />
            ) : (
              <Typography
                key={s.slotNumber}
                variant="body2"
                color="text.secondary"
              >
                Slot {s.slotNumber}: (loading...)
              </Typography>
            ),
          )}
        </Subsection>
      )}

      {singleFilter && (
        <Subsection title="Single Filter">
          <FilterDetailLine filter={singleFilter} />
        </Subsection>
      )}
    </>
  );
}

function GuideSystemBody({
  oag,
  guideScope,
  guideCamera,
}: {
  oag: Oag | null;
  guideScope: GuideScope | null;
  guideCamera: Camera | null;
}) {
  return (
    <>
      {oag && (
        <Subsection title="Off-Axis Guider">
          <Field
            label="Model"
            value={`${oag.manufacturer.name} ${oag.model_name}`}
          />
          {oag.prism_size_mm != null && (
            <Field label="Prism Size" value={`${oag.prism_size_mm} mm`} />
          )}
          {oag.back_focus_contribution_mm != null && (
            <Field
              label="Back Focus Contribution"
              value={`${oag.back_focus_contribution_mm} mm`}
            />
          )}
          {oag.weight_g != null && (
            <Field label="Weight" value={`${oag.weight_g} g`} />
          )}
          {oag.imaging_side_connector && (
            <Field
              label="Imaging-side Connector"
              value={oag.imaging_side_connector.name}
            />
          )}
          {oag.guide_camera_connector && (
            <Field
              label="Guide Camera Connector"
              value={oag.guide_camera_connector.name}
            />
          )}
          {oag.notes && <Field label="Notes" value={oag.notes} />}
        </Subsection>
      )}
      {guideScope && (
        <Subsection title="Guide Scope">
          <Field
            label="Model"
            value={`${guideScope.manufacturer.name} ${guideScope.model_name}`}
          />
          {guideScope.aperture_mm != null && (
            <Field label="Aperture" value={`${guideScope.aperture_mm} mm`} />
          )}
          {guideScope.focal_length_mm != null && (
            <Field label="Focal Length" value={`${guideScope.focal_length_mm} mm`} />
          )}
          {guideScope.aperture_mm != null && guideScope.focal_length_mm != null && (
            <Field
              label="Focal Ratio"
              value={`f/${(guideScope.focal_length_mm / guideScope.aperture_mm).toFixed(1)}`}
            />
          )}
          {guideScope.weight_g != null && (
            <Field label="Weight" value={`${guideScope.weight_g} g`} />
          )}
          {guideScope.guide_camera_connector && (
            <Field
              label="Guide Camera Connector"
              value={guideScope.guide_camera_connector.name}
            />
          )}
          {guideScope.notes && <Field label="Notes" value={guideScope.notes} />}
        </Subsection>
      )}
      {guideCamera && (
        <Subsection title="Guide Camera">
          <CameraBody camera={guideCamera} />
        </Subsection>
      )}
    </>
  );
}

function MountBody({ mount }: { mount: Mount }) {
  return (
    <>
      <Field
        label="Model"
        value={`${mount.manufacturer.name} ${mount.model_name}`}
      />
      {mount.mount_type && (
        <Field label="Type" value={mount.mount_type.name} />
      )}
      {mount.payload_capacity_kg != null && (
        <Field
          label="Payload Capacity"
          value={`${mount.payload_capacity_kg} kg`}
        />
      )}
      {mount.mount_weight_kg != null && (
        <Field label="Mount Weight" value={`${mount.mount_weight_kg} kg`} />
      )}
      <Field
        label="Counterweight Required"
        value={mount.counterweight_required ? "Yes" : "No"}
      />
      <Field label="GoTo" value={mount.goto_capable ? "Yes" : "No"} />
      {mount.periodic_error_arcsec != null && (
        <Field
          label="Periodic Error"
          value={`${mount.periodic_error_arcsec}″`}
        />
      )}
      {mount.drive_type && <Field label="Drive Type" value={mount.drive_type} />}
      {mount.interfaces.length > 0 && (
        <Field
          label="Interfaces"
          value={<InterfacePills interfaces={mount.interfaces} />}
        />
      )}
      {mount.notes && <Field label="Notes" value={mount.notes} />}
    </>
  );
}

function FocuserBody({ focuser }: { focuser: Focuser }) {
  return (
    <>
      <Field
        label="Model"
        value={`${focuser.manufacturer.name} ${focuser.model_name}`}
      />
      {focuser.focuser_type && (
        <Field label="Type" value={focuser.focuser_type.name} />
      )}
      <Field label="Motorized" value={focuser.motorized ? "Yes" : "No"} />
      {focuser.travel_range_mm != null && (
        <Field label="Travel" value={`${focuser.travel_range_mm} mm`} />
      )}
      {focuser.step_size_um != null && (
        <Field label="Step Size" value={`${focuser.step_size_um} µm`} />
      )}
      {focuser.total_steps != null && (
        <Field label="Total Steps" value={focuser.total_steps} />
      )}
      <Field
        label="Temp Compensation"
        value={focuser.temperature_compensation ? "Yes" : "No"}
      />
      {focuser.backlash_steps != null && (
        <Field label="Backlash" value={`${focuser.backlash_steps} steps`} />
      )}
      {focuser.interfaces.length > 0 && (
        <Field
          label="Interfaces"
          value={<InterfacePills interfaces={focuser.interfaces} />}
        />
      )}
      {focuser.notes && <Field label="Notes" value={focuser.notes} />}
    </>
  );
}

function ComputingBody({
  computer,
  software,
}: {
  computer: Computer | null;
  software: { id: number; name: string; category: string }[];
}) {
  return (
    <>
      {computer && (
        <Subsection title="Computer">
          <Field
            label="Model"
            value={`${computer.manufacturer.name} ${computer.model_name}`}
          />
          {computer.form_factor && (
            <Field label="Form Factor" value={computer.form_factor.name} />
          )}
          {computer.notes && <Field label="Notes" value={computer.notes} />}
        </Subsection>
      )}
      {software.length > 0 && (
        <Subsection title="Software">
          {software.map((s) => (
            <Field key={s.id} label={s.category} value={s.name} />
          ))}
        </Subsection>
      )}
    </>
  );
}
