/**
 * Top-line metrics table for a guiding section.
 *
 * Dual-unit rendering ("0.42 px / 1.66″") when the section header declared a
 * Pixel scale; pixels-only otherwise. Dual-unit is a display concern — the
 * backend surfaces `arcsec_scale` alongside every metric so the UI doesn't
 * need to re-read the header.
 */
import { useState } from "react";
import Box from "@mui/material/Box";
import Collapse from "@mui/material/Collapse";
import Grid from "@mui/material/Grid";
import IconButton from "@mui/material/IconButton";
import Snackbar from "@mui/material/Snackbar";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import type { SectionMetrics } from "@/api/phd2";

interface Props {
  metrics: SectionMetrics;
  kind: "calibration" | "guiding";
  /** Heading above the metrics grid. Defaults to "Section summary"
   *  for the section-wide panel; the Viewport Summary panel overrides
   *  with its own label. */
  title?: string;
  /** Optional second-line caption under the title — used by the
   *  Viewport Summary to show "N / M frames visible". */
  subtitle?: string;
  /** When true, the title row becomes a click target with a chevron
   *  that collapses the metrics grid. */
  collapsible?: boolean;
  /** Initial expanded state when ``collapsible``. Default true. */
  defaultExpanded?: boolean;
}

export default function StatsPanel({
  metrics,
  kind,
  title = "Section summary",
  subtitle,
  collapsible = false,
  defaultExpanded = true,
}: Props) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const [copiedOpen, setCopiedOpen] = useState(false);
  const isOpen = collapsible ? expanded : true;
  const toggle = () => collapsible && setExpanded((v) => !v);

  const header = (
    <Stack
      direction="row"
      alignItems="center"
      spacing={0.5}
      onClick={toggle}
      sx={{
        cursor: collapsible ? "pointer" : "default",
        userSelect: "none",
        mb: subtitle || !isOpen ? 0.25 : 1,
      }}
    >
      {collapsible && (
        <ExpandMoreIcon
          fontSize="small"
          sx={{
            transition: "transform 120ms ease",
            transform: isOpen ? "rotate(0deg)" : "rotate(-90deg)",
            color: "text.secondary",
          }}
        />
      )}
      <Typography variant="subtitle2">{title}</Typography>
      {kind === "guiding" && (
        <Tooltip title="Copy stats to clipboard (TSV)">
          <IconButton
            size="small"
            sx={{ ml: 0.5, p: 0.25 }}
            onClick={(ev) => {
              // Stop propagation so clicking the icon doesn't also
              // toggle the collapse state.
              ev.stopPropagation();
              handleCopy();
            }}
          >
            <ContentCopyIcon sx={{ fontSize: 14 }} />
          </IconButton>
        </Tooltip>
      )}
    </Stack>
  );

  const subtitleNode = subtitle && (
    <Typography
      variant="caption"
      color="text.secondary"
      sx={{ display: "block", mb: isOpen ? 1 : 0, pl: collapsible ? 3 : 0 }}
    >
      {subtitle}
    </Typography>
  );
  if (kind === "calibration") {
    return (
      <Box>
        {header}
        {subtitleNode}
        <Collapse in={isOpen} unmountOnExit>
          <Typography variant="body2" color="text.secondary">
            Calibration sections don't carry guide-performance metrics. See the
            derived angle + rate values in the plot legend.
          </Typography>
        </Collapse>
      </Box>
    );
  }

  const scale = metrics.arcsec_scale;
  const renderDist = (px: number | null): string => {
    if (px === null) return "—";
    if (scale === null) return `${px.toFixed(3)} px`;
    return `${px.toFixed(3)} px / ${(px * scale).toFixed(2)}″`;
  };
  const renderDrift = (pxPerMin: number | null): string => {
    if (pxPerMin === null) return "—";
    // Sign-preserving; no absolute value. 3 decimals for px (typical
    // values sub-pixel per minute), 2 for arcsec.
    if (scale === null) return `${pxPerMin.toFixed(3)} px/min`;
    return `${pxPerMin.toFixed(3)} px/min / ${(pxPerMin * scale).toFixed(2)}″/min`;
  };
  const renderOscillation = (frac: number | null): string => {
    if (frac === null) return "—";
    return `${(frac * 100).toFixed(1)}%`;
  };

  const items: Array<{ label: string; value: string }> = [
    { label: "RMS total", value: renderDist(metrics.rms_total_px) },
    { label: "RMS RA", value: renderDist(metrics.rms_ra_px) },
    { label: "RMS Dec", value: renderDist(metrics.rms_dec_px) },
    { label: "Peak RA", value: renderDist(metrics.peak_ra_px) },
    { label: "Peak Dec", value: renderDist(metrics.peak_dec_px) },
    { label: "Drift RA", value: renderDrift(metrics.drift_ra_px_per_min) },
    { label: "Drift Dec", value: renderDrift(metrics.drift_dec_px_per_min) },
    { label: "Osc RA", value: renderOscillation(metrics.oscillation_ra) },
    { label: "Osc Dec", value: renderOscillation(metrics.oscillation_dec) },
    {
      label: "Duration",
      value: formatDuration(metrics.duration_seconds),
    },
    {
      label: "Frames",
      value: formatFrameCount(metrics),
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

  const handleCopy = () => {
    // Tab-separated metric rows, prefixed with the panel title and
    // optional subtitle. Matches PHD2's own copy-stats output so the
    // text pastes cleanly into a spreadsheet or the PHD2 forum.
    const header = subtitle ? `${title}\t${subtitle}` : title;
    const body = items.map((i) => `${i.label}\t${i.value}`).join("\n");
    const tsv = `${header}\n${body}`;
    // ``navigator.clipboard`` requires a secure context — in local
    // dev (http://localhost) this is granted; swallow failures
    // quietly if the browser refuses.
    void navigator.clipboard
      ?.writeText(tsv)
      .then(() => setCopiedOpen(true))
      .catch(() => {
        /* clipboard blocked — skip feedback */
      });
  };

  return (
    <Box>
      {header}
      {subtitleNode}
      <Collapse in={isOpen} unmountOnExit>
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
      </Collapse>
      <Snackbar
        open={copiedOpen}
        autoHideDuration={1500}
        onClose={() => setCopiedOpen(false)}
        message="Stats copied to clipboard"
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      />
    </Box>
  );
}

/** Render the frames-row value with an optional "N total · M in stats ·
 *  K in settle" decomposition when settle exclusion actually removed
 *  frames. Falls back to "N total · K error" and "N" for the simpler
 *  cases. */
function formatFrameCount(metrics: SectionMetrics): string {
  const t = metrics.frame_count_total.toLocaleString();
  const parts: string[] = [`${t} total`];
  if (metrics.frame_count_in_settle > 0) {
    parts.push(`${metrics.frame_count_in_stats.toLocaleString()} in stats`);
    parts.push(`${metrics.frame_count_in_settle.toLocaleString()} in settle`);
  }
  if (metrics.frame_count_error > 0) {
    parts.push(`${metrics.frame_count_error.toLocaleString()} error`);
  }
  // When nothing special happened — no settle, no errors — fall back
  // to the tidy single-number form.
  if (parts.length === 1) return metrics.frame_count_total.toLocaleString();
  return parts.join(" · ");
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
