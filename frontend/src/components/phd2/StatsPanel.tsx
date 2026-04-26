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
  /** Heading above the metrics grid. Defaults to "Section stats"
   *  for the section-wide panel; the Viewport stats panel overrides
   *  with its own label. */
  title?: string;
  /** Optional second-line caption under the title — used by the
   *  Viewport stats panel to show "N / M frames visible". */
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
  title = "Section stats",
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
      sx={{ display: "block", mb: isOpen ? 1 : 0, pl: collapsible ? 3 : 0, whiteSpace: "pre-line" }}
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
    // Well-guided sessions drift at 10⁻³–10⁻² px/min (= 10⁻²–10⁻¹ ″/min
    // at a typical scale) — four decimals on px and three on arcsec
    // let small-but-real drift show instead of rounding to zero. Sign
    // preserved; no absolute value.
    const pxStr = pxPerMin.toFixed(4);
    if (scale === null) return `${pxStr} px/min`;
    const arcsecStr = (pxPerMin * scale).toFixed(3);
    return `${pxStr} px/min / ${arcsecStr}″/min`;
  };
  const renderOscillation = (frac: number | null): string => {
    if (frac === null) return "—";
    return `${(frac * 100).toFixed(1)}%`;
  };
  const renderPaError = (arcmin: number | null): string => {
    if (arcmin === null) return "—";
    return `${arcmin.toFixed(2)}′`;
  };

  const items: Array<{ label: string; value: string; tooltip?: string; cols: number }> = [
    // Row 1: overview
    {
      label: "Duration",
      value: formatDuration(metrics.duration_total_seconds),
      tooltip: "Wall-clock duration from first to last guiding frame.",
      cols: 6,
    },
    {
      label: "Frames",
      value: formatFrameCount(metrics),
      tooltip: "Total frames, included in stats, settle frames, and error frames.",
      cols: 6,
    },
    // Row 2: alignment quality
    {
      label: "PA error",
      value: renderPaError(metrics.polar_alignment_error_arcmin),
      tooltip: "Estimated polar alignment error in arcminutes, derived from Dec drift and declination.",
      cols: 6,
    },
    {
      label: "Elongation",
      value: renderOscillation(metrics.elongation),
      tooltip: "How elongated the scatter cloud is — 0 is round, nearer 1 means one axis dominates.",
      cols: 6,
    },
    // Row 3: RMS
    {
      label: "RMS Total",
      value: renderDist(metrics.rms_total_px),
      tooltip: "Quadrature sum of RMS RA and RMS Dec.",
      cols: 4,
    },
    {
      label: "RMS RA",
      value: renderDist(metrics.rms_ra_px),
      tooltip: "Standard deviation of RA error across included frames.",
      cols: 4,
    },
    {
      label: "RMS Dec",
      value: renderDist(metrics.rms_dec_px),
      tooltip: "Standard deviation of Dec error across included frames.",
      cols: 4,
    },
    // Row 4: peaks
    {
      label: "Peak RA",
      value: renderDist(metrics.peak_ra_px),
      tooltip: "Worst-case single-frame RA offset, sign preserved.",
      cols: 6,
    },
    {
      label: "Peak Dec",
      value: renderDist(metrics.peak_dec_px),
      tooltip: "Worst-case single-frame Dec offset, sign preserved.",
      cols: 6,
    },
    // Row 5: drift
    {
      label: "Drift RA",
      value: renderDrift(metrics.drift_ra_px_per_min),
      tooltip: "Long-term linear RA drift the algorithm did not fully cancel.",
      cols: 6,
    },
    {
      label: "Drift Dec",
      value: renderDrift(metrics.drift_dec_px_per_min),
      tooltip: "Long-term linear Dec drift, computed across unguided frames only.",
      cols: 6,
    },
    // Row 6: oscillation
    {
      label: "Osc RA",
      value: renderOscillation(metrics.oscillation_ra),
      tooltip: "Fraction of frames where RA error flipped sign. High values (>40%) suggest overcorrection.",
      cols: 6,
    },
    {
      label: "Osc Dec",
      value: renderOscillation(metrics.oscillation_dec),
      tooltip: "Fraction of frames where Dec error flipped sign.",
      cols: 6,
    },
    // Row 7: star health
    {
      label: "Mean SNR",
      value: metrics.mean_snr !== null ? metrics.mean_snr.toFixed(2) : "—",
      tooltip: "Average guide-star signal-to-noise ratio. Below ~5 the centroid gets noisy.",
      cols: 6,
    },
    {
      label: "Star mass",
      value:
        metrics.mean_star_mass !== null
          ? `${Math.round(metrics.mean_star_mass).toLocaleString()} (mean)`
          : "—",
      tooltip: "Average integrated brightness of the guide star (ADU).",
      cols: 6,
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
        <Grid container spacing={1} columns={12}>
        {items.map((item) => (
          <Grid key={item.label} size={item.cols}>
            {item.tooltip ? (
              <Tooltip title={item.tooltip} arrow placement="top">
                <Typography
                  variant="caption"
                  color="text.secondary"
                  sx={{ display: "block", cursor: "help" }}
                >
                  {item.label}
                </Typography>
              </Tooltip>
            ) : (
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ display: "block" }}
              >
                {item.label}
              </Typography>
            )}
            <Typography
              variant="body2"
              sx={{
                fontVariantNumeric: "tabular-nums",
                whiteSpace: "pre-line",
              }}
            >
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

/** Render the frames-row value as a multi-line breakdown when settle
 *  exclusion or errors removed frames; falls back to the tidy
 *  single-number form when nothing special happened.
 *
 *  Newline-separated rather than ``·``-separated so the narrow
 *  left-nav column can render each part on its own line via
 *  ``whiteSpace: pre-line``. */
function formatFrameCount(metrics: SectionMetrics): string {
  const total = metrics.frame_count_total.toLocaleString();
  const lines: string[] = [`${total} total`];
  if (metrics.frame_count_in_settle > 0) {
    lines.push(`${metrics.frame_count_in_stats.toLocaleString()} in stats`);
    lines.push(`${metrics.frame_count_in_settle.toLocaleString()} in settle`);
  }
  if (metrics.frame_count_error > 0) {
    lines.push(`${metrics.frame_count_error.toLocaleString()} error`);
  }
  if (lines.length === 1) return total;
  return lines.join("\n");
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
