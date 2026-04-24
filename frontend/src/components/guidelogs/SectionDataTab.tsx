/**
 * Data tab for the Guide Logs section view.
 *
 * Renders a DataGrid over the parsed rows of the currently-selected
 * section — per-frame ``GuidingSample`` rows for guiding sections, or
 * flattened ``CalibrationSample`` rows across all five phases for
 * calibration sections. Below the grid: a compact chronological list
 * of the section's INFO events (settle, dither, lock, alert, …).
 *
 * Pagination UI matches the DSO catalog: ``PaginationActions`` slot
 * (First / Prev / page input / Next / Last) + MUI's default rows-
 * per-page dropdown.
 *
 * Filter UX: columns with closed vocabularies (Type on guiding, Phase
 * on calibration) and the Error column use ``type: "singleSelect"``
 * with ``valueOptions`` so the user gets a dropdown of the actual
 * values present instead of a free-text string filter.
 */
import { useMemo, useState } from "react";
import { DataGrid, type GridColDef } from "@mui/x-data-grid";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";
import type { LogSection } from "@/api/guideLogs";
import PaginationActions from "@/components/common/PaginationActions";
import { formatWallClock } from "@/lib/guideLogFormat";
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

// Sentinel filter value for non-error rows — kept as the literal em-dash
// so what the user sees in the cell matches the filter-dropdown entry.
const NO_ERROR = "—";

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

// Closed vocabulary from the parser — every guiding row's `mount_kind`
// must be one of these, so a fixed list drives the filter dropdown.
const MOUNT_KIND_OPTIONS: Array<"Mount" | "AO" | "DROP"> = ["Mount", "AO", "DROP"];

// Calibration's five phases are fixed too.
const PHASE_OPTIONS: string[] = ["West", "East", "Backlash", "North", "South"];

// ── Calibration-sample grid types ────────────────────────────────────────────

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

// ── Main component ───────────────────────────────────────────────────────────

type ViewMode = "paginated" | "scroll";

export default function SectionDataTab({ section }: Props) {
  // Paginated vs scroll presentation of the guiding DataGrid. Persists
  // across tab switches and section changes within a session.
  const [viewMode, setViewMode] = useState<ViewMode>("paginated");

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

  // Data-driven filter options for the Error column: unique descriptions
  // that actually appear in this section, plus a "no error" entry when
  // any good rows are present. Sorted alphabetically for a stable dropdown.
  const errorOptions = useMemo(() => {
    const descriptions = new Set<string>();
    let hasOkRow = false;
    for (const r of guidingRows) {
      if (r.error_code === 0) {
        hasOkRow = true;
      } else {
        descriptions.add(r.error_description ?? "(no description)");
      }
    }
    const sorted = Array.from(descriptions).sort();
    return hasOkRow ? [NO_ERROR, ...sorted] : sorted;
  }, [guidingRows]);

  const sectionStartIso = section.start_time;

  const guidingColumns = useMemo<GridColDef<GuidingRow>[]>(
    () => [
      { field: "frame", headerName: "Frame", width: 80 },
      {
        field: "time_seconds",
        headerName: "Time (s)",
        width: 90,
        valueFormatter: (v: number) => v.toFixed(2),
      },
      {
        field: "wall_clock",
        headerName: "Clock",
        width: 90,
        // Wall-clock is monotonic with Time(s) within a section — no
        // sort/filter UX value, and filtering on a continuous time
        // value doesn't help anyway.
        sortable: false,
        filterable: false,
        valueGetter: (_v, row) => formatWallClock(sectionStartIso, row.time_seconds),
      },
      {
        field: "mount_kind",
        headerName: "Type",
        width: 95,
        type: "singleSelect",
        valueOptions: MOUNT_KIND_OPTIONS,
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
      { field: "dx_px", headerName: "dx (px)", width: 95, valueFormatter: fmt3 },
      { field: "dy_px", headerName: "dy (px)", width: 95, valueFormatter: fmt3 },
      {
        field: "ra_raw_px",
        headerName: "RA raw (px)",
        width: 110,
        valueFormatter: fmt3,
      },
      {
        field: "dec_raw_px",
        headerName: "Dec raw (px)",
        width: 115,
        valueFormatter: fmt3,
      },
      {
        field: "ra_guide_px",
        headerName: "RA guide (px)",
        width: 120,
        valueFormatter: fmt3,
      },
      {
        field: "dec_guide_px",
        headerName: "Dec guide (px)",
        width: 125,
        valueFormatter: fmt3,
      },
      {
        field: "ra_pulse",
        headerName: "RA pulse",
        width: 105,
        sortable: false,
        valueGetter: (_v, row) =>
          row.ra_duration_ms != null && row.ra_duration_ms > 0
            ? `${row.ra_duration_ms} ms ${row.ra_direction ?? ""}`.trim()
            : "—",
      },
      {
        field: "dec_pulse",
        headerName: "Dec pulse",
        width: 105,
        sortable: false,
        valueGetter: (_v, row) =>
          row.dec_duration_ms != null && row.dec_duration_ms > 0
            ? `${row.dec_duration_ms} ms ${row.dec_direction ?? ""}`.trim()
            : "—",
      },
      { field: "snr", headerName: "SNR", width: 85, valueFormatter: fmt2 },
      { field: "star_mass", headerName: "Mass", width: 95, valueFormatter: fmtInt },
      {
        field: "error",
        headerName: "Error",
        flex: 1,
        minWidth: 200,
        sortable: false,
        type: "singleSelect",
        valueOptions: errorOptions,
        // `valueGetter` drives filtering + sorting — we expose the
        // description (or the NO_ERROR sentinel) so the singleSelect
        // dropdown matches the filter value.
        valueGetter: (_v, row) =>
          row.error_code === 0
            ? NO_ERROR
            : (row.error_description ?? "(no description)"),
        // `renderCell` is the display form — prepend the numeric code
        // so users still see "6: Star lost - mass changed".
        renderCell: (params) => {
          const row = params.row;
          if (row.error_code === 0) return NO_ERROR;
          return `${row.error_code}: ${row.error_description ?? "(no description)"}`;
        },
      },
    ],
    [errorOptions, sectionStartIso],
  );

  const calibrationColumns = useMemo<GridColDef<CalibrationRow>[]>(
    () => [
      {
        field: "direction",
        headerName: "Phase",
        width: 120,
        type: "singleSelect",
        valueOptions: PHASE_OPTIONS,
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
    ],
    [],
  );

  const isGuiding = section.kind === "guiding";

  return (
    <Stack spacing={2} sx={{ height: "100%", minHeight: 0 }}>
      {isGuiding && (
        <Stack direction="row" spacing={1} alignItems="center" sx={{ flexShrink: 0 }}>
          <Typography variant="caption" color="text.secondary">
            View
          </Typography>
          <ViewModeToggle
            value={viewMode}
            onChange={(v) => setViewMode(v)}
          />
          <Typography variant="caption" color="text.secondary" sx={{ ml: 1 }}>
            {viewMode === "paginated"
              ? `${guidingRows.length.toLocaleString()} rows`
              : `${guidingRows.length.toLocaleString()} rows, virtualized scroll`}
          </Typography>
        </Stack>
      )}
      <Paper
        variant="outlined"
        sx={{
          // flex + minHeight: 0 let the grid shrink with the viewport so
          // the paginator footer stays visible even on short windows.
          flex: 1,
          minHeight: 0,
          // DROP-frame rows get a subtle tint so the user can spot
          // errors at a glance without needing a red/green signal.
          "& .guidelogs-drop-row": {
            bgcolor: "action.hover",
          },
        }}
      >
        {isGuiding ? (
          <DataGrid
            // Key forces a remount between paginated and scroll modes so
            // the internal page-size state doesn't leak across.
            key={viewMode}
            rows={guidingRows}
            columns={guidingColumns}
            density="compact"
            disableRowSelectionOnClick
            {...(viewMode === "paginated"
              ? {
                  initialState: {
                    pagination: { paginationModel: { pageSize: 100 } },
                  },
                  pageSizeOptions: [25, 50, 100],
                  slotProps: {
                    basePagination: {
                      ActionsComponent: PaginationActions,
                      // eslint-disable-next-line @typescript-eslint/no-explicit-any
                    } as any,
                  },
                }
              : {
                  // Scroll mode: hide the paginator; render all rows in
                  // a single page. MUI DataGrid's internal virtualization
                  // keeps DOM cost constant regardless of row count, so
                  // a 7 500-row guiding section scrolls smoothly with no
                  // backend round-trips. (All rows are already in memory
                  // from the initial parse — a "true" prefetch-from-DB
                  // model belongs to v0.29.0 when SQLite persistence
                  // lands.)
                  hideFooterPagination: true,
                  initialState: {
                    pagination: {
                      paginationModel: {
                        pageSize: Math.max(1, guidingRows.length),
                      },
                    },
                  },
                  pageSizeOptions: [Math.max(1, guidingRows.length)],
                })}
            getRowClassName={(params) =>
              params.row.mount_kind === "DROP" ? "guidelogs-drop-row" : ""
            }
            sx={{ border: 0 }}
          />
        ) : (
          <DataGrid
            rows={calibrationRows}
            columns={calibrationColumns}
            density="compact"
            disableRowSelectionOnClick
            hideFooterPagination
            hideFooterSelectedRowCount
            sx={{ border: 0 }}
          />
        )}
      </Paper>
      <EventsList section={section} />
    </Stack>
  );
}

// ── View-mode toggle ─────────────────────────────────────────────────────────

function ViewModeToggle({
  value,
  onChange,
}: {
  value: ViewMode;
  onChange: (v: ViewMode) => void;
}) {
  return (
    <ToggleButtonGroup
      value={value}
      exclusive
      size="small"
      onChange={(_, v) => {
        if (v) onChange(v as ViewMode);
      }}
      sx={{ "& .MuiToggleButton-root": { py: 0.25, px: 1, fontSize: 12 } }}
    >
      <ToggleButton value="paginated">Paginated</ToggleButton>
      <ToggleButton value="scroll">Scroll</ToggleButton>
    </ToggleButtonGroup>
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
