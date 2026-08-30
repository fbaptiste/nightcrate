import Box from "@mui/material/Box";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { RIG_BLUE } from "@/lib/rigColors";
import type { IntegrationSummary } from "@/api/projectSessions";

export function formatHoursMinutes(minutes: number): string {
  const total = Math.round(minutes);
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
}

// Per-filter integration: a horizontal bar of actual time per filter. A read-out,
// not a tracker — per-filter goals were removed in v0.41.1. Blue fill keeps it
// colorblind-safe (no red/green).
export default function IntegrationBars({ summary }: Props) {
  if (summary.lines.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary">
        No integration yet. Add an imaging session, or derive sessions from your cataloged
        sub frames, to track time per filter.
      </Typography>
    );
  }

  // Scale every bar against the largest value, so the longest bar fills the track.
  const scale = Math.max(1, ...summary.lines.map((l) => l.actual_minutes));

  return (
    <Box sx={{ maxWidth: 560 }}>
      <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1 }}>
        Integration — {formatHoursMinutes(summary.total_actual_minutes)} total
      </Typography>

      <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
        {summary.lines.map((line) => (
          <Box key={line.label} sx={{ display: "flex", alignItems: "center", gap: 1 }}>
            {/* The label is a free string — a canonical bandpass, or a filter
                name straight from the FITS header. Truncate rather than wrap. */}
            <Tooltip title={line.label} placement="left">
              <Typography
                variant="body2"
                sx={{ width: 120, flexShrink: 0, fontWeight: 600, cursor: "default", ...ELLIPSIS }}
              >
                {line.label}
              </Typography>
            </Tooltip>

            <Box
              sx={{
                position: "relative",
                flexGrow: 1,
                height: 18,
                borderRadius: 0.5,
                bgcolor: "action.hover",
                overflow: "hidden",
              }}
            >
              <Box
                sx={{
                  position: "absolute",
                  inset: 0,
                  width: `${Math.min((line.actual_minutes / scale) * 100, 100)}%`,
                  bgcolor: RIG_BLUE,
                  borderRadius: 0.5,
                }}
              />
            </Box>

            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ width: 120, flexShrink: 0, textAlign: "left" }}
            >
              {formatHoursMinutes(line.actual_minutes)}
            </Typography>
          </Box>
        ))}
      </Box>
    </Box>
  );
}
