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
import { useMemo, useState } from "react";
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

// Null → empty cell convention across every numeric column. The
// em-dash signalled "missing" but cluttered the grid; blank reads as
// missing just as clearly and keeps the eye on the data that IS there.
const fmt3 = (v: unknown) => (v == null ? "" : (v as number).toFixed(3));
const fmt2 = (v: unknown) => (v == null ? "" : (v as number).toFixed(2));
const fmtInt = (v: unknown) => (v == null ? "" : (v as number).toLocaleString());

// Sentinel filter-key for rows without an error. Intentionally empty
// so the Error cell and filter dropdown both stay blank for non-error
// rows — the filter options surface only real error descriptions.
const NO_ERROR = "";

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
  // Pulse split into numeric value + direction so users can sort by
  // pulse size (the value column's natural numeric sort) without the
  // direction letter polluting the sort order.
  ra_pulse_ms: number | null;
  ra_pulse_dir: "W" | "E" | null;
  dec_pulse_ms: number | null;
  dec_pulse_dir: "N" | "S" | null;
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
  // Frame number to scroll to + auto-expand; set by EventsList clicks,
  // cleared by DataTable once the scroll completes.
  const [scrollTarget, setScrollTarget] = useState<number | null>(null);

  // Events are anchored per-frame in the parser — an event's time_seconds
  // matches the time of the sample row immediately before it. Build a
  // lookup from frame → events so the DataTable can render an expand
  // chip on rows that have associated events.
  const eventsByFrame = useMemo(() => {
    const map = new Map<number, typeof section.events>();
    if (section.kind !== "guiding") return map;
    // Group events by the frame whose time matches the event's anchor.
    // `_peek_sample_time_seconds` rounds to 0 decimals for locale-recovered
    // rows, so we match within 0.01s tolerance to be safe.
    const framesByTime = new Map<number, number>();
    for (const s of section.samples) {
      // Round to 2 decimals — matches parser's precision.
      framesByTime.set(Math.round(s.time_seconds * 100), s.frame);
    }
    for (const e of section.events) {
      if (e.time_seconds == null) continue;
      const key = Math.round(e.time_seconds * 100);
      // Try exact match first, then search a small window.
      let frame = framesByTime.get(key);
      if (frame == null) {
        for (let delta = 1; delta <= 3 && frame == null; delta++) {
          frame = framesByTime.get(key - delta) ?? framesByTime.get(key + delta);
        }
      }
      if (frame == null) continue;
      const list = map.get(frame) ?? [];
      list.push(e);
      map.set(frame, list);
    }
    return map;
  }, [section]);

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
      ra_pulse_ms:
        s.ra_duration_ms != null && s.ra_duration_ms > 0 ? s.ra_duration_ms : null,
      ra_pulse_dir: s.ra_duration_ms != null && s.ra_duration_ms > 0 ? s.ra_direction : null,
      dec_pulse_ms:
        s.dec_duration_ms != null && s.dec_duration_ms > 0 ? s.dec_duration_ms : null,
      dec_pulse_dir:
        s.dec_duration_ms != null && s.dec_duration_ms > 0 ? s.dec_direction : null,
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
      {
        field: "frame",
        headerName: "Frame",
        width: 110,
        // Keep the default right-align for the number; expand chip
        // floats on the left of the cell via a flex row.
        renderCell: (row, api) => {
          const events = eventsByFrame.get(row.frame);
          return (
            <Stack
              direction="row"
              alignItems="center"
              spacing={0.5}
              sx={{ width: "100%", justifyContent: "flex-end" }}
            >
              {events && events.length > 0 && (
                <Chip
                  label={events.length}
                  size="small"
                  onClick={(e) => {
                    e.stopPropagation();
                    api.toggleExpand();
                  }}
                  sx={{
                    height: 18,
                    fontSize: 10,
                    fontWeight: 600,
                    cursor: "pointer",
                    bgcolor: api.isExpanded ? "primary.main" : "primary.light",
                    color: "#ffffff",
                    "& .MuiChip-label": { px: 0.75 },
                  }}
                />
              )}
              <Typography
                component="span"
                sx={{ fontFamily: "inherit", fontSize: "inherit" }}
              >
                {row.frame}
              </Typography>
            </Stack>
          );
        },
      },
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
      {
        field: "ra_pulse_ms",
        headerName: "RA pulse (ms)",
        width: 105,
        align: "right",
        format: fmtInt,
      },
      { field: "ra_pulse_dir", headerName: "RA dir", width: 75, align: "center" },
      {
        field: "dec_pulse_ms",
        headerName: "Dec pulse (ms)",
        width: 110,
        align: "right",
        format: fmtInt,
      },
      { field: "dec_pulse_dir", headerName: "Dec dir", width: 78, align: "center" },
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
    [eventsByFrame],
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
        // Only actual error descriptions in the filter dropdown —
        // no "no error" sentinel, since filtering to non-error rows
        // isn't a common use-case and the sentinel clutters the list.
        options: (rows) => {
          const set = new Set<string>();
          for (const r of rows as GuidingRow[]) {
            if (r.error_code !== 0) set.add(r.error_label);
          }
          return Array.from(set).sort();
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
    <Stack spacing={2} sx={{ height: "100%", minHeight: 0, minWidth: 0 }}>
      <Box
        sx={{
          flex: 1,
          minHeight: 0,
          minWidth: 0,
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
            isExpandable={(r) => (eventsByFrame.get(r.frame)?.length ?? 0) > 0}
            expandedHeight={(r) =>
              24 + (eventsByFrame.get(r.frame)?.length ?? 0) * 24
            }
            scrollToRowId={scrollTarget}
            onRowScrolledTo={() => setScrollTarget(null)}
            renderExpanded={(r) => {
              const events = eventsByFrame.get(r.frame) ?? [];
              if (events.length === 0) return null;
              return (
                <Stack spacing={0.5}>
                  {events.map((e, i) => (
                    <Stack
                      key={i}
                      direction="row"
                      spacing={1}
                      alignItems="center"
                      sx={{ fontSize: 12 }}
                    >
                      <Chip
                        label={e.kind}
                        size="small"
                        variant="outlined"
                        sx={{ fontSize: 10, height: 18, minWidth: 110 }}
                      />
                      <Typography
                        variant="caption"
                        sx={{
                          fontFamily: "monospace",
                          color: "text.secondary",
                          minWidth: 72,
                        }}
                      >
                        {e.time_seconds != null
                          ? formatWallClock(section.start_time, e.time_seconds)
                          : "—"}
                      </Typography>
                      <Typography variant="body2" sx={{ color: "text.primary", flex: 1 }}>
                        {e.raw_message}
                      </Typography>
                    </Stack>
                  ))}
                </Stack>
              );
            }}
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
      <EventsList
        section={section}
        eventsByFrame={eventsByFrame}
        onEventClick={section.kind === "guiding" ? setScrollTarget : undefined}
      />
    </Stack>
  );
}

// ── Events list (secondary panel) ────────────────────────────────────────────

interface EventsListProps {
  section: LogSection;
  eventsByFrame: Map<number, LogSection["events"]>;
  onEventClick?: (frame: number) => void;
}

function EventsList({ section, eventsByFrame, onEventClick }: EventsListProps) {
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

  // Reverse lookup: each event → its frame (by reference identity).
  const frameByEvent = new Map<LogSection["events"][number], number>();
  for (const [frame, evs] of eventsByFrame.entries()) {
    for (const ev of evs) frameByEvent.set(ev, frame);
  }

  return (
    <Box sx={{ flexShrink: 0 }}>
      <Typography variant="overline" color="text.secondary">
        Events ({section.events.length})
      </Typography>
      <Stack spacing={0.25} sx={{ maxHeight: 200, overflow: "auto", pr: 1 }}>
        {section.events.map((e, i) => {
          const frame = frameByEvent.get(e);
          const clickable = onEventClick != null && frame != null;
          return (
            <Stack
              key={i}
              direction="row"
              spacing={1}
              alignItems="center"
              onClick={clickable ? () => onEventClick!(frame!) : undefined}
              sx={{
                fontSize: 12,
                py: 0.25,
                borderRadius: 0.5,
                cursor: clickable ? "pointer" : "default",
                "&:hover": clickable ? { bgcolor: "action.hover" } : undefined,
              }}
            >
              <Typography
                variant="caption"
                sx={{ fontFamily: "monospace", minWidth: 78, color: "text.secondary" }}
              >
                {e.time_seconds != null
                  ? formatWallClock(section.start_time, e.time_seconds)
                  : ""}
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
              {frame != null && (
                <Typography
                  variant="caption"
                  sx={{
                    fontFamily: "monospace",
                    color: "text.secondary",
                    fontSize: 10,
                  }}
                >
                  #{frame}
                </Typography>
              )}
            </Stack>
          );
        })}
      </Stack>
    </Box>
  );
}
