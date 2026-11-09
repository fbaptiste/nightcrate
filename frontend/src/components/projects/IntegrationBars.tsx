import Box from "@mui/material/Box";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import type { IntegrationSummary } from "@/api/projectSessions";
import FilterSwatch from "./FilterSwatch";
import { compareFilters, resolveFilterLabel } from "./filterColors";

// Shared with the sessions exposure table and gallery read-outs.
// eslint-disable-next-line react-refresh/only-export-components
export function formatHoursMinutes(minutes: number): string {
  const total = Math.round(minutes);
  // Short subs are real time: 10 x 2 s must not read as nothing captured.
  if (total === 0 && minutes > 0) return "<1m";
  const h = Math.floor(total / 60);
  const m = total % 60;
  if (h === 0) return `${m}m`;
  if (m === 0) return `${h}h`;
  return `${h}h ${m}m`;
}

const ELLIPSIS = {
  overflow: "hidden",
  textOverflow: "ellipsis",
  whiteSpace: "nowrap",
} as const;

interface Props {
  summary: IntegrationSummary;
  compact?: boolean;
  showHeading?: boolean;
}

// Per-filter integration: a horizontal bar of actual time per filter. A read-out,
// not a tracker — per-filter goals were removed in v0.41.1.
export default function IntegrationBars({
  summary,
  compact = false,
  showHeading = true,
}: Props) {
  // Every session holds time, so a zero total means no sessions. Empty `lines`
  // alone does not: a broadband filter (UV/IR cut, L-Pro) has no line to credit.
  if (summary.total_actual_minutes === 0) {
    return (
      <Typography variant="body2" color="text.secondary">
        No integration yet. Add an imaging session, or derive sessions from your cataloged
        sub frames, to track time per filter.
      </Typography>
    );
  }

  // Scale every bar against the largest value, so the longest bar fills the track.
  const scale = Math.max(1, ...summary.lines.map((l) => l.actual_minutes));
  const lines = summary.lines
    .map((line) => ({ ...line, filter: resolveFilterLabel(line.label) }))
    .sort((a, b) => compareFilters(a.filter, b.filter));

  return (
    <Box sx={{ maxWidth: compact ? "none" : 560 }}>
      {showHeading && (
        <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1 }}>
          Integration — {formatHoursMinutes(summary.total_actual_minutes)} total
        </Typography>
      )}

      {summary.lines.length === 0 && (
        <Typography variant="body2" color="text.secondary">
          None of these filters has a known bandpass, so the time has no line to
          count toward.
        </Typography>
      )}

      <Box sx={{ display: "flex", flexDirection: "column", gap: compact ? "6px" : 1 }}>
        {lines.map((line) => (
          <Box
            key={line.label}
            sx={{ display: "flex", alignItems: "center", gap: compact ? "12px" : 1 }}
          >
            {/* The label is a free string — a canonical bandpass, or a filter
                name straight from the FITS header. Truncate rather than wrap. */}
            <Tooltip title={line.label} placement="left">
              <Typography
                variant="body2"
                sx={{
                  width: compact ? 48 : 120,
                  flexShrink: 0,
                  fontSize: compact ? "13px" : undefined,
                  lineHeight: compact ? 1.45 : undefined,
                  fontWeight: compact ? 400 : 600,
                  cursor: "default",
                  ...ELLIPSIS,
                }}
              >
                {line.label}
              </Typography>
            </Tooltip>

            <Box
              sx={{
                position: "relative",
                flexGrow: 1,
                height: compact ? 12 : 18,
                borderRadius: compact ? "3px" : 0.5,
                bgcolor: compact
                  ? (theme) => (theme.palette.mode === "dark" ? "#31343a" : "#ebe8e3")
                  : "action.hover",
                overflow: "hidden",
              }}
            >
              <Box
                sx={{
                  position: "absolute",
                  inset: 0,
                  width: `${Math.min((line.actual_minutes / scale) * 100, 100)}%`,
                  borderRadius: compact ? "3px" : 0.5,
                  overflow: "hidden",
                }}
              >
                <FilterSwatch
                  filter={line.filter}
                  width="100%"
                  height="100%"
                  borderRadius="inherit"
                  outlineWidth={1.5}
                  display="block"
                />
              </Box>
            </Box>

            <Typography
              variant="caption"
              color="text.secondary"
              sx={{
                width: compact ? 64 : 120,
                flexShrink: 0,
                textAlign: compact ? "right" : "left",
                fontSize: compact ? "13px" : undefined,
                lineHeight: compact ? 1.45 : undefined,
                fontVariantNumeric: compact ? "tabular-nums" : undefined,
              }}
            >
              {formatHoursMinutes(line.actual_minutes)}
            </Typography>
          </Box>
        ))}
      </Box>
    </Box>
  );
}
