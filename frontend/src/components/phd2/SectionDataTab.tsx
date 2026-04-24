/**
 * Data tab for the PHD2 Analyzer section view.
 *
 * Renders a DataTable over the parsed rows of the currently-selected
 * section — per-frame ``GuidingSample`` rows for guiding sections, or
 * flattened ``CalibrationSample`` rows across all five phases for
 * calibration sections. Below the table: a compact chronological list
 * of the section's INFO events (settle, dither, lock, alert, …).
 *
 * Filter controls (Type / Error for guiding, Phase for calibration)
 * live above the grid in the DataTable's filter bar.
 */
import { useMemo } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import type { LogSection } from "@/api/phd2";
import { DataTable } from "@/components/common/DataTable";
import type {
  DataTableColumn,
  DataTableFilter,
} from "@/components/common/DataTable";
import { formatWallClock } from "@/lib/phd2Format";
import { RIG_BLUE, RIG_ORANGE, RIG_TEAL } from "@/lib/rigColors";
import { PHASE_COLORS } from "./CalibrationPlot";

interface Props {
  section: LogSection;
}

// ── Formatters ────────────────────────────────────────────────────────────────

const fmt3 = (v: unknown) => (v == null ? "—" : (v as number).toFixed(3));
const fmt2 = (v: unknown) => (v == null ? "—" : (v as number).toFixed(2));
const fmtInt = (v: unknown) =>
  v == null ? "—" : (v as number).toLocaleString();

// Sentinel filter value for non-error rows — kept as the literal em-dash
// so what the user sees in the cell matches the filter-dropdown entry.
const NO_ERROR = "—";

// ── Row types ────────────────────────────────────────────────────────────────

interface GuidingRow {
  id: number;
  frame: number;
  time_seconds: number;
  wall_clock: string;
  mount_kind: "Mount" | "AO" | "DROP";
  dx_px: number | null;
  dy_px: number | null;
  ra_raw_px: number | null;
  dec_raw_px: number | null;
  ra_guide_px: number | null;
  dec_guide_px: number | null;
  ra_pulse: string;
  dec_pulse: string;
  snr: number | null;
  star_mass: number | null;
  error_code: number;
  error_label: string;
  error_display: string;
}

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

const MOUNT_COLOR: Record<string, string> = {
  Mount: RIG_BLUE,
  AO: RIG_TEAL,
  DROP: RIG_ORANGE,
};

const PHASE_OPTIONS: readonly string[] = [
  "West",
  "East",
  "Backlash",
  "North",
  "South",
];

// ── Main component ───────────────────────────────────────────────────────────

export default function SectionDataTab({ section }: Props) {
  const guidingRows = useMemo<GuidingRow[]>(() => {
    if (section.kind !== "guiding") return [];
    return section.samples.map((s) => ({
      id: s.frame,
      frame: s.frame,
      time_seconds: s.time_seconds,
      wall_clock: formatWallClock(section.start_time, s.time_seconds),
      mount_kind: s.mount_kind,
      dx_px: s.dx_px,
      dy_px: s.dy_px,
      ra_raw_px: s.ra_raw_px,
      dec_raw_px: s.dec_raw_px,
      ra_guide_px: s.ra_guide_px,
      dec_guide_px: s.dec_guide_px,
      ra_pulse:
        s.ra_duration_ms != null && s.ra_duration_ms > 0
          ? `${s.ra_duration_ms} ms ${s.ra_direction ?? ""}`.trim()
          : "—",
      dec_pulse:
        s.dec_duration_ms != null && s.dec_duration_ms > 0
          ? `${s.dec_duration_ms} ms ${s.dec_direction ?? ""}`.trim()
          : "—",
      snr: s.snr,
      star_mass: s.star_mass,
      error_code: s.error_code,
      error_label:
        s.error_code === 0 ? NO_ERROR : (s.error_description ?? "(no description)"),
      error_display:
        s.error_code === 0
          ? NO_ERROR
          : `${s.error_code}: ${s.error_description ?? "(no description)"}`,
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

  const guidingColumns = useMemo<DataTableColumn<GuidingRow>[]>(
    () => [
      { field: "frame", headerName: "Frame", width: 70, align: "right" },
      {
        field: "time_seconds",
        headerName: "Time (s)",
        width: 85,
        align: "right",
        format: (v) => (v as number).toFixed(2),
      },
      { field: "wall_clock", headerName: "Clock", width: 85, sortable: false },
      {
        field: "mount_kind",
        headerName: "Type",
        width: 85,
        renderCell: (row) => (
          <Chip
            label={row.mount_kind}
            size="small"
            sx={{
              bgcolor: MOUNT_COLOR[row.mount_kind],
              color: "#ffffff",
              fontSize: 11,
              height: 20,
            }}
          />
        ),
      },
      { field: "dx_px", headerName: "dx (px)", width: 85, align: "right", format: fmt3 },
      { field: "dy_px", headerName: "dy (px)", width: 85, align: "right", format: fmt3 },
      {
        field: "ra_raw_px",
        headerName: "RA raw (px)",
        width: 100,
        align: "right",
        format: fmt3,
      },
      {
        field: "dec_raw_px",
        headerName: "Dec raw (px)",
        width: 100,
        align: "right",
        format: fmt3,
      },
      {
        field: "ra_guide_px",
        headerName: "RA guide (px)",
        width: 110,
        align: "right",
        format: fmt3,
      },
      {
        field: "dec_guide_px",
        headerName: "Dec guide (px)",
        width: 115,
        align: "right",
        format: fmt3,
      },
      { field: "ra_pulse", headerName: "RA pulse", width: 100, sortable: false },
      { field: "dec_pulse", headerName: "Dec pulse", width: 100, sortable: false },
      { field: "snr", headerName: "SNR", width: 75, align: "right", format: fmt2 },
      { field: "star_mass", headerName: "Mass", width: 85, align: "right", format: fmtInt },
      {
        field: "error_display",
        headerName: "Error",
        flex: 1,
        minWidth: 200,
        sortable: false,
        // Display shows "N: description" but the column's underlying
        // value is already that string.
      },
    ],
    [],
  );

  const calibrationColumns = useMemo<DataTableColumn<CalibrationRow>[]>(
    () => [
      {
        field: "direction",
        headerName: "Phase",
        width: 110,
        renderCell: (row) => (
          <Chip
            label={row.direction}
            size="small"
            sx={{
              bgcolor: PHASE_COLORS[row.direction],
              color: "#ffffff",
              fontSize: 11,
              height: 20,
            }}
          />
        ),
      },
      { field: "step", headerName: "Step", width: 80, align: "right" },
      { field: "dx_px", headerName: "dx (px)", width: 95, align: "right", format: fmt3 },
      { field: "dy_px", headerName: "dy (px)", width: 95, align: "right", format: fmt3 },
      { field: "x_px", headerName: "x (px)", width: 95, align: "right", format: fmt3 },
      { field: "y_px", headerName: "y (px)", width: 95, align: "right", format: fmt3 },
      {
        field: "distance_px",
        headerName: "Distance (px)",
        flex: 1,
        minWidth: 120,
        align: "right",
        format: fmt3,
      },
    ],
    [],
  );

  // Filter definitions. Type + Error apply only to guiding rows; the
  // options for Error are data-driven (each section has its own mix of
  // error descriptions).
  const guidingFilters = useMemo<DataTableFilter<GuidingRow>[]>(
    () => [
      {
        field: "mount_kind",
        label: "Type",
        options: ["Mount", "AO", "DROP"],
        valueGetter: (r) => r.mount_kind,
      },
      {
        field: "error_label",
        label: "Error",
        options: (rows) => {
          const set = new Set<string>();
          let hasOk = false;
          for (const r of rows as GuidingRow[]) {
            if (r.error_code === 0) hasOk = true;
            else set.add(r.error_label);
          }
          const arr = Array.from(set).sort();
          return hasOk ? [NO_ERROR, ...arr] : arr;
        },
        valueGetter: (r) => r.error_label,
      },
    ],
    [],
  );

  const calibrationFilters = useMemo<DataTableFilter<CalibrationRow>[]>(
    () => [
      {
        field: "direction",
        label: "Phase",
        options: PHASE_OPTIONS,
        valueGetter: (r) => r.direction,
      },
    ],
    [],
  );

  return (
    <Stack spacing={2} sx={{ height: "100%", minHeight: 0 }}>
      <Box
        sx={{
          flex: 1,
          minHeight: 0,
          display: "flex",
          flexDirection: "column",
          // DROP-frame rows get a subtle tint so the user can spot
          // errors at a glance without needing a red/green signal.
          "& .phd2-drop-row": {
            bgcolor: "action.hover",
          },
        }}
      >
        {section.kind === "guiding" ? (
          <DataTable
            rows={guidingRows}
            columns={guidingColumns}
            filters={guidingFilters}
            getRowClassName={(r) => (r.mount_kind === "DROP" ? "phd2-drop-row" : undefined)}
            initialSort={{ field: "frame", direction: "asc" }}
            defaultViewMode="scroll"
            defaultPageSize={100}
            pageSizeOptions={[25, 50, 100, 250]}
          />
        ) : (
          <DataTable
            rows={calibrationRows}
            columns={calibrationColumns}
            filters={calibrationFilters}
            defaultViewMode="scroll"
            showViewModeToggle={false}
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
      <Box sx={{ flexShrink: 0 }}>
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
    <Box sx={{ flexShrink: 0 }}>
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
              sx={{ fontFamily: "monospace", minWidth: 78, color: "text.secondary" }}
            >
              {e.time_seconds != null
                ? formatWallClock(section.start_time, e.time_seconds)
                : "—"}
            </Typography>
            <Typography
              variant="caption"
              sx={{ fontFamily: "monospace", minWidth: 60, color: "text.secondary" }}
            >
              {e.time_seconds != null ? `${e.time_seconds.toFixed(1)}s` : ""}
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
