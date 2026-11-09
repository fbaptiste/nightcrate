import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type MouseEvent,
} from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import AddIcon from "@mui/icons-material/Add";
import CloseIcon from "@mui/icons-material/Close";
import Autocomplete from "@mui/material/Autocomplete";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import IconButton from "@mui/material/IconButton";
import Paper from "@mui/material/Paper";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import {
  setProjectRigs,
  type Project,
  type ProjectRigSetups,
  type ProjectSetup,
} from "@/api/projects";
import { fetchRigs, type Rig } from "@/api/rigs";
import ProjectRigSetupPanel from "./ProjectRigSetupPanel";

interface Props {
  project: Project;
  rigSetups: ProjectRigSetups[];
  onUpdated: (project: Project) => void;
  onChanged: () => void;
  onError: (message: string) => void;
}

const GRID_COLUMNS = "minmax(170px, 1.3fr) 1.4fr 0.8fr 1fr 0.7fr 120px";
const NARROW_COLUMNS = "minmax(0, 1.3fr) minmax(0, 1fr) minmax(90px, 0.8fr) 120px";

function compactNumber(value: number): string {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(value);
}

function formatDate(value: string): string {
  const [year, month, day] = value.slice(0, 10).split("-").map(Number);
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(Date.UTC(year, month - 1, day)));
}

function displaySetup(rig: ProjectRigSetups): ProjectSetup | null {
  return (
    rig.setups.find((setup) => setup.rig_setup_id == null && setup.night_count > 0) ??
    rig.setups[0] ??
    null
  );
}

function earlierUsedSetup(
  rig: ProjectRigSetups,
  displayed: ProjectSetup | null,
): ProjectSetup | null {
  return (
    rig.setups.find(
      (setup) => setup !== displayed && setup.night_count > 0,
    ) ?? null
  );
}

export default function ProjectEquipmentSection({
  project,
  rigSetups,
  onUpdated,
  onChanged,
  onError,
}: Props) {
  const [selectedRigId, setSelectedRigId] = useState<number | null>(null);
  const [addingRig, setAddingRig] = useState(false);
  const rowRefs = useRef(new Map<number, HTMLElement>());
  const panelRef = useRef<HTMLDivElement | null>(null);
  const { data: allRigs = [] } = useQuery({
    queryKey: ["rigs", "all"],
    queryFn: () => fetchRigs(false),
  });

  const declaredIds = useMemo(
    () => new Set(project.rigs.map((rig) => rig.id)),
    [project.rigs],
  );
  const rigOptions = useMemo(
    () => allRigs.filter((rig) => (rig.active && rig.is_mine) || declaredIds.has(rig.id)),
    [allRigs, declaredIds],
  );
  const orderedSetups = useMemo(
    () => [...rigSetups].sort((a, b) => Number(b.declared) - Number(a.declared)),
    [rigSetups],
  );

  const rigsMut = useMutation({
    mutationFn: (rigIds: number[]) => setProjectRigs(project.id, rigIds),
    onSuccess: (updated) => {
      onUpdated(updated);
      onChanged();
      setAddingRig(false);
    },
    onError: (error) => onError(String(error)),
  });

  const toggleRig = (rigId: number) => {
    setSelectedRigId((current) => (current === rigId ? null : rigId));
  };

  const handleRowKeyDown = (event: KeyboardEvent<HTMLElement>, rigId: number) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    toggleRig(rigId);
  };

  const removeRig = (event: MouseEvent<HTMLButtonElement>, rigId: number) => {
    event.stopPropagation();
    if (selectedRigId === rigId) setSelectedRigId(null);
    rigsMut.mutate(project.rigs.filter((rig) => rig.id !== rigId).map((rig) => rig.id));
  };

  const addRig = (rig: Rig | null) => {
    if (!rig || declaredIds.has(rig.id)) return;
    rigsMut.mutate([...project.rigs.map((item) => item.id), rig.id]);
  };

  const closePanel = () => {
    const rigId = selectedRigId;
    setSelectedRigId(null);
    if (rigId != null) requestAnimationFrame(() => rowRefs.current.get(rigId)?.focus());
  };

  const selectedRig = selectedRigId == null
    ? null
    : rigSetups.find((rig) => rig.rig_id === selectedRigId) ?? null;

  useEffect(() => {
    if (selectedRigId == null) return;
    const frame = requestAnimationFrame(() => {
      panelRef.current?.scrollIntoView({
        block: "nearest",
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "auto"
          : "smooth",
      });
    });
    return () => cancelAnimationFrame(frame);
  }, [selectedRigId]);

  return (
    <Box component="section" aria-labelledby="project-equipment-heading" sx={{ mt: "36px" }}>
      <Box sx={{ display: "flex", alignItems: "baseline", gap: "12px", mb: "12px" }}>
        <Typography
          id="project-equipment-heading"
          component="h2"
          sx={{ m: 0, fontSize: "17px", lineHeight: 1.4, fontWeight: 600 }}
        >
          Equipment
        </Typography>
        <Typography sx={{ color: "text.secondary", fontSize: "13px", lineHeight: 1.4 }}>
          Click a rig to see its full setup.
        </Typography>
      </Box>

      <Paper
        variant="outlined"
        sx={(theme) => ({
          overflow: "hidden",
          borderColor: theme.palette.mode === "dark" ? "#34373d" : "#dcd9d4",
          borderRadius: "8px",
          bgcolor: theme.palette.mode === "dark" ? "#24272c" : "#ffffff",
        })}
      >
        <Box
          aria-hidden="true"
          sx={(theme) => ({
            display: "grid",
            gridTemplateColumns: GRID_COLUMNS,
            gap: "12px",
            alignItems: "center",
            px: "16px",
            py: "8px",
            borderBottom: `1px solid ${theme.palette.mode === "dark" ? "#34373d" : "#dcd9d4"}`,
            color: "text.secondary",
            fontSize: "12px",
            "@media (max-width: 1099.95px)": {
              gridTemplateColumns: NARROW_COLUMNS,
              "& .equipment-fov, & .equipment-nights": { display: "none" },
            },
          })}
        >
          <span>Rig</span>
          <span>Camera</span>
          <span>Image scale</span>
          <span className="equipment-fov">Field of view</span>
          <span className="equipment-nights">Nights</span>
          <span />
        </Box>

        {orderedSetups.map((rig) => {
          const setup = displaySetup(rig);
          const earlier = earlierUsedSetup(rig, setup);
          const shownSetupIsEarlier = setup?.rig_setup_id != null && setup.until_at != null;
          const earlierCameraDiffers =
            setup != null && earlier != null && setup.parts.camera_id !== earlier.parts.camera_id;
          const earlierScaleDiffers =
            setup != null &&
            earlier != null &&
            setup.parts.image_scale_arcsec_per_pixel !==
              earlier.parts.image_scale_arcsec_per_pixel;
          const open = selectedRigId === rig.rig_id;
          const nights = rig.setups.reduce((total, item) => total + item.night_count, 0);
          return (
            <Box
              key={rig.rig_id}
              sx={(theme) => ({
                position: "relative",
                borderBottom: `1px solid ${theme.palette.mode === "dark" ? "#34373d" : "#dcd9d4"}`,
              })}
            >
              <Box
                ref={(element: HTMLElement | null) => {
                  if (element) rowRefs.current.set(rig.rig_id, element);
                  else rowRefs.current.delete(rig.rig_id);
                }}
                role="button"
                tabIndex={0}
                aria-expanded={open}
                aria-controls={open ? `project-rig-panel-${rig.rig_id}` : undefined}
                onClick={() => toggleRig(rig.rig_id)}
                onKeyDown={(event) => handleRowKeyDown(event, rig.rig_id)}
                sx={(theme) => {
                  const amber = theme.palette.mode === "dark" ? "#d4993f" : "#c07b2b";
                  const openBackground = `color-mix(in srgb, ${amber} 8%, transparent)`;
                  return {
                    display: "grid",
                    gridTemplateColumns: GRID_COLUMNS,
                    gap: "12px",
                    alignItems: "center",
                    px: "16px",
                    py: "11px",
                    cursor: "pointer",
                    bgcolor: open ? openBackground : "transparent",
                    boxShadow: open ? `inset 3px 0 0 ${amber}` : "none",
                    "&:hover": { bgcolor: open ? openBackground : "action.hover" },
                    "&:focus-visible": {
                      outline: `2px solid ${amber}`,
                      outlineOffset: "-2px",
                    },
                    "@media (max-width: 1099.95px)": {
                      gridTemplateColumns: NARROW_COLUMNS,
                      "& .equipment-fov, & .equipment-nights": { display: "none" },
                    },
                  };
                }}
              >
                <Box sx={{ minWidth: 0 }}>
                  <Box sx={{ display: "flex", alignItems: "center", flexWrap: "wrap" }}>
                    <Typography component="span" sx={{ fontSize: "13.5px", fontWeight: 600 }}>
                      {rig.rig_name}
                    </Typography>
                    {!rig.declared && (
                      <Box
                        component="span"
                        sx={(theme) => ({
                          display: "inline-flex",
                          alignItems: "center",
                          height: "18px",
                          ml: "6px",
                          px: "7px",
                          border: `1px solid ${theme.palette.mode === "dark" ? "rgba(255,255,255,0.23)" : "#c4c1bb"}`,
                          borderRadius: "9px",
                          color: "text.secondary",
                          fontSize: "11px",
                          lineHeight: "18px",
                          whiteSpace: "nowrap",
                        })}
                      >
                        used, not listed
                      </Box>
                    )}
                  </Box>
                  {setup && (
                    <Typography sx={{ color: "text.secondary", fontSize: "12px", lineHeight: 1.4 }}>
                      {setup.parts.telescope_name},{" "}
                      {compactNumber(setup.parts.effective_focal_length_mm)} mm f/
                      {compactNumber(setup.parts.effective_focal_ratio)}
                    </Typography>
                  )}
                </Box>

                <Box sx={{ minWidth: 0 }}>
                  <Typography sx={{ fontSize: "13.5px", lineHeight: 1.4 }}>
                    {setup?.parts.camera_name ?? "—"}
                  </Typography>
                  {shownSetupIsEarlier && setup?.until_at && (
                    <Typography sx={{ color: "text.secondary", fontSize: "12px", lineHeight: 1.4 }}>
                      until {formatDate(setup.until_at)}
                    </Typography>
                  )}
                  {earlierCameraDiffers && earlier && (
                    <Typography sx={{ color: "text.secondary", fontSize: "12px", lineHeight: 1.4 }}>
                      {earlier.until_at ? `until ${formatDate(earlier.until_at)}: ` : "before: "}
                      {earlier.parts.camera_name}
                    </Typography>
                  )}
                </Box>

                <Box>
                  <Typography sx={{ fontSize: "13.5px", lineHeight: 1.4 }}>
                    {setup ? `${setup.parts.image_scale_arcsec_per_pixel.toFixed(2)}″/px` : "—"}
                  </Typography>
                  {earlierScaleDiffers && earlier && (
                    <Typography sx={{ color: "text.secondary", fontSize: "12px", lineHeight: 1.4 }}>
                      {earlier.parts.image_scale_arcsec_per_pixel.toFixed(2)}″/px before
                    </Typography>
                  )}
                </Box>

                <Typography className="equipment-fov" sx={{ fontSize: "13.5px", lineHeight: 1.4 }}>
                  {setup
                    ? `${setup.parts.field_of_view_deg[0].toFixed(2)}° × ${setup.parts.field_of_view_deg[1].toFixed(2)}°`
                    : "—"}
                </Typography>
                <Typography className="equipment-nights" sx={{ fontSize: "13.5px", lineHeight: 1.4 }}>
                  {nights}
                </Typography>

                <Box sx={{ justifySelf: "end", pr: rig.declared ? "28px" : 0 }}>
                  <Typography
                    component="span"
                    sx={{ color: "primary.main", fontSize: "13px", whiteSpace: "nowrap" }}
                  >
                    {open ? "Hide setup" : "Show setup"}
                  </Typography>
                </Box>
              </Box>
              {rig.declared && (
                <IconButton
                  size="small"
                  onClick={(event) => removeRig(event, rig.rig_id)}
                  aria-label={`Remove ${rig.rig_name} from this project`}
                  disabled={rigsMut.isPending}
                  sx={{
                    position: "absolute",
                    top: "50%",
                    right: "12px",
                    transform: "translateY(-50%)",
                    color: "text.secondary",
                  }}
                >
                  <CloseIcon sx={{ fontSize: "16px" }} />
                </IconButton>
              )}
            </Box>
          );
        })}

        <Box
          sx={{
            display: "flex",
            minHeight: "44px",
            alignItems: "center",
            gap: "14px",
            px: "16px",
            py: "6px",
          }}
        >
          {addingRig ? (
            <Autocomplete<Rig, false, false, false>
              openOnFocus
              options={rigOptions}
              value={null}
              disabled={rigsMut.isPending}
              onChange={(_event, value) => addRig(value)}
              getOptionDisabled={(option) => declaredIds.has(option.id)}
              getOptionLabel={(option) => `${option.name}${option.active ? "" : " (retired)"}`}
              isOptionEqualToValue={(option, value) => option.id === value.id}
              sx={{ width: 280 }}
              renderInput={(params) => (
                <TextField
                  {...params}
                  autoFocus
                  size="small"
                  placeholder="Choose a rig"
                  inputProps={{ ...params.inputProps, readOnly: true }}
                  onKeyDown={(event) => {
                    if (event.key === "Escape") setAddingRig(false);
                  }}
                />
              )}
            />
          ) : (
            <Button
              size="small"
              startIcon={<AddIcon />}
              onClick={() => setAddingRig(true)}
              sx={{ ml: "-8px", color: "primary.main", fontSize: "13px" }}
            >
              Add a rig
            </Button>
          )}
        </Box>
      </Paper>

      {selectedRig && (
        <Box ref={panelRef} sx={{ display: "flow-root" }}>
          <ProjectRigSetupPanel
            key={selectedRig.rig_id}
            project={project}
            rigSetups={selectedRig}
            onClose={closePanel}
            onChanged={onChanged}
          />
        </Box>
      )}
    </Box>
  );
}
