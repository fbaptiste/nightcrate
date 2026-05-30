import Box from "@mui/material/Box";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { RIG_BLUE } from "@/lib/rigColors";
import { lineLabel } from "@/lib/lineNames";
import type { IntegrationSummary } from "@/api/projectSessions";

export function formatHoursMinutes(minutes: number): string {
  const total = Math.round(minutes);
  const h = Math.floor(total / 60);
  const m = total % 60;
  if (h === 0) return `${m}m`;
  if (m === 0) return `${h}h`;
  return `${h}h ${m}m`;
}

interface Props {
  summary: IntegrationSummary;
}

// Per-filter integration: a horizontal bar of actual time with a goal marker.
// Blue fill / neutral goal tick keep it colorblind-safe (no red/green).
export default function IntegrationBars({ summary }: Props) {
  if (summary.lines.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary">
        No integration yet. Add imaging sessions to track time per filter.
      </Typography>
    );
  }

  // Scale every bar against the largest actual-or-goal value across all lines.
  const scale = Math.max(
    1,
    ...summary.lines.map((l) => Math.max(l.actual_minutes, l.goal_minutes ?? 0)),
  );

  return (
    <Box sx={{ maxWidth: 520 }}>
      <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1 }}>
        Integration — {formatHoursMinutes(summary.total_actual_minutes)} total
      </Typography>

      <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
        {summary.lines.map((line) => {
          const actualPct = (line.actual_minutes / scale) * 100;
          const goalPct = line.goal_minutes ? (line.goal_minutes / scale) * 100 : null;
          const valueText =
            line.goal_minutes != null
              ? `${formatHoursMinutes(line.actual_minutes)} / ${formatHoursMinutes(
                  line.goal_minutes,
                )} (${Math.round((line.actual_minutes / line.goal_minutes) * 100)}%)`
              : formatHoursMinutes(line.actual_minutes);

          return (
            <Box key={line.line_name} sx={{ display: "flex", alignItems: "center", gap: 1 }}>
              <Tooltip title={lineLabel(line.line_name)} placement="left">
                <Typography
                  variant="body2"
                  sx={{ width: 44, flexShrink: 0, fontWeight: 600, cursor: "default" }}
                >
                  {line.line_name}
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
                    width: `${Math.min(actualPct, 100)}%`,
                    bgcolor: RIG_BLUE,
                    borderRadius: 0.5,
                  }}
                />
                {goalPct != null && (
                  <Tooltip title={`Goal: ${formatHoursMinutes(line.goal_minutes!)}`}>
                    <Box
                      sx={{
                        position: "absolute",
                        top: -2,
                        bottom: -2,
                        left: `${Math.min(goalPct, 100)}%`,
                        width: 2,
                        bgcolor: "text.primary",
                      }}
                    />
                  </Tooltip>
                )}
              </Box>

              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ width: 150, flexShrink: 0, textAlign: "left" }}
              >
                {valueText}
              </Typography>
            </Box>
          );
        })}
      </Box>
    </Box>
  );
}
