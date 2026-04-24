/**
 * Data tab for the Guide Logs section view.
 *
 * Renders a DataGrid over the parsed rows of the currently-selected
 * section — per-frame ``GuidingSample`` rows for guiding sections, or
 * flattened ``CalibrationSample`` rows across all five phases for
 * calibration sections. Below the grid: a compact chronological list
 * of the section's INFO events (settle, dither, lock, alert, …).
 */
import { useMemo } from "react";
import { DataGrid, type GridColDef } from "@mui/x-data-grid";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import type { LogSection } from "@/api/guideLogs";
import { RIG_BLUE, RIG_ORANGE, RIG_TEAL } from "@/lib/rigColors";
import { PHASE_COLORS } from "./CalibrationPlot";

interface Props {
  section: LogSection;
}

// ── Formatters ────────────────────────────────────────────────────────────────

const fmt3 = (v: number | null | undefined) => (v == null ? "—" : v.toFixed(3));
const fmt2 = (v: number | null | undefined) => (v == null ? "—" : v.toFixed(2));
const fmtInt = (v: number | null | undefined) =>
  v == null ? "—" : v.toLocaleString();

// ── Guiding-sample grid ──────────────────────────────────────────────────────

interface GuidingRow {
  id: number;
  frame: number;
  time_seconds: number;
  mount_kind: "Mount" | "AO" | "DROP";
  dx_px: number | null;
  dy_px: number | null;
  ra_raw_px: number | null;
  dec_raw_px: number | null;
  ra_guide_px: number | null;
  dec_guide_px: number | null;
  ra_duration_ms: number | null;
  ra_direction: "W" | "E" | null;
  dec_duration_ms: number | null;
  dec_direction: "N" | "S" | null;
  snr: number | null;
  star_mass: number | null;
  error_code: number;
  error_description: string | null;
}

const MOUNT_COLOR: Record<string, string> = {
  Mount: RIG_BLUE,
  AO: RIG_TEAL,
  DROP: RIG_ORANGE,
};

const GUIDING_COLUMNS: GridColDef<GuidingRow>[] = [
  { field: "frame", headerName: "Frame", width: 70 },
  {
    field: "time_seconds",
    headerName: "Time (s)",
    width: 85,
    valueFormatter: (v: number) => v.toFixed(2),
  },
  {
    field: "mount_kind",
    headerName: "Type",
    width: 85,
    renderCell: (params) => (
      <Chip
        label={params.value}
        size="small"
        sx={{
          bgcolor: MOUNT_COLOR[params.value as string],
          color: "#ffffff",
          fontSize: 11,
          height: 20,
        }}
      />
    ),
  },
  { field: "dx_px", headerName: "dx (px)", width: 90, valueFormatter: fmt3 },
  { field: "dy_px", headerName: "dy (px)", width: 90, valueFormatter: fmt3 },
  { field: "ra_raw_px", headerName: "RA raw (px)", width: 100, valueFormatter: fmt3 },
  { field: "dec_raw_px", headerName: "Dec raw (px)", width: 105, valueFormatter: fmt3 },
  { field: "ra_guide_px", headerName: "RA guide (px)", width: 110, valueFormatter: fmt3 },
  { field: "dec_guide_px", headerName: "Dec guide (px)", width: 115, valueFormatter: fmt3 },
  {
    field: "ra_pulse",
    headerName: "RA pulse",
    width: 100,
    sortable: false,
    valueGetter: (_v, row) =>
      row.ra_duration_ms != null && row.ra_duration_ms > 0
        ? `${row.ra_duration_ms} ms ${row.ra_direction ?? ""}`.trim()
        : "—",
  },
  {
    field: "dec_pulse",
    headerName: "Dec pulse",
    width: 100,
    sortable: false,
    valueGetter: (_v, row) =>
      row.dec_duration_ms != null && row.dec_duration_ms > 0
        ? `${row.dec_duration_ms} ms ${row.dec_direction ?? ""}`.trim()
        : "—",
  },
  { field: "snr", headerName: "SNR", width: 80, valueFormatter: fmt2 },
  { field: "star_mass", headerName: "Mass", width: 90, valueFormatter: fmtInt },
  {
    field: "error",
    headerName: "Error",
    flex: 1,
    minWidth: 180,
    sortable: false,
    valueGetter: (_v, row) =>
      row.error_code === 0
        ? "—"
        : `${row.error_code}: ${row.error_description ?? "(no description)"}`,
  },
];

// ── Calibration-sample grid ──────────────────────────────────────────────────

interface CalibrationRow {
  id: string;
  direction: string;
  step: number;
  dx_px: number;
  dy_px: number;
  x_px: number;
  y_px: number;
  distance_px: number;
}

const CALIBRATION_COLUMNS: GridColDef<CalibrationRow>[] = [
  {
    field: "direction",
    headerName: "Phase",
    width: 110,
    renderCell: (params) => (
      <Chip
        label={params.value}
        size="small"
        sx={{
          bgcolor: PHASE_COLORS[params.value as string],
          color: "#ffffff",
          fontSize: 11,
          height: 20,
        }}
      />
    ),
  },
  { field: "step", headerName: "Step", width: 80 },
  { field: "dx_px", headerName: "dx (px)", width: 95, valueFormatter: fmt3 },
  { field: "dy_px", headerName: "dy (px)", width: 95, valueFormatter: fmt3 },
  { field: "x_px", headerName: "x (px)", width: 95, valueFormatter: fmt3 },
  { field: "y_px", headerName: "y (px)", width: 95, valueFormatter: fmt3 },
  {
    field: "distance_px",
    headerName: "Distance (px)",
    flex: 1,
    minWidth: 120,
    valueFormatter: fmt3,
  },
];

// ── Main component ───────────────────────────────────────────────────────────

export default function SectionDataTab({ section }: Props) {
  const guidingRows = useMemo<GuidingRow[]>(() => {
    if (section.kind !== "guiding") return [];
    return section.samples.map((s) => ({
      id: s.frame,
      frame: s.frame,
      time_seconds: s.time_seconds,
      mount_kind: s.mount_kind,
      dx_px: s.dx_px,
      dy_px: s.dy_px,
      ra_raw_px: s.ra_raw_px,
      dec_raw_px: s.dec_raw_px,
      ra_guide_px: s.ra_guide_px,
      dec_guide_px: s.dec_guide_px,
      ra_duration_ms: s.ra_duration_ms,
      ra_direction: s.ra_direction,
      dec_duration_ms: s.dec_duration_ms,
      dec_direction: s.dec_direction,
      snr: s.snr,
      star_mass: s.star_mass,
      error_code: s.error_code,
      error_description: s.error_description,
    }));
  }, [section]);

  const calibrationRows = useMemo<CalibrationRow[]>(() => {
    if (section.kind !== "calibration") return [];
    return section.calibration_phases.flatMap((p) =>
      p.samples.map((s, i) => ({
        id: `${p.direction}-${i}`,
        direction: p.direction,
        step: s.step,
        dx_px: s.dx_px,
        dy_px: s.dy_px,
        x_px: s.x_px,
        y_px: s.y_px,
        distance_px: s.distance_px,
      })),
    );
  }, [section]);

  return (
    <Stack spacing={2} sx={{ height: "100%", minHeight: 0 }}>
      <Box
        sx={{
          flex: 1,
          minHeight: 320,
          // DROP-frame rows get a subtle tint so the user can spot
          // errors at a glance without needing a red/green signal.
          "& .guidelogs-drop-row": {
            bgcolor: "action.hover",
          },
        }}
      >
        {section.kind === "guiding" ? (
          <DataGrid
            rows={guidingRows}
            columns={GUIDING_COLUMNS}
            density="compact"
            disableRowSelectionOnClick
            initialState={{
              pagination: { paginationModel: { pageSize: 100 } },
            }}
            pageSizeOptions={[50, 100, 250, 500]}
            getRowClassName={(params) =>
              params.row.mount_kind === "DROP" ? "guidelogs-drop-row" : ""
            }
          />
        ) : (
          <DataGrid
            rows={calibrationRows}
            columns={CALIBRATION_COLUMNS}
            density="compact"
            disableRowSelectionOnClick
            hideFooterPagination
            hideFooterSelectedRowCount
          />
        )}
      </Box>
      <EventsList section={section} />
    </Stack>
  );
}

// ── Events list (secondary panel) ────────────────────────────────────────────

function EventsList({ section }: { section: LogSection }) {
  if (section.events.length === 0) {
    return (
      <Box>
        <Typography variant="overline" color="text.secondary">
          Events
        </Typography>
        <Typography variant="body2" color="text.secondary">
          No events in this section.
        </Typography>
      </Box>
    );
  }

  return (
    <Box>
      <Typography variant="overline" color="text.secondary">
        Events ({section.events.length})
      </Typography>
      <Stack spacing={0.5} sx={{ maxHeight: 200, overflow: "auto", pr: 1 }}>
        {section.events.map((e, i) => (
          <Stack
            key={i}
            direction="row"
            spacing={1}
            alignItems="center"
            sx={{ fontSize: 12 }}
          >
            <Typography
              variant="caption"
              sx={{ fontFamily: "monospace", minWidth: 64, color: "text.secondary" }}
            >
              {e.time_seconds != null ? `${e.time_seconds.toFixed(1)}s` : "—"}
            </Typography>
            <Chip
              label={e.kind}
              size="small"
              variant="outlined"
              sx={{ fontSize: 10, height: 18 }}
            />
            <Typography variant="body2" sx={{ color: "text.secondary", flex: 1 }}>
              {e.raw_message}
            </Typography>
          </Stack>
        ))}
      </Stack>
    </Box>
  );
}
