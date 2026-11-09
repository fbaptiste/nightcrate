import { useMemo, useState } from "react";
import Autocomplete from "@mui/material/Autocomplete";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import TextField from "@mui/material/TextField";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";
import { orderSoftwareOptions } from "@/components/shared/softwareOrder";
import { formatSnakeCase } from "@/lib/formUtils";
import type {
  CameraOption,
  EquipmentOptions,
  FilterOption,
  FilterWheelOption,
  GuideScopeOption,
  RigParts,
  RigPartsInput,
  SimpleOption,
  SoftwareOption,
  TelescopeConfigOption,
} from "@/api/rigs";
import {
  keepRetiredSelected,
  retainedGroup,
  retainedLabel,
  type RetainedOption,
} from "@/components/rigs/retainedOptions";

interface RigPartsFormProps {
  value: RigPartsInput;
  base?: RigPartsInput;
  onChange: (value: RigPartsInput) => void;
  options: EquipmentOptions;
  partSources?: PartsSource[];
}

type PartsSource = Omit<RigParts, "software_ids"> & {
  software_ids?: number[];
  filter_wheel_positions?: number | null;
  guide_scope_focal_length_mm?: number | null;
};

type GuidingMode = "none" | "oag" | "guide_scope";

interface FlatConfigOption extends TelescopeConfigOption {
  telescope_name: string;
  manufacturer_name: string;
}

type PartGroup =
  | "telescope"
  | "camera"
  | "filters"
  | "mount"
  | "focuser"
  | "guider"
  | "guide_camera"
  | "computer"
  | "software";

const GROUP_FIELDS: Record<PartGroup, (keyof RigPartsInput)[]> = {
  telescope: ["telescope_configuration_id"],
  camera: ["camera_id"],
  filters: ["filter_wheel_id", "single_filter_id", "filter_slots"],
  mount: ["mount_id"],
  focuser: ["focuser_id"],
  guider: ["oag_id", "guide_scope_id"],
  guide_camera: ["guide_camera_id"],
  computer: ["computer_id"],
  software: ["software_ids"],
};

function normalized(field: keyof RigPartsInput, fieldValue: unknown): unknown {
  if (field === "software_ids") return [...((fieldValue as number[] | undefined) ?? [])].sort();
  if (field === "filter_slots") {
    return [...((fieldValue as { slot_number: number; filter_id: number }[] | undefined) ?? [])]
      .map(({ slot_number, filter_id }) => ({ slot_number, filter_id }))
      .sort((a, b) => a.slot_number - b.slot_number || a.filter_id - b.filter_id);
  }
  return fieldValue ?? null;
}

function groupChanged(value: RigPartsInput, base: RigPartsInput, group: PartGroup): boolean {
  return GROUP_FIELDS[group].some(
    (field) => JSON.stringify(normalized(field, value[field])) !== JSON.stringify(normalized(field, base[field])),
  );
}

function sortByManufacturer<T extends { manufacturer_name: string; model_name?: string }>(
  options: T[],
): T[] {
  return [...options].sort((a, b) => {
    const manufacturer = a.manufacturer_name.localeCompare(b.manufacturer_name, undefined, {
      sensitivity: "base",
    });
    if (manufacturer !== 0) return manufacturer;
    return (a.model_name ?? "").localeCompare(b.model_name ?? "", undefined, {
      sensitivity: "base",
    });
  });
}

function simpleLabel(option: RetainedOption<SimpleOption>): string {
  return retainedLabel(
    option,
    `${option.manufacturer_name} — ${option.model_name}`,
    option.model_name,
  );
}

function optionGroup(option: { retired?: true; manufacturer_name: string }): string {
  return retainedGroup(option, option.manufacturer_name);
}

function retainedSimpleOption(
  partSources: PartsSource[],
  id: number,
  idKey: "mount_id" | "focuser_id" | "oag_id" | "computer_id",
  nameKey: "mount_name" | "focuser_name" | "oag_name" | "computer_name",
): SimpleOption | null {
  const source = partSources.find((parts) => parts[idKey] === id);
  const name = source?.[nameKey];
  return name ? { id, model_name: name, manufacturer_name: "", is_mine: false } : null;
}

function modeFromParts(parts: RigPartsInput): GuidingMode {
  if (parts.oag_id) return "oag";
  if (parts.guide_scope_id) return "guide_scope";
  return "none";
}

function ProjectTag() {
  return (
    <Box
      component="span"
      sx={(theme) => ({
        display: "inline-flex",
        alignItems: "center",
        height: "20px",
        px: "8px",
        borderRadius: "10px",
        bgcolor: theme.palette.mode === "dark" ? "#4db6ac" : "#00695c",
        color: theme.palette.mode === "dark" ? "#10201e" : "#ffffff",
        fontSize: "12px",
        lineHeight: "20px",
        fontWeight: 600,
        whiteSpace: "nowrap",
      })}
    >
      for this project
    </Box>
  );
}

function FilterSlots({
  count,
  filters,
  slots,
  onChange,
}: {
  count: number;
  filters: RetainedOption<FilterOption>[];
  slots: { slot_number: number; filter_id: number }[];
  onChange: (slots: { slot_number: number; filter_id: number }[]) => void;
}) {
  return (
    <Box sx={{ display: "grid", gap: 1 }}>
      {Array.from({ length: count }, (_, index) => {
        const slotNumber = index + 1;
        const selected = slots.find((slot) => slot.slot_number === slotNumber);
        return (
          <Box key={slotNumber} sx={{ display: "flex", alignItems: "center", gap: 1 }}>
            <Typography sx={{ width: 48, textAlign: "right", fontSize: "13px" }}>
              {slotNumber}
            </Typography>
            <Autocomplete<RetainedOption<FilterOption>>
              size="small"
              options={filters}
              groupBy={optionGroup}
              getOptionLabel={(option) => retainedLabel(
                option,
                `${option.manufacturer_name} — ${option.model_name}`,
                option.model_name,
              )}
              value={filters.find((option) => option.id === selected?.filter_id) ?? null}
              onChange={(_event, option) => {
                const next = slots.filter((slot) => slot.slot_number !== slotNumber);
                if (option) next.push({ slot_number: slotNumber, filter_id: option.id });
                onChange(next.sort((a, b) => a.slot_number - b.slot_number));
              }}
              isOptionEqualToValue={(option, current) => option.id === current.id}
              renderInput={(params) => <TextField {...params} placeholder="Select filter" />}
              sx={{ flex: 1 }}
            />
          </Box>
        );
      })}
    </Box>
  );
}

export default function RigPartsForm({
  value,
  base,
  onChange,
  options,
  partSources = [],
}: RigPartsFormProps) {
  const [selectedGuidingMode, setSelectedGuidingMode] = useState<GuidingMode>(() =>
    modeFromParts(value),
  );
  const configs = useMemo<RetainedOption<FlatConfigOption>[]>(
    () => {
      const active = options.telescopes
        .flatMap((telescope) =>
          telescope.configs.map((config) => ({
            ...config,
            telescope_name: telescope.telescope_name,
            manufacturer_name: telescope.manufacturer_name,
          })),
        )
        .sort((a, b) => {
          const manufacturer = a.manufacturer_name.localeCompare(b.manufacturer_name, undefined, {
            sensitivity: "base",
          });
          if (manufacturer !== 0) return manufacturer;
          return `${a.telescope_name} ${a.config_name}`.localeCompare(
            `${b.telescope_name} ${b.config_name}`,
            undefined,
            { sensitivity: "base" },
          );
        });
      return keepRetiredSelected(active, [value.telescope_configuration_id], (id) => {
        const source = partSources.find((parts) => parts.telescope_configuration_id === id);
        if (!source) return null;
        return {
          id,
          config_name: source.telescope_config_name,
          effective_focal_length_mm: 0,
          effective_focal_ratio: 0,
          effective_image_circle_mm: null,
          telescope_name: source.telescope_name,
          manufacturer_name: "",
        };
      });
    },
    [options.telescopes, partSources, value.telescope_configuration_id],
  );
  const cameras = useMemo(
    () => keepRetiredSelected(
      sortByManufacturer(options.cameras),
      [value.camera_id, value.guide_camera_id],
      (id) => {
        const source = partSources.find(
          (parts) => parts.camera_id === id || parts.guide_camera_id === id,
        );
        const name = source?.camera_id === id ? source.camera_name : source?.guide_camera_name;
        if (!name) return null;
        return {
          id,
          model_name: name,
          manufacturer_name: "",
          pixel_size_um: 0,
          resolution_x: 0,
          resolution_y: 0,
          sensor_width_mm: null,
          sensor_height_mm: null,
          sensor_type: "",
          is_mine: false,
        };
      },
    ),
    [options.cameras, partSources, value.camera_id, value.guide_camera_id],
  );
  const filterWheels = useMemo(
    () => keepRetiredSelected(
      sortByManufacturer(options.filter_wheels),
      [value.filter_wheel_id],
      (id) => {
        const source = partSources.find((parts) => parts.filter_wheel_id === id);
        if (!source?.filter_wheel_name) return null;
        return {
          id,
          model_name: source.filter_wheel_name,
          manufacturer_name: "",
          num_positions: source.filter_wheel_positions
            ?? Math.max(1, ...source.filter_slots.map((slot) => slot.slot_number)),
          is_mine: false,
        };
      },
    ),
    [options.filter_wheels, partSources, value.filter_wheel_id],
  );
  const selectedFilterIds = useMemo(
    () => [value.single_filter_id, ...value.filter_slots.map((slot) => slot.filter_id)],
    [value.single_filter_id, value.filter_slots],
  );
  const filters = useMemo(
    () => keepRetiredSelected(sortByManufacturer(options.filters), selectedFilterIds, (id) => {
      const source = partSources.find(
        (parts) => parts.single_filter_id === id
          || parts.filter_slots.some((slot) => slot.filter_id === id),
      );
      const name = source?.single_filter_id === id
        ? source.single_filter_name
        : source?.filter_slots.find((slot) => slot.filter_id === id)?.filter_name;
      if (!name) return null;
      return {
        id,
        model_name: name,
        manufacturer_name: "",
        filter_type_name: "",
        is_mine: false,
      };
    }),
    [options.filters, partSources, selectedFilterIds],
  );
  const mounts = useMemo(
    () => keepRetiredSelected(
      sortByManufacturer(options.mounts),
      [value.mount_id],
      (id) => retainedSimpleOption(partSources, id, "mount_id", "mount_name"),
    ),
    [options.mounts, partSources, value.mount_id],
  );
  const focusers = useMemo(
    () => keepRetiredSelected(
      sortByManufacturer(options.focusers),
      [value.focuser_id],
      (id) => retainedSimpleOption(partSources, id, "focuser_id", "focuser_name"),
    ),
    [options.focusers, partSources, value.focuser_id],
  );
  const oags = useMemo(
    () => keepRetiredSelected(
      sortByManufacturer(options.oags),
      [value.oag_id],
      (id) => retainedSimpleOption(partSources, id, "oag_id", "oag_name"),
    ),
    [options.oags, partSources, value.oag_id],
  );
  const guideScopes = useMemo(
    () => keepRetiredSelected(
      sortByManufacturer(options.guide_scopes),
      [value.guide_scope_id],
      (id) => {
        const source = partSources.find((parts) => parts.guide_scope_id === id);
        if (!source?.guide_scope_name) return null;
        return {
          id,
          model_name: source.guide_scope_name,
          manufacturer_name: "",
          focal_length_mm: source.guide_scope_focal_length_mm ?? null,
          is_mine: false,
        };
      },
    ),
    [options.guide_scopes, partSources, value.guide_scope_id],
  );
  const computers = useMemo(
    () => keepRetiredSelected(
      sortByManufacturer(options.computers),
      [value.computer_id],
      (id) => retainedSimpleOption(partSources, id, "computer_id", "computer_name"),
    ),
    [options.computers, partSources, value.computer_id],
  );
  const software = useMemo(
    () => orderSoftwareOptions(
      keepRetiredSelected(options.software, value.software_ids, (id) => {
        const item = partSources.flatMap((parts) => parts.software).find((entry) => entry.id === id);
        return item ? { ...item, is_mine: false } : null;
      }),
      "rig",
    ),
    [options.software, partSources, value.software_ids],
  );

  const set = (patch: Partial<RigPartsInput>) => onChange({ ...value, ...patch });
  const guidingMode: GuidingMode = value.oag_id
    ? "oag"
    : value.guide_scope_id
      ? "guide_scope"
      : selectedGuidingMode;
  const selectedWheel = filterWheels.find((wheel) => wheel.id === value.filter_wheel_id);

  const resetGroup = (group: PartGroup) => {
    if (!base) return;
    if (group === "guider") setSelectedGuidingMode(modeFromParts(base));
    set(Object.fromEntries(GROUP_FIELDS[group].map((field) => [field, base[field]])) as Partial<RigPartsInput>);
  };

  const resetLink = (group: PartGroup) => (
    <Button
      size="small"
      onClick={() => resetGroup(group)}
      sx={(theme) => ({
        minWidth: 0,
        p: 0,
        fontSize: "13px",
        lineHeight: "20px",
        textTransform: "none",
        whiteSpace: "nowrap",
        color: theme.palette.mode === "dark" ? "#d4993f" : "#c07b2b",
      })}
    >
      Use the rig&apos;s
    </Button>
  );

  const indicator = (group: PartGroup) => {
    if (!base) return null;
    if (!groupChanged(value, base, group)) {
      return (
        <Typography sx={{ fontSize: "12px", color: "text.secondary", whiteSpace: "nowrap" }}>
          Rig&apos;s
        </Typography>
      );
    }
    return (
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
        <ProjectTag />
        {resetLink(group)}
      </Box>
    );
  };

  const rowSx = {
    display: "grid",
    gridTemplateColumns: { xs: "1fr", sm: "130px minmax(0, 1fr) auto" },
    gap: "10px 14px",
    alignItems: "center",
  } as const;
  const labelSx = { fontSize: "13px", color: "text.secondary" } as const;

  return (
    <Box
      sx={(theme) => ({
        display: "grid",
        gap: "10px",
        "& .MuiOutlinedInput-notchedOutline": {
          borderColor: theme.palette.mode === "dark" ? "rgba(255, 255, 255, 0.23)" : "#c4c1bb",
        },
      })}
    >
      <Box sx={rowSx}>
        <Typography sx={labelSx}>Telescope</Typography>
        <Autocomplete
          size="small"
          options={configs}
          groupBy={optionGroup}
          getOptionLabel={(option) => retainedLabel(
            option,
            `${option.manufacturer_name} ${option.telescope_name} — ${option.config_name}`,
            `${option.telescope_name} — ${option.config_name}`,
          )}
          value={configs.find((option) => option.id === value.telescope_configuration_id) ?? null}
          onChange={(_event, option) => set({ telescope_configuration_id: option?.id ?? 0 })}
          isOptionEqualToValue={(option, selected) => option.id === selected.id}
          renderInput={(params) => <TextField {...params} required />}
        />
        {indicator("telescope")}
      </Box>

      <Box sx={rowSx}>
        <Typography sx={labelSx}>Camera</Typography>
        <Autocomplete<RetainedOption<CameraOption>>
          size="small"
          options={cameras}
          groupBy={optionGroup}
          getOptionLabel={(option) => retainedLabel(
            option,
            `${option.manufacturer_name} — ${option.model_name}`,
            option.model_name,
          )}
          value={cameras.find((option) => option.id === value.camera_id) ?? null}
          onChange={(_event, option) => set({ camera_id: option?.id ?? 0 })}
          isOptionEqualToValue={(option, selected) => option.id === selected.id}
          renderInput={(params) => <TextField {...params} required />}
        />
        {indicator("camera")}
      </Box>

      <Box sx={rowSx}>
        <Typography sx={labelSx}>Filter wheel</Typography>
        <Autocomplete<RetainedOption<FilterWheelOption>>
          size="small"
          options={filterWheels}
          groupBy={optionGroup}
          getOptionLabel={(option) => retainedLabel(
            option,
            `${option.manufacturer_name} — ${option.model_name} (${option.num_positions} positions)`,
            option.model_name,
          )}
          value={filterWheels.find((option) => option.id === value.filter_wheel_id) ?? null}
          onChange={(_event, option) =>
            set({
              filter_wheel_id: option?.id ?? null,
              single_filter_id: option ? null : value.single_filter_id,
              filter_slots: option?.id === value.filter_wheel_id ? value.filter_slots : [],
            })
          }
          isOptionEqualToValue={(option, selected) => option.id === selected.id}
          renderInput={(params) => <TextField {...params} placeholder="None" />}
        />
        {indicator("filters")}
      </Box>

      {selectedWheel && (
        <Box sx={{ ...rowSx, alignItems: "start" }}>
          <Typography sx={{ ...labelSx, pt: 1 }}>Slots</Typography>
          <FilterSlots
            count={selectedWheel.num_positions}
            filters={filters}
            slots={value.filter_slots ?? []}
            onChange={(filter_slots) => set({ filter_slots })}
          />
          <Box />
        </Box>
      )}

      {!selectedWheel && (
        <Box sx={rowSx}>
          <Typography sx={labelSx}>Single filter</Typography>
          <Autocomplete<RetainedOption<FilterOption>>
            size="small"
            options={filters}
            groupBy={optionGroup}
            getOptionLabel={(option) => retainedLabel(
              option,
              `${option.manufacturer_name} — ${option.model_name}`,
              option.model_name,
            )}
            value={filters.find((option) => option.id === value.single_filter_id) ?? null}
            onChange={(_event, option) => set({ single_filter_id: option?.id ?? null })}
            isOptionEqualToValue={(option, selected) => option.id === selected.id}
            renderInput={(params) => <TextField {...params} placeholder="None" />}
          />
          <Box />
        </Box>
      )}

      <Box sx={rowSx}>
        <Typography sx={labelSx}>Mount</Typography>
        <Autocomplete<RetainedOption<SimpleOption>>
          size="small"
          options={mounts}
          groupBy={optionGroup}
          getOptionLabel={simpleLabel}
          value={mounts.find((option) => option.id === value.mount_id) ?? null}
          onChange={(_event, option) => set({ mount_id: option?.id ?? null })}
          isOptionEqualToValue={(option, selected) => option.id === selected.id}
          renderInput={(params) => <TextField {...params} placeholder="None" />}
        />
        {indicator("mount")}
      </Box>

      <Box sx={rowSx}>
        <Typography sx={labelSx}>Focuser</Typography>
        <Autocomplete<RetainedOption<SimpleOption>>
          size="small"
          options={focusers}
          groupBy={optionGroup}
          getOptionLabel={simpleLabel}
          value={focusers.find((option) => option.id === value.focuser_id) ?? null}
          onChange={(_event, option) => set({ focuser_id: option?.id ?? null })}
          isOptionEqualToValue={(option, selected) => option.id === selected.id}
          renderInput={(params) => <TextField {...params} placeholder="None" />}
        />
        {indicator("focuser")}
      </Box>

      <Box sx={rowSx}>
        <Typography sx={labelSx}>Guiding</Typography>
        <ToggleButtonGroup
          exclusive
          size="small"
          value={guidingMode}
          aria-label="Guiding"
          onChange={(_event, mode: GuidingMode | null) => {
            if (!mode) return;
            setSelectedGuidingMode(mode);
            set({
              oag_id: mode === "oag" ? value.oag_id : null,
              guide_scope_id: mode === "guide_scope" ? value.guide_scope_id : null,
              guide_camera_id: mode === "none" ? null : value.guide_camera_id,
            });
          }}
          sx={(theme) => ({
            "& .MuiToggleButton-root": {
              textTransform: "none",
              "&.Mui-selected": {
                bgcolor: theme.palette.mode === "dark" ? "#d4993f29" : "#c07b2b29",
                color: theme.palette.mode === "dark" ? "#d4993f" : "#9a6220",
                fontWeight: 600,
                "&:hover": {
                  bgcolor: theme.palette.mode === "dark" ? "#d4993f29" : "#c07b2b29",
                },
              },
            },
          })}
        >
          <ToggleButton value="none">None</ToggleButton>
          <ToggleButton value="oag">Off-axis guider</ToggleButton>
          <ToggleButton value="guide_scope">Guide scope</ToggleButton>
        </ToggleButtonGroup>
        {indicator("guider")}
      </Box>

      {guidingMode === "oag" && (
        <Box sx={rowSx}>
          <Typography sx={labelSx}>Off-axis guider</Typography>
          <Autocomplete<RetainedOption<SimpleOption>>
            size="small"
            options={oags}
            groupBy={optionGroup}
            getOptionLabel={simpleLabel}
            value={oags.find((option) => option.id === value.oag_id) ?? null}
            onChange={(_event, option) => set({ oag_id: option?.id ?? null })}
            isOptionEqualToValue={(option, selected) => option.id === selected.id}
            renderInput={(params) => <TextField {...params} />}
          />
          <Box />
        </Box>
      )}

      {guidingMode === "guide_scope" && (
        <Box sx={rowSx}>
          <Typography sx={labelSx}>Guide scope</Typography>
          <Autocomplete<RetainedOption<GuideScopeOption>>
            size="small"
            options={guideScopes}
            groupBy={optionGroup}
            getOptionLabel={simpleLabel}
            value={guideScopes.find((option) => option.id === value.guide_scope_id) ?? null}
            onChange={(_event, option) => set({ guide_scope_id: option?.id ?? null })}
            isOptionEqualToValue={(option, selected) => option.id === selected.id}
            renderInput={(params) => <TextField {...params} />}
          />
          <Box />
        </Box>
      )}

      {guidingMode !== "none" && (
        <Box sx={rowSx}>
          <Typography sx={labelSx}>Guide camera</Typography>
          <Autocomplete<RetainedOption<CameraOption>>
            size="small"
            options={cameras}
            groupBy={optionGroup}
            getOptionLabel={(option) => retainedLabel(
              option,
              `${option.manufacturer_name} — ${option.model_name}`,
              option.model_name,
            )}
            value={cameras.find((option) => option.id === value.guide_camera_id) ?? null}
            onChange={(_event, option) => set({ guide_camera_id: option?.id ?? null })}
            isOptionEqualToValue={(option, selected) => option.id === selected.id}
            renderInput={(params) => <TextField {...params} />}
          />
          {indicator("guide_camera")}
        </Box>
      )}

      <Box sx={rowSx}>
        <Typography sx={labelSx}>Computer</Typography>
        <Autocomplete<RetainedOption<SimpleOption>>
          size="small"
          options={computers}
          groupBy={optionGroup}
          getOptionLabel={simpleLabel}
          value={computers.find((option) => option.id === value.computer_id) ?? null}
          onChange={(_event, option) => set({ computer_id: option?.id ?? null })}
          isOptionEqualToValue={(option, selected) => option.id === selected.id}
          renderInput={(params) => <TextField {...params} placeholder="None" />}
        />
        {indicator("computer")}
      </Box>

      <Box sx={rowSx}>
        <Typography sx={labelSx}>Software</Typography>
        <Autocomplete<RetainedOption<SoftwareOption>, true>
          multiple
          size="small"
          options={software}
          groupBy={(option) => formatSnakeCase(option.category)}
          getOptionLabel={(option) => retainedLabel(option, option.name, option.name)}
          value={software.filter((option) => (value.software_ids ?? []).includes(option.id))}
          onChange={(_event, selected) => set({ software_ids: selected.map((option) => option.id) })}
          isOptionEqualToValue={(option, selected) => option.id === selected.id}
          renderInput={(params) => <TextField {...params} placeholder="None" />}
        />
        {indicator("software")}
      </Box>
    </Box>
  );
}
