import { useMemo, useState } from "react";
import { useQueries, useQuery } from "@tanstack/react-query";
import { SimpleTreeView } from "@mui/x-tree-view/SimpleTreeView";
import { TreeItem } from "@mui/x-tree-view/TreeItem";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
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
  // ── Data fetching ─────────────────────────────────────────────────────────

  const { data: telescope, isLoading: tLoading } = useQuery({
    queryKey: ["rig-equipment", "telescope", rig.telescope_id],
    queryFn: async (): Promise<{
      telescope: Telescope;
      config: TelescopeConfiguration;
    }> => {
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

  const filterIdsOrdered: Array<{ id: number; slot: number | null }> = [];
  for (const slot of rig.filter_slots) {
    filterIdsOrdered.push({ id: slot.filter_id, slot: slot.slot_number });
  }
  if (rig.single_filter_id != null) {
    filterIdsOrdered.push({ id: rig.single_filter_id, slot: null });
  }

  const filterQueries = useQueries({
    queries: filterIdsOrdered.map(({ id }) => ({
      queryKey: ["rig-equipment", "filter", id],
      queryFn: () => fetchFilter(id),
    })),
  });
  const filtersById = useMemo(() => {
    const map = new Map<number, Filter>();
    for (const q of filterQueries) {
      if (q.data) map.set(q.data.id, q.data);
    }
    return map;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterQueries.map((q) => q.data?.id ?? -1).join(",")]);

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

  // ── Tree model ────────────────────────────────────────────────────────────

  const hasSummary = Boolean(rig.description || rig.notes);
  const hasMultipleCameras = camera != null && guideCamera != null;

  const tree = useMemo(
    () => buildTree({ rig, camera, guideCamera, filtersById, hasSummary, hasMultipleCameras }),
    [rig, camera, guideCamera, filtersById, hasSummary, hasMultipleCameras],
  );

  const [selectedId, setSelectedId] = useState<string>(
    hasSummary ? "summary" : `camera:${rig.camera_id}`,
  );

  const coreLoading = tLoading || cLoading;

  // ── Render ────────────────────────────────────────────────────────────────

  if (coreLoading) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", py: 4 }}>
        <CircularProgress size={28} />
      </Box>
    );
  }

  return (
    <Box
      sx={{
        display: "flex",
        flexDirection: { xs: "column", md: "row" },
        gap: 2,
        alignItems: "stretch",
      }}
    >
      <Box
        sx={{
          width: { xs: "100%", md: 280 },
          flexShrink: 0,
          borderRight: { md: 1 },
          borderBottom: { xs: 1, md: 0 },
          borderColor: "divider",
          pr: { md: 1 },
          pb: { xs: 1, md: 0 },
          maxHeight: { md: "70vh" },
          overflowY: { md: "auto" },
        }}
      >
        <SimpleTreeView
          selectedItems={selectedId}
          onSelectedItemsChange={(_event, itemId) => {
            if (typeof itemId === "string" && !itemId.startsWith("group-")) {
              setSelectedId(itemId);
            }
          }}
          defaultExpandedItems={tree.defaultExpanded}
        >
          {tree.nodes}
        </SimpleTreeView>
      </Box>

      <Box sx={{ flex: 1, minWidth: 0 }}>
        <DetailPane
          selectedId={selectedId}
          rig={rig}
          telescope={telescope}
          camera={camera}
          guideCamera={guideCamera}
          filterWheel={filterWheel}
          filtersById={filtersById}
          mount={mount}
          focuser={focuser}
          oag={oag}
          guideScope={guideScope}
          computer={computer}
        />
      </Box>
    </Box>
  );
}

// ── Tree construction ──────────────────────────────────────────────────────

interface BuildTreeArgs {
  rig: Rig;
  camera: Camera | undefined;
  guideCamera: Camera | undefined;
  filtersById: Map<number, Filter>;
  hasSummary: boolean;
  hasMultipleCameras: boolean;
}

function buildTree(args: BuildTreeArgs) {
  const { rig, camera, guideCamera, filtersById, hasSummary, hasMultipleCameras } = args;
  const defaultExpanded: string[] = [
    "group-imaging",
    "group-optics",
    "group-tracking",
    "group-accessories",
    "group-computing",
  ];

  const nodes: React.ReactNode[] = [];

  if (hasSummary) {
    nodes.push(<TreeItem key="summary" itemId="summary" label="Summary" />);
  }

  // Imaging
  const imaging: React.ReactNode[] = [];
  if (hasMultipleCameras) {
    const cameras: React.ReactNode[] = [];
    if (camera) {
      cameras.push(
        <TreeItem
          key={`camera:${rig.camera_id}`}
          itemId={`camera:${rig.camera_id}`}
          label={`Imaging: ${camera.manufacturer.name} ${camera.model_name}`}
        />,
      );
    }
    if (guideCamera) {
      cameras.push(
        <TreeItem
          key={`camera:${rig.guide_camera_id}`}
          itemId={`camera:${rig.guide_camera_id}`}
          label={`Guide: ${guideCamera.manufacturer.name} ${guideCamera.model_name}`}
        />,
      );
    }
    imaging.push(
      <TreeItem key="group-cameras" itemId="group-cameras" label="Cameras">
        {cameras}
      </TreeItem>,
    );
    defaultExpanded.push("group-cameras");
  } else if (camera) {
    imaging.push(
      <TreeItem
        key={`camera:${rig.camera_id}`}
        itemId={`camera:${rig.camera_id}`}
        label={`Camera: ${camera.manufacturer.name} ${camera.model_name}`}
      />,
    );
  } else if (guideCamera) {
    imaging.push(
      <TreeItem
        key={`camera:${rig.guide_camera_id}`}
        itemId={`camera:${rig.guide_camera_id}`}
        label={`Guide Camera: ${guideCamera.manufacturer.name} ${guideCamera.model_name}`}
      />,
    );
  }
  if (imaging.length > 0) {
    nodes.push(
      <TreeItem key="group-imaging" itemId="group-imaging" label={<GroupLabel>Imaging</GroupLabel>}>
        {imaging}
      </TreeItem>,
    );
  }

  // Optics
  const optics: React.ReactNode[] = [];
  optics.push(
    <TreeItem
      key={`telescope:${rig.telescope_id}`}
      itemId={`telescope:${rig.telescope_id}`}
      label={`OTA: ${rig.telescope_name}`}
    />,
  );

  const filterEntries: Array<{ filter: Filter; slotNumber: number | null }> = [];
  for (const slot of rig.filter_slots) {
    const f = filtersById.get(slot.filter_id);
    if (f) filterEntries.push({ filter: f, slotNumber: slot.slot_number });
  }
  if (rig.single_filter_id != null) {
    const f = filtersById.get(rig.single_filter_id);
    if (f) filterEntries.push({ filter: f, slotNumber: null });
  }

  if (filterEntries.length > 0) {
    optics.push(
      <TreeItem key="group-filters" itemId="group-filters" label="Filters">
        {filterEntries.map(({ filter, slotNumber }) => (
          <TreeItem
            key={`filter:${filter.id}`}
            itemId={`filter:${filter.id}`}
            label={
              slotNumber != null
                ? `Slot ${slotNumber}: ${filter.model_name}`
                : filter.model_name
            }
          />
        ))}
      </TreeItem>,
    );
    defaultExpanded.push("group-filters");
  }

  nodes.push(
    <TreeItem key="group-optics" itemId="group-optics" label={<GroupLabel>Optics</GroupLabel>}>
      {optics}
    </TreeItem>,
  );

  // Tracking
  if (rig.mount_id) {
    nodes.push(
      <TreeItem
        key="group-tracking"
        itemId="group-tracking"
        label={<GroupLabel>Tracking</GroupLabel>}
      >
        <TreeItem
          key={`mount:${rig.mount_id}`}
          itemId={`mount:${rig.mount_id}`}
          label={`Mount: ${rig.mount_name}`}
        />
      </TreeItem>,
    );
  }

  // Accessories
  const accessories: React.ReactNode[] = [];
  if (rig.focuser_id) {
    accessories.push(
      <TreeItem
        key={`focuser:${rig.focuser_id}`}
        itemId={`focuser:${rig.focuser_id}`}
        label={`Focuser: ${rig.focuser_name}`}
      />,
    );
  }
  if (rig.filter_wheel_id) {
    accessories.push(
      <TreeItem
        key={`filter-wheel:${rig.filter_wheel_id}`}
        itemId={`filter-wheel:${rig.filter_wheel_id}`}
        label={`Filter Wheel: ${rig.filter_wheel_name}`}
      />,
    );
  }
  if (rig.oag_id) {
    accessories.push(
      <TreeItem
        key={`oag:${rig.oag_id}`}
        itemId={`oag:${rig.oag_id}`}
        label={`OAG: ${rig.oag_name}`}
      />,
    );
  }
  if (rig.guide_scope_id) {
    accessories.push(
      <TreeItem
        key={`guide-scope:${rig.guide_scope_id}`}
        itemId={`guide-scope:${rig.guide_scope_id}`}
        label={`Guide Scope: ${rig.guide_scope_name}`}
      />,
    );
  }
  if (accessories.length > 0) {
    nodes.push(
      <TreeItem
        key="group-accessories"
        itemId="group-accessories"
        label={<GroupLabel>Accessories</GroupLabel>}
      >
        {accessories}
      </TreeItem>,
    );
  }

  // Computing
  const computing: React.ReactNode[] = [];
  if (rig.computer_id) {
    computing.push(
      <TreeItem
        key={`computer:${rig.computer_id}`}
        itemId={`computer:${rig.computer_id}`}
        label={`Computer: ${rig.computer_name}`}
      />,
    );
  }
  if (rig.software.length === 1) {
    computing.push(
      <TreeItem
        key={`software:${rig.software[0].id}`}
        itemId={`software:${rig.software[0].id}`}
        label={`Software: ${rig.software[0].name}`}
      />,
    );
  } else if (rig.software.length > 1) {
    computing.push(
      <TreeItem key="group-software" itemId="group-software" label="Software">
        {rig.software.map((s) => (
          <TreeItem
            key={`software:${s.id}`}
            itemId={`software:${s.id}`}
            label={s.name}
          />
        ))}
      </TreeItem>,
    );
    defaultExpanded.push("group-software");
  }
  if (computing.length > 0) {
    nodes.push(
      <TreeItem
        key="group-computing"
        itemId="group-computing"
        label={<GroupLabel>Computing</GroupLabel>}
      >
        {computing}
      </TreeItem>,
    );
  }

  return { nodes, defaultExpanded };
}

function GroupLabel({ children }: { children: React.ReactNode }) {
  return (
    <Typography
      variant="caption"
      fontWeight={700}
      sx={{
        textTransform: "uppercase",
        letterSpacing: 0.8,
        color: "text.secondary",
      }}
    >
      {children}
    </Typography>
  );
}

// ── Detail pane dispatch ───────────────────────────────────────────────────

interface DetailPaneProps {
  selectedId: string;
  rig: Rig;
  telescope: { telescope: Telescope; config: TelescopeConfiguration } | undefined;
  camera: Camera | undefined;
  guideCamera: Camera | undefined;
  filterWheel: FilterWheel | undefined;
  filtersById: Map<number, Filter>;
  mount: Mount | undefined;
  focuser: Focuser | undefined;
  oag: Oag | undefined;
  guideScope: GuideScope | undefined;
  computer: Computer | undefined;
}

function DetailPane(props: DetailPaneProps) {
  const { selectedId, rig } = props;

  if (selectedId === "summary") {
    return (
      <DetailWrapper title="Summary">
        {rig.description && (
          <Field label="Description" value={rig.description} />
        )}
        {rig.notes && (
          <Box sx={{ mt: 1 }}>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>
              Notes
            </Typography>
            <Typography
              variant="body2"
              sx={{ whiteSpace: "pre-wrap", color: "text.secondary" }}
            >
              {rig.notes}
            </Typography>
          </Box>
        )}
      </DetailWrapper>
    );
  }

  const [kind, idStr] = selectedId.split(":");
  const id = Number(idStr);

  if (kind === "telescope" && props.telescope) {
    return (
      <DetailWrapper
        title={`${props.telescope.telescope.manufacturer.name} ${props.telescope.telescope.model_name}`}
        subtitle={props.telescope.config.config_name}
      >
        <OpticalTrainBody
          telescope={props.telescope.telescope}
          config={props.telescope.config}
          allConfigs={props.telescope.telescope.configurations}
        />
      </DetailWrapper>
    );
  }
  if (kind === "camera") {
    const cam =
      id === rig.camera_id ? props.camera : id === rig.guide_camera_id ? props.guideCamera : undefined;
    const role = id === rig.guide_camera_id ? "Guide Camera" : "Imaging Camera";
    if (cam) {
      return (
        <DetailWrapper title={`${cam.manufacturer.name} ${cam.model_name}`} subtitle={role}>
          <CameraBody camera={cam} />
        </DetailWrapper>
      );
    }
  }
  if (kind === "filter") {
    const f = props.filtersById.get(id);
    if (f) {
      const slot = rig.filter_slots.find((s) => s.filter_id === id);
      const subtitle =
        slot != null
          ? `Slot ${slot.slot_number}`
          : rig.single_filter_id === id
          ? "Single filter"
          : undefined;
      return (
        <DetailWrapper
          title={`${f.manufacturer.name} ${f.model_name}`}
          subtitle={subtitle}
        >
          <FilterBody filter={f} />
        </DetailWrapper>
      );
    }
  }
  if (kind === "filter-wheel" && props.filterWheel) {
    return (
      <DetailWrapper
        title={`${props.filterWheel.manufacturer.name} ${props.filterWheel.model_name}`}
      >
        <FilterWheelBody wheel={props.filterWheel} />
      </DetailWrapper>
    );
  }
  if (kind === "mount" && props.mount) {
    return (
      <DetailWrapper title={`${props.mount.manufacturer.name} ${props.mount.model_name}`}>
        <MountBody mount={props.mount} />
      </DetailWrapper>
    );
  }
  if (kind === "focuser" && props.focuser) {
    return (
      <DetailWrapper title={`${props.focuser.manufacturer.name} ${props.focuser.model_name}`}>
        <FocuserBody focuser={props.focuser} />
      </DetailWrapper>
    );
  }
  if (kind === "oag" && props.oag) {
    return (
      <DetailWrapper title={`${props.oag.manufacturer.name} ${props.oag.model_name}`}>
        <OagBody oag={props.oag} />
      </DetailWrapper>
    );
  }
  if (kind === "guide-scope" && props.guideScope) {
    return (
      <DetailWrapper title={`${props.guideScope.manufacturer.name} ${props.guideScope.model_name}`}>
        <GuideScopeBody guideScope={props.guideScope} />
      </DetailWrapper>
    );
  }
  if (kind === "computer" && props.computer) {
    return (
      <DetailWrapper title={`${props.computer.manufacturer.name} ${props.computer.model_name}`}>
        <ComputerBody computer={props.computer} />
      </DetailWrapper>
    );
  }
  if (kind === "software") {
    const sw = rig.software.find((s) => s.id === id);
    if (sw) {
      return (
        <DetailWrapper title={sw.name} subtitle={sw.category}>
          <Typography variant="body2" color="text.secondary">
            No additional details available.
          </Typography>
        </DetailWrapper>
      );
    }
  }

  return (
    <DetailWrapper title="Loading…">
      <CircularProgress size={20} />
    </DetailWrapper>
  );
}

function DetailWrapper({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <Box
      sx={{
        px: { xs: 0, md: 2 },
        maxHeight: { md: "70vh" },
        overflowY: { md: "auto" },
      }}
    >
      <Typography variant="h6" sx={{ mb: subtitle ? 0.25 : 1 }}>
        {title}
      </Typography>
      {subtitle && (
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
          {subtitle}
        </Typography>
      )}
      <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
        {children}
      </Box>
    </Box>
  );
}

// ── Shared atoms ───────────────────────────────────────────────────────────

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  if (value === null || value === undefined || value === "") return null;
  return (
    <Box sx={{ display: "flex", gap: 1 }}>
      <Typography
        variant="body2"
        color="text.secondary"
        sx={{ minWidth: 170, flexShrink: 0 }}
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
    <Box sx={{ mt: 1 }}>
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

// ── Detail bodies ──────────────────────────────────────────────────────────

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
      <Field label="Aperture" value={`${telescope.aperture_mm} mm`} />
      <Field label="Optical Design" value={telescope.optical_design?.name ?? null} />
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
        value={telescope.obstruction_pct != null ? `${telescope.obstruction_pct}%` : null}
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
        {config.accessory_name && <Field label="Accessory" value={config.accessory_name} />}
        <Field label="Focal Length" value={`${config.effective_focal_length_mm} mm`} />
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
          <Field label="Back Focus Target" value={`${config.effective_back_focus_mm} mm`} />
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
      {sensor.bayer_pattern && <Field label="Bayer Pattern" value={sensor.bayer_pattern} />}
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
        <Field label="Full Well" value={`${sensor.full_well_capacity_ke} ke⁻`} />
      )}
      {sensor.read_noise_e != null && (
        <Field label="Read Noise" value={`${sensor.read_noise_e} e⁻`} />
      )}
      {sensor.peak_qe_pct != null && <Field label="Peak QE" value={`${sensor.peak_qe_pct}%`} />}
      <Field label="Dual Gain" value={sensor.dual_gain ? "Yes" : "No"} />
      {sensor.notes && <Field label="Notes" value={sensor.notes} />}
    </Subsection>
  );
}

function CameraBody({ camera }: { camera: Camera }) {
  return (
    <>
      <Field label="Cooled" value={camera.cooled ? "Yes" : "No"} />
      {camera.cooling_delta_c != null && (
        <Field label="Cooling Delta" value={`Δ${camera.cooling_delta_c}°C`} />
      )}
      {camera.back_focus_mm != null && (
        <Field label="Back Focus" value={`${camera.back_focus_mm} mm`} />
      )}
      {camera.weight_g != null && <Field label="Weight" value={`${camera.weight_g} g`} />}
      <Field label="Tilt Adapter" value={camera.tilt_adapter ? "Yes" : "No"} />
      <Field label="USB Hub" value={camera.has_usb_hub ? "Yes" : "No"} />
      {camera.usb_hub_interface && (
        <Field label="USB Hub Interface" value={camera.usb_hub_interface.name} />
      )}
      {camera.connector_size && <Field label="Connector" value={camera.connector_size.name} />}
      {camera.unity_gain != null && <Field label="Unity Gain" value={camera.unity_gain} />}
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
            <Field label="HCG Threshold Gain" value={camera.hcg_threshold_gain} />
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

function FilterBody({ filter }: { filter: Filter }) {
  const sizes = filter.size_options.map((s) => {
    const suffix =
      s.mounted_thickness_mm != null ? ` (${s.mounted_thickness_mm} mm thick)` : "";
    return `${s.filter_size.name}${suffix}`;
  });
  return (
    <>
      <Field
        label="Type"
        value={filter.filter_type.display_name ?? filter.filter_type.name}
      />
      {filter.peak_transmission_pct != null && (
        <Field label="Peak Transmission" value={`${filter.peak_transmission_pct}%`} />
      )}
      {sizes.length > 0 && <Field label="Sizes" value={sizes.join(", ")} />}
      {filter.passbands.length > 0 && (
        <Subsection title="Passbands">
          {filter.passbands.map((p) => {
            const parts: string[] = [];
            parts.push(`${p.central_wavelength_nm.toFixed(1)} nm`);
            if (p.bandwidth_nm != null) parts.push(`${p.bandwidth_nm} nm wide`);
            if (p.peak_transmission_pct != null) parts.push(`${p.peak_transmission_pct}% peak`);
            return (
              <Typography key={p.id} variant="body2">
                {p.line_name ? <strong>{p.line_name}: </strong> : null}
                {parts.join(" · ")}
              </Typography>
            );
          })}
        </Subsection>
      )}
      {filter.notes && <Field label="Notes" value={filter.notes} />}
    </>
  );
}

function FilterWheelBody({ wheel }: { wheel: FilterWheel }) {
  return (
    <>
      <Field label="Positions" value={wheel.num_positions} />
      {wheel.filter_size && <Field label="Filter Size" value={wheel.filter_size.name} />}
      {wheel.camera_side_connector && (
        <Field label="Camera-side Connector" value={wheel.camera_side_connector.name} />
      )}
      {wheel.telescope_side_connector && (
        <Field label="Scope-side Connector" value={wheel.telescope_side_connector.name} />
      )}
      {wheel.back_focus_contribution_mm != null && (
        <Field
          label="Back Focus Contribution"
          value={`${wheel.back_focus_contribution_mm} mm`}
        />
      )}
      {wheel.interfaces.length > 0 && (
        <Field label="Interfaces" value={<InterfacePills interfaces={wheel.interfaces} />} />
      )}
      {wheel.notes && <Field label="Notes" value={wheel.notes} />}
    </>
  );
}

function MountBody({ mount }: { mount: Mount }) {
  return (
    <>
      {mount.mount_type && <Field label="Type" value={mount.mount_type.name} />}
      {mount.payload_capacity_kg != null && (
        <Field label="Payload Capacity" value={`${mount.payload_capacity_kg} kg`} />
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
        <Field label="Periodic Error" value={`${mount.periodic_error_arcsec}″`} />
      )}
      {mount.drive_type && <Field label="Drive Type" value={mount.drive_type} />}
      {mount.interfaces.length > 0 && (
        <Field label="Interfaces" value={<InterfacePills interfaces={mount.interfaces} />} />
      )}
      {mount.notes && <Field label="Notes" value={mount.notes} />}
    </>
  );
}

function FocuserBody({ focuser }: { focuser: Focuser }) {
  return (
    <>
      {focuser.focuser_type && <Field label="Type" value={focuser.focuser_type.name} />}
      <Field label="Motorized" value={focuser.motorized ? "Yes" : "No"} />
      {focuser.travel_range_mm != null && (
        <Field label="Travel" value={`${focuser.travel_range_mm} mm`} />
      )}
      {focuser.step_size_um != null && (
        <Field label="Step Size" value={`${focuser.step_size_um} µm`} />
      )}
      {focuser.total_steps != null && <Field label="Total Steps" value={focuser.total_steps} />}
      <Field
        label="Temp Compensation"
        value={focuser.temperature_compensation ? "Yes" : "No"}
      />
      {focuser.backlash_steps != null && (
        <Field label="Backlash" value={`${focuser.backlash_steps} steps`} />
      )}
      {focuser.interfaces.length > 0 && (
        <Field label="Interfaces" value={<InterfacePills interfaces={focuser.interfaces} />} />
      )}
      {focuser.notes && <Field label="Notes" value={focuser.notes} />}
    </>
  );
}

function OagBody({ oag }: { oag: Oag }) {
  return (
    <>
      {oag.prism_size_mm != null && (
        <Field label="Prism Size" value={`${oag.prism_size_mm} mm`} />
      )}
      {oag.back_focus_contribution_mm != null && (
        <Field
          label="Back Focus Contribution"
          value={`${oag.back_focus_contribution_mm} mm`}
        />
      )}
      {oag.weight_g != null && <Field label="Weight" value={`${oag.weight_g} g`} />}
      {oag.imaging_side_connector && (
        <Field label="Imaging-side Connector" value={oag.imaging_side_connector.name} />
      )}
      {oag.guide_camera_connector && (
        <Field label="Guide Camera Connector" value={oag.guide_camera_connector.name} />
      )}
      {oag.notes && <Field label="Notes" value={oag.notes} />}
    </>
  );
}

function GuideScopeBody({ guideScope }: { guideScope: GuideScope }) {
  return (
    <>
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
      {guideScope.weight_g != null && <Field label="Weight" value={`${guideScope.weight_g} g`} />}
      {guideScope.guide_camera_connector && (
        <Field
          label="Guide Camera Connector"
          value={guideScope.guide_camera_connector.name}
        />
      )}
      {guideScope.notes && <Field label="Notes" value={guideScope.notes} />}
    </>
  );
}

function ComputerBody({ computer }: { computer: Computer }) {
  return (
    <>
      {computer.form_factor && (
        <Field label="Form Factor" value={computer.form_factor.name} />
      )}
      {computer.notes && <Field label="Notes" value={computer.notes} />}
    </>
  );
}
