/**
 * Parse-time warnings hover card.
 *
 * Header-row chip shows the count; hovering reveals the full list in a
 * tooltip. Warning codes from the parser (``frames_with_errors``, etc.)
 * are translated to friendly titles — the raw code is an internal
 * identifier, not something the user should see verbatim.
 */
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import type { ParseWarning } from "@/api/phd2";

interface Props {
  warnings: ParseWarning[];
}

/** Friendly titles for parser warning codes. Keep in lockstep with
 *  the codes emitted by ``services/phd2_parser.py``. Falls back to
 *  a Start-Case rendering of the raw code if one isn't mapped. */
const WARNING_TITLES: Record<string, string> = {
  backward_timestamp_jump: "Clock jumped backward",
  no_csv_header: "Missing CSV header",
  missing_pixel_scale: "Missing pixel scale",
  frames_with_errors: "Frames with errors",
  header_validation_error: "Header validation error",
  locale_recovery_applied: "Locale-decimal recovery",
  short_row: "Short row",
  bad_calibration_row: "Bad calibration row",
};

function friendlyTitle(code: string): string {
  return (
    WARNING_TITLES[code] ??
    code
      .split("_")
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join(" ")
  );
}

export default function WarningsDrawer({ warnings }: Props) {
  if (warnings.length === 0) return null;

  const tooltipBody = (
    <Stack spacing={1} sx={{ p: 0.5, maxWidth: 360 }}>
      {warnings.map((w, i) => (
        <Box key={i}>
          <Typography variant="caption" sx={{ fontWeight: 700, display: "block" }}>
            {friendlyTitle(w.code)}
            {w.section_index !== null ? ` · Section ${w.section_index}` : ""}
          </Typography>
          <Typography variant="caption" sx={{ display: "block", opacity: 0.85 }}>
            {w.message}
          </Typography>
        </Box>
      ))}
    </Stack>
  );

  return (
    <Tooltip title={tooltipBody} arrow placement="bottom-end">
      <Chip
        icon={<WarningAmberIcon />}
        label={`${warnings.length} warning${warnings.length === 1 ? "" : "s"}`}
        color="warning"
        variant="outlined"
        size="small"
      />
    </Tooltip>
  );
}
