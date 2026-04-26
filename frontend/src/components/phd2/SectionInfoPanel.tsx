/**
 * Per-section header info panel — surfaces parsed equipment / sky /
 * algorithm settings beneath the Section list in the left nav.
 *
 * Each section in a PHD2 log carries its own header (the user can
 * change equipment mid-session), so the panel is selection-aware:
 * switching sections in the navigator re-renders this panel for
 * the newly-selected section.
 *
 * Groups with no populated fields drop out entirely — a calibration-
 * only section that omits guide algorithms simply doesn't render
 * the Algorithms group.
 *
 * The freeform-keys dict from the parser (everything PHD2 wrote
 * that NightCrate didn't pre-recognize) is rendered as a final
 * "Other" group so future PHD2 versions don't lose information
 * silently — same data-preservation principle as the parser itself.
 */
import { useState } from "react";
import Box from "@mui/material/Box";
import Collapse from "@mui/material/Collapse";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import type { SectionHeader } from "@/api/phd2";

interface Props {
  header: SectionHeader;
  /** When false, the panel renders without a collapse toggle — all
   *  groups are visible immediately. Default: true (collapsible). */
  collapsible?: boolean;
  /** Initial expanded state. Default: collapsed (the chart + summary
   *  panels are the primary focus; header is reference data the user
   *  pulls up when troubleshooting). */
  defaultExpanded?: boolean;
}

interface InfoRow {
  label: string;
  value: string;
}

interface InfoGroup {
  title: string;
  rows: InfoRow[];
}

export default function SectionInfoPanel({
  header,
  collapsible = true,
  defaultExpanded = false,
}: Props) {
  const [expanded, setExpanded] = useState(defaultExpanded);

  const groups = buildGroups(header);
  if (groups.length === 0) return null;

  const isOpen = collapsible ? expanded : true;

  const groupNode = (g: InfoGroup, fontSize: number) => (
    <Box key={g.title}>
      <Typography
        variant="caption"
        sx={{
          display: "block",
          fontWeight: 700,
          letterSpacing: 0.6,
          color: "primary.main",
          mb: 0.25,
          textTransform: "uppercase",
          fontSize: fontSize - 1,
        }}
      >
        {g.title}
      </Typography>
      <Stack spacing={0.25}>
        {g.rows.map((r) => (
          <Stack
            key={r.label}
            direction="row"
            spacing={1}
            alignItems="baseline"
            sx={{ minWidth: 0 }}
          >
            <Typography
              variant="caption"
              sx={{
                color: "text.secondary",
                flexShrink: 0,
                minWidth: 92,
                fontSize,
              }}
            >
              {r.label}
            </Typography>
            <Typography
              variant="caption"
              sx={{
                fontFamily: "monospace",
                fontSize,
                wordBreak: "break-word",
                flex: 1,
              }}
            >
              {r.value}
            </Typography>
          </Stack>
        ))}
      </Stack>
    </Box>
  );

  if (!collapsible) {
    return (
      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: "max-content max-content max-content",
          columnGap: 4,
          rowGap: 2,
        }}
      >
        {groups.map((g) => (
          <Box key={g.title}>
            {groupNode(g, 12)}
          </Box>
        ))}
      </Box>
    );
  }

  return (
    <Box sx={{ mt: 1 }}>
      <Stack
        direction="row"
        alignItems="center"
        spacing={0.5}
        onClick={() => setExpanded((v) => !v)}
        sx={{ cursor: "pointer", userSelect: "none", pl: 0.5 }}
      >
        <ExpandMoreIcon
          fontSize="small"
          sx={{
            transition: "transform 120ms ease",
            transform: isOpen ? "rotate(0deg)" : "rotate(-90deg)",
            color: "text.secondary",
          }}
        />
        <Typography variant="overline" sx={{ color: "text.secondary" }}>
          Section info
        </Typography>
      </Stack>
      <Collapse in={isOpen} unmountOnExit>
        <Stack spacing={1.25} sx={{ pl: 1, pr: 0.5, pt: 0.5 }}>
          {groups.map((g) => groupNode(g, 11))}
        </Stack>
      </Collapse>
    </Box>
  );
}

/** Build the grouped key-value layout from the section header.
 *  Skips any field whose parsed value is null/undefined — only
 *  rows with actual content surface. Empty groups drop out
 *  entirely.
 */
function buildGroups(h: SectionHeader): InfoGroup[] {
  const groups: InfoGroup[] = [];

  push(groups, "Optics", [
    row("Focal length", h.focal_length_mm, (v) => `${v} mm`),
    row("Pixel scale", h.pixel_scale_arcsec_per_px, (v) => `${v} ″/px`),
    row("Binning", h.binning, (v) => `${v}×${v}`),
    row("Exposure", h.exposure_ms, (v) => `${v} ms`),
  ]);

  push(groups, "Camera", [row("Camera", h.camera)]);

  push(groups, "Mount", [
    row("Mount", h.mount),
    row("AO", h.ao),
    row("X angle", h.x_angle_deg, (v) => `${v.toFixed(1)}°`),
    row("X rate", h.x_rate_px_per_sec, (v) => `${v.toFixed(3)} px/s`),
    row("Y angle", h.y_angle_deg, (v) => `${v.toFixed(1)}°`),
    row("Y rate", h.y_rate_px_per_sec, (v) => `${v.toFixed(3)} px/s`),
    row("Parity", h.parity),
    row("Cal step", h.calibration_step_ms, (v) => `${v} ms`),
    row("Cal Dec", h.cal_declination_deg, (v) => `${v.toFixed(1)}°`),
    row("Last cal issue", h.last_cal_issue),
  ]);

  push(groups, "Sky position", [
    row("Declination", h.declination_deg, (v) => `${v.toFixed(2)}°`),
    row("Hour angle", h.hour_angle_hr, (v) => `${v.toFixed(2)} hr`),
    row("Pier side", h.pier_side),
    row("Rotator", h.rotator_position),
  ]);

  push(groups, "Star + lock", [
    row(
      "Lock pos",
      formatXY(h.lock_position_x_px, h.lock_position_y_px, 3),
    ),
    row(
      "Star pos",
      formatXY(h.star_position_x_px, h.star_position_y_px, 3),
    ),
    row("HFD", h.hfd_px, (v) => `${v.toFixed(2)} px`),
    row("Search region", h.search_region_px, (v) => `${v} px`),
    row(
      "Mass tolerance",
      h.star_mass_tolerance_pct,
      (v) => `${v.toFixed(1)}%`,
    ),
  ]);

  push(groups, "Algorithms", [
    row("X guide algo", h.x_guide_algorithm),
    row("Y guide algo", h.y_guide_algorithm),
    row("Dec guide mode", h.dec_guide_mode),
    row("Backlash comp", formatBool(h.backlash_comp_enabled)),
    row("Backlash pulse", h.backlash_pulse_ms, (v) => `${v} ms`),
    row("Max RA dur", h.max_ra_duration_ms, (v) => `${v} ms`),
    row("Max Dec dur", h.max_dec_duration_ms, (v) => `${v} ms`),
    row("RA speed", h.ra_guide_speed),
    row("Dec speed", h.dec_guide_speed),
  ]);

  push(groups, "Dither", [
    row("Dither", h.dither_description),
    row("Dither scale", h.dither_scale, (v) => v.toFixed(3)),
    row("Image NR", h.image_noise_reduction),
  ]);

  push(groups, "Profile", [row("Equipment profile", h.equipment_profile)]);

  // Surface unrecognized keys verbatim so the user sees everything
  // PHD2 wrote, even if NightCrate's parser didn't pre-categorize it.
  // Sorted by key so the layout is stable across renders.
  const otherKeys = Object.keys(h.freeform_keys ?? {}).sort();
  if (otherKeys.length > 0) {
    push(
      groups,
      "Other",
      otherKeys.map((k) => ({ label: k, value: h.freeform_keys[k] })),
    );
  }

  return groups;
}

function push(groups: InfoGroup[], title: string, rows: (InfoRow | null)[]) {
  const filtered = rows.filter((r): r is InfoRow => r !== null);
  if (filtered.length > 0) groups.push({ title, rows: filtered });
}

/** Build an InfoRow from a possibly-null source value. The optional
 *  ``format`` lambda handles non-string types; defaults to ``String(v)``
 *  for primitive values that already format cleanly. */
function row<T>(
  label: string,
  value: T | null | undefined,
  format?: (v: T) => string,
): InfoRow | null {
  if (value === null || value === undefined) return null;
  if (typeof value === "string" && value.trim() === "") return null;
  const text = format ? format(value) : String(value);
  return { label, value: text };
}

function formatXY(
  x: number | null,
  y: number | null,
  digits: number,
): string | null {
  if (x === null || y === null) return null;
  return `${x.toFixed(digits)}, ${y.toFixed(digits)}`;
}

function formatBool(v: boolean | null | undefined): string | null {
  if (v === null || v === undefined) return null;
  return v ? "enabled" : "disabled";
}
