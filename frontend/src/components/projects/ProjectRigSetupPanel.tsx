import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import IconButton from "@mui/material/IconButton";
import Paper from "@mui/material/Paper";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";
import type { Theme } from "@mui/material/styles";
import {
  deleteProjectRigChange,
  type Project,
  type ProjectRigSetups,
  type ProjectSetup,
} from "@/api/projects";
import {
  fetchEquipmentOptions,
  fetchRigSetups,
  fetchRigs,
  type RigSetup,
} from "@/api/rigs";
import CorrectSetupDialog from "@/components/rigs/CorrectSetupDialog";
import RigFormDialog from "@/components/rigs/RigFormDialog";
import ProjectRigChangeDialog from "./ProjectRigChangeDialog";

interface Props {
  project: Project;
  rigSetups: ProjectRigSetups;
  onClose: () => void;
  onChanged: () => void;
}

interface DisplayValue {
  main: string;
  detail?: string;
}

interface DisplayRow {
  label: string;
  group?: string;
  values: DisplayValue[];
}

function formatDate(value: string): string {
  const dateOnly = value.slice(0, 10);
  const [year, month, day] = dateOnly.split("-").map(Number);
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(Date.UTC(year, month - 1, day)));
}

function countLabel(count: number): string {
  return `${count} ${count === 1 ? "night" : "nights"}`;
}

function compactNumber(value: number): string {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(value);
}

function projectTag() {
  return (
    <Box
      component="span"
      sx={(theme) => ({
        display: "inline-flex",
        alignItems: "center",
        height: "20px",
        ml: "6px",
        px: "8px",
        borderRadius: "10px",
        verticalAlign: "1px",
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

function guidingValue(setup: ProjectSetup): DisplayValue {
  const parts = setup.parts;
  const guider = parts.guide_scope_name ?? parts.oag_name;
  const names = [guider, parts.guide_camera_name].filter(Boolean);
  return { main: names.join(", ") || "—" };
}

function rowsFor(setups: ProjectSetup[]): DisplayRow[] {
  return [
    {
      label: "Telescope",
      group: "telescope",
      values: setups.map(({ parts }) => ({
        main: `${parts.telescope_name}, ${parts.telescope_config_name}`,
        detail: `${compactNumber(parts.effective_focal_length_mm)} mm, f/${compactNumber(parts.effective_focal_ratio)}`,
      })),
    },
    {
      label: "Camera",
      group: "camera",
      values: setups.map(({ parts }) => ({
        main: parts.camera_name,
        detail: `${compactNumber(parts.pixel_size_um)} µm pixels, ${parts.sensor_resolution_x} × ${parts.sensor_resolution_y}`,
      })),
    },
    {
      label: "Image scale",
      values: setups.map(({ parts }) => ({
        main: `${parts.image_scale_arcsec_per_pixel.toFixed(2)}″/px`,
      })),
    },
    {
      label: "Field of view",
      values: setups.map(({ parts }) => ({
        main: `${parts.field_of_view_deg[0].toFixed(2)}° × ${parts.field_of_view_deg[1].toFixed(2)}°`,
      })),
    },
    {
      label: "Filters",
      group: "filters",
      values: setups.map(({ parts }) => ({
        main: parts.filter_wheel_name ?? parts.single_filter_name ?? "—",
        detail: parts.filter_wheel_name
          ? parts.filter_slots.map((slot) => slot.filter_name).join(", ") || undefined
          : undefined,
      })),
    },
    {
      label: "Mount",
      group: "mount",
      values: setups.map(({ parts }) => ({ main: parts.mount_name ?? "—" })),
    },
    {
      label: "Focuser",
      group: "focuser",
      values: setups.map(({ parts }) => ({ main: parts.focuser_name ?? "—" })),
    },
    {
      label: "Guiding",
      group: "guiding",
      values: setups.map(guidingValue),
    },
    {
      label: "Computer",
      group: "computer",
      values: setups.map(({ parts }) => ({ main: parts.computer_name ?? "—" })),
    },
    {
      label: "Software",
      group: "software",
      values: setups.map(({ parts }) => ({
        main: parts.software.map((software) => software.name).join(", ") || "—",
      })),
    },
  ];
}

function valuesDiffer(values: DisplayValue[]): boolean {
  const first = values[0];
  return values.some((value) => value.main !== first.main || value.detail !== first.detail);
}

export default function ProjectRigSetupPanel({
  project,
  rigSetups,
  onClose,
  onChanged,
}: Props) {
  const [changeOpen, setChangeOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [correcting, setCorrecting] = useState<RigSetup | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [undoing, setUndoing] = useState(false);
  const { data: allRigs = [] } = useQuery({
    queryKey: ["rigs", "all"],
    queryFn: () => fetchRigs(false),
  });
  const { data: rawSetups, refetch: refetchRawSetups } = useQuery({
    queryKey: ["rig-setups", rigSetups.rig_id],
    queryFn: () => fetchRigSetups(rigSetups.rig_id),
  });
  const { data: options } = useQuery({
    queryKey: ["equipment-options"],
    queryFn: fetchEquipmentOptions,
    enabled: correcting != null,
  });
  const rig = allRigs.find((item) => item.id === rigSetups.rig_id) ?? null;
  const rows = useMemo(() => rowsFor(rigSetups.setups), [rigSetups.setups]);
  const changedGroups = new Set(rigSetups.changed_groups);
  const textButtonSx = (theme: Theme) => ({
    color: theme.palette.mode === "dark" ? "#d4993f" : "#c07b2b",
  });

  const rigGuider = rig?.oag_name
    ? "an off-axis guider"
    : rig?.guide_scope_name
      ? rig.guide_scope_name
      : "no guider";

  const undo = async () => {
    setUndoing(true);
    setError(null);
    try {
      await deleteProjectRigChange(project.id, rigSetups.rig_id);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to undo the project change");
    } finally {
      setUndoing(false);
    }
  };

  return (
    <Paper
      component="section"
      aria-labelledby={`project-rig-panel-${rigSetups.rig_id}`}
      variant="outlined"
      sx={(theme) => ({
        mt: "12px",
        position: "relative",
        border: `1px solid ${theme.palette.mode === "dark" ? "#34373d" : "#dcd9d4"}`,
        borderRadius: "8px",
        bgcolor: theme.palette.mode === "dark" ? "#24272c" : "#ffffff",
        px: "20px",
        pt: "16px",
        pb: "18px",
      })}
    >
      <IconButton
        size="small"
        onClick={onClose}
        aria-label="Close rig setup details"
        sx={{ position: "absolute", top: 10, right: 10 }}
      >
        <CloseIcon fontSize="small" />
      </IconButton>
      <Typography
        id={`project-rig-panel-${rigSetups.rig_id}`}
        sx={{ fontSize: "16px", fontWeight: 600, lineHeight: 1.4 }}
      >
        {rigSetups.rig_name}
      </Typography>
      <Typography sx={{ fontSize: "13px", color: "text.secondary", mb: "14px" }}>
        The setups this project was imaged with, newest first.
      </Typography>
      {error && <Alert severity="error" sx={{ mb: 1.5 }}>{error}</Alert>}
      <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap", mb: "14px" }}>
        <Tooltip title="Changes the setup for this project only, for example a guide scope instead of the off-axis guider. The rig and other projects stay as they are.">
          <Button
            variant="outlined"
            size="small"
            onClick={() => setChangeOpen(true)}
            sx={textButtonSx}
          >
            Change for this project only
          </Button>
        </Tooltip>
        {rigSetups.change && (
          <Tooltip title="Removes this project's own change, so it uses the rig's setup again. The rig and other projects are unchanged.">
            <span>
              <Button
                variant="outlined"
                size="small"
                onClick={() => void undo()}
                disabled={undoing}
                sx={textButtonSx}
              >
                Undo the project change
              </Button>
            </span>
          </Tooltip>
        )}
        <Tooltip title="Edits the rig itself. If the rig is in use, an equipment change asks whether to correct existing projects or apply from now on.">
          <span>
            <Button
              variant="outlined"
              size="small"
              onClick={() => setEditOpen(true)}
              disabled={!rig}
              sx={textButtonSx}
            >
              Edit rig
            </Button>
          </span>
        </Tooltip>
      </Box>

      <Box sx={{ overflowX: "auto" }}>
        <Box
          component="table"
          sx={(theme) => ({
            width: "100%",
            borderCollapse: "collapse",
            fontSize: "13.5px",
            "& th, & td": {
              textAlign: "left",
              verticalAlign: "top",
              py: "7px",
              pr: "12px",
              borderBottom: `1px solid ${theme.palette.mode === "dark" ? "#34373d" : "#dcd9d4"}`,
            },
            "& thead th": {
              pb: "10px",
              borderBottomColor: theme.palette.mode === "dark" ? "#4a4d54" : "#c4c1bb",
            },
          })}
        >
          <thead>
            <tr>
              <Box component="th" sx={{ width: "140px", minWidth: "140px" }} />
              {rigSetups.setups.map((setup) => (
                <Box component="th" key={setup.rig_setup_id ?? "now"}>
                  <Typography sx={{ fontSize: "15px", fontWeight: 600 }}>
                    {setup.until_at ? `Until ${formatDate(setup.until_at)}` : "Now"}
                  </Typography>
                  <Typography sx={{ fontSize: "13px", fontWeight: 400, color: "text.secondary" }}>
                    {countLabel(setup.night_count)}
                    {setup.until_at == null && setup.since_at
                      ? `, since ${formatDate(setup.since_at)}`
                      : ""}
                  </Typography>
                  {setup.rig_setup_id != null && (
                    <Button
                      size="small"
                      disabled={!rawSetups?.some((item) => item.id === setup.rig_setup_id)}
                      onClick={() => {
                        const rawSetup = rawSetups?.find(
                          (item) => item.id === setup.rig_setup_id,
                        );
                        if (rawSetup) setCorrecting(rawSetup);
                      }}
                      sx={(theme) => ({ ...textButtonSx(theme), mt: "6px", ml: "-10px" })}
                    >
                      Correct this setup
                    </Button>
                  )}
                </Box>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const differs = valuesDiffer(row.values);
              const projectChanged = row.group === "guiding"
                ? changedGroups.has("guider") || changedGroups.has("guide_camera")
                : row.group != null && changedGroups.has(row.group);
              return (
                <tr key={row.label}>
                  <Box
                    component="th"
                    scope="row"
                    sx={{ width: "140px", color: "text.secondary", fontWeight: 500 }}
                  >
                    {row.label}
                    {differs && (
                      <Box component="span" sx={(theme) => ({
                        fontWeight: 400,
                        color: theme.palette.mode === "dark" ? "#57554f" : "#a3a3a3",
                      })}>
                        {" (changed)"}
                      </Box>
                    )}
                  </Box>
                  {row.values.map((value, index) => (
                    <Box
                      component="td"
                      key={rigSetups.setups[index].rig_setup_id ?? `now-${row.label}`}
                      sx={{ fontWeight: differs ? 600 : 400 }}
                    >
                      {value.main}
                      {projectChanged && projectTag()}
                      {value.detail && (
                        <Typography
                          component="small"
                          sx={{ display: "block", color: "text.secondary", fontSize: "12px", fontWeight: 400 }}
                        >
                          {value.detail}
                        </Typography>
                      )}
                      {row.group === "guiding" && projectChanged && (
                        <Typography
                          component="small"
                          sx={{ display: "block", color: "text.secondary", fontSize: "12px", fontWeight: 400 }}
                        >
                          The rig uses {rigGuider}.
                        </Typography>
                      )}
                    </Box>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </Box>
      </Box>

      <ProjectRigChangeDialog
        open={changeOpen}
        projectId={project.id}
        projectName={project.name}
        rig={rigSetups}
        onClose={() => setChangeOpen(false)}
        onSaved={onChanged}
      />
      <RigFormDialog
        open={editOpen}
        rig={rig}
        onClose={() => setEditOpen(false)}
        onSaved={onChanged}
      />
      {options && (
        <CorrectSetupDialog
          open={correcting != null}
          setup={correcting}
          options={options}
          onClose={() => setCorrecting(null)}
          onSaved={() => {
            void refetchRawSetups();
            onChanged();
          }}
        />
      )}
    </Paper>
  );
}
