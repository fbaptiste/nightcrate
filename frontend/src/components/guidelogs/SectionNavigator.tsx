/**
 * Section navigator — left-column list of sections in a parsed log.
 *
 * Ordered by file position (not timestamp — PHD2 can emit backward-
 * timestamp sections after a clock change). Each row shows type, start
 * time, duration, frame count, and the top-line stat.
 */
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import List from "@mui/material/List";
import ListItemButton from "@mui/material/ListItemButton";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import type { SectionWithMetrics } from "@/api/guideLogs";
import { RIG_BLUE, RIG_ORANGE } from "@/lib/rigColors";

interface Props {
  sections: SectionWithMetrics[];
  selectedIndex: number;
  onSelect: (index: number) => void;
}

export default function SectionNavigator({ sections, selectedIndex, onSelect }: Props) {
  return (
    <Box>
      <Typography variant="overline" sx={{ pl: 1, color: "text.secondary" }}>
        Sections
      </Typography>
      <List dense disablePadding>
        {sections.map((sw) => {
          const s = sw.section;
          const isSel = s.index === selectedIndex;
          const kindColor = s.kind === "guiding" ? RIG_BLUE : RIG_ORANGE;
          const summary = formatSummary(sw);
          const startTime = formatClockTime(s.start_time);
          const durationLabel = formatDuration(sw.metrics.duration_seconds);
          return (
            <ListItemButton
              key={s.index}
              selected={isSel}
              onClick={() => onSelect(s.index)}
              sx={{ borderRadius: 1, mb: 0.5 }}
            >
              <Stack spacing={0.25} sx={{ width: "100%" }}>
                <Stack direction="row" spacing={1} alignItems="center">
                  <Chip
                    label={s.kind === "guiding" ? "Guiding" : "Calibration"}
                    size="small"
                    sx={{
                      bgcolor: kindColor,
                      color: "#ffffff",
                      fontSize: 10,
                      height: 18,
                    }}
                  />
                  <Typography
                    variant="body2"
                    sx={{ fontFamily: "monospace", fontSize: 12 }}
                  >
                    {startTime}
                  </Typography>
                  <Box sx={{ flex: 1 }} />
                  <Typography variant="caption" color="text.secondary">
                    {durationLabel}
                  </Typography>
                </Stack>
                <Typography variant="caption" color="text.secondary" sx={{ pl: 0.25 }}>
                  {summary}
                </Typography>
              </Stack>
            </ListItemButton>
          );
        })}
      </List>
    </Box>
  );
}

function formatSummary(sw: SectionWithMetrics): string {
  const s = sw.section;
  if (s.kind === "guiding") {
    const rms = sw.metrics.rms_total_px;
    const arc = sw.metrics.arcsec_scale;
    const frames = sw.metrics.frame_count_total;
    const errs = sw.metrics.frame_count_error;
    const rmsLabel =
      rms === null ? "no RMS" : arc !== null ? `RMS ${(rms * arc).toFixed(2)}″` : `RMS ${rms.toFixed(2)} px`;
    return errs > 0 ? `${frames} frames · ${rmsLabel} · ${errs} errors` : `${frames} frames · ${rmsLabel}`;
  }
  const west = s.calibration_phases.find((p) => p.direction === "West");
  const north = s.calibration_phases.find((p) => p.direction === "North");
  if (west?.angle_deg !== undefined && west?.angle_deg !== null && north?.angle_deg !== undefined && north?.angle_deg !== null) {
    return `x ${west.angle_deg.toFixed(1)}° · y ${north.angle_deg.toFixed(1)}°`;
  }
  return "Calibration section";
}

function formatDuration(seconds: number): string {
  if (!seconds) return "—";
  if (seconds < 60) return `${seconds.toFixed(0)}s`;
  if (seconds < 3600) {
    const m = Math.floor(seconds / 60);
    return `${m}m`;
  }
  const h = Math.floor(seconds / 3600);
  const m = Math.round((seconds - h * 3600) / 60);
  return `${h}h${String(m).padStart(2, "0")}`;
}

function formatClockTime(isoLike: string): string {
  // Backend sends naive local timestamps; slice the time portion.
  const t = isoLike.includes("T") ? isoLike.split("T")[1] : isoLike.split(" ")[1];
  return t ? t.slice(0, 5) : isoLike;
}
