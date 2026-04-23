/**
 * Top-line metrics table for a guiding section.
 *
 * Dual-unit rendering ("0.42 px / 1.66″") when the section header declared a
 * Pixel scale; pixels-only otherwise. Dual-unit is a display concern — the
 * backend surfaces `arcsec_scale` alongside every metric so the UI doesn't
 * need to re-read the header.
 */
import Box from "@mui/material/Box";
import Grid from "@mui/material/Grid";
import Typography from "@mui/material/Typography";
import type { SectionMetrics } from "@/api/guideLogs";

interface Props {
  metrics: SectionMetrics;
  kind: "calibration" | "guiding";
}

export default function StatsPanel({ metrics, kind }: Props) {
  if (kind === "calibration") {
    return (
      <Box>
        <Typography variant="subtitle2" sx={{ mb: 1 }}>
          Section summary
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Calibration sections don't carry guide-performance metrics. See the
          derived angle + rate values in the plot legend.
        </Typography>
      </Box>
    );
  }

  const scale = metrics.arcsec_scale;
  const renderDist = (px: number | null): string => {
    if (px === null) return "—";
    if (scale === null) return `${px.toFixed(3)} px`;
    return `${px.toFixed(3)} px / ${(px * scale).toFixed(2)}″`;
  };

  const items: Array<{ label: string; value: string }> = [
    { label: "RMS total", value: renderDist(metrics.rms_total_px) },
    { label: "RMS RA", value: renderDist(metrics.rms_ra_px) },
    { label: "RMS Dec", value: renderDist(metrics.rms_dec_px) },
    { label: "Peak RA", value: renderDist(metrics.peak_ra_px) },
    { label: "Peak Dec", value: renderDist(metrics.peak_dec_px) },
    {
      label: "Duration",
      value: formatDuration(metrics.duration_seconds),
    },
    {
      label: "Frames",
      value:
        metrics.frame_count_error > 0
          ? `${metrics.frame_count_total} total · ${metrics.frame_count_error} error`
          : `${metrics.frame_count_total}`,
    },
    {
      label: "Mean SNR",
      value: metrics.mean_snr !== null ? metrics.mean_snr.toFixed(2) : "—",
    },
    {
      label: "Star mass",
      value:
        metrics.mean_star_mass !== null
          ? `${Math.round(metrics.mean_star_mass).toLocaleString()} (mean)`
          : "—",
    },
  ];

  return (
    <Box>
      <Typography variant="subtitle2" sx={{ mb: 1 }}>
        Section summary
      </Typography>
      <Grid container spacing={1}>
        {items.map((item) => (
          <Grid key={item.label} size={{ xs: 6, sm: 4 }}>
            <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
              {item.label}
            </Typography>
            <Typography variant="body2" sx={{ fontVariantNumeric: "tabular-nums" }}>
              {item.value}
            </Typography>
          </Grid>
        ))}
      </Grid>
      {scale === null && (
        <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: "block" }}>
          Pixel scale not declared in header — arcsec values unavailable.
        </Typography>
      )}
    </Box>
  );
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(1)} s`;
  if (seconds < 3600) {
    const m = Math.floor(seconds / 60);
    const s = Math.round(seconds - m * 60);
    return `${m}m ${s}s`;
  }
  const h = Math.floor(seconds / 3600);
  const m = Math.round((seconds - h * 3600) / 60);
  return `${h}h ${m}m`;
}
