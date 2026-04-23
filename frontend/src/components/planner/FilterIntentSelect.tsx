/**
 * Filter-intent multi-select (v0.21.0). One toggle per line; multi-band
 * filters are multiple selections. Drives the scoring moon dimension.
 * Tonight mode only.
 */
import FormHelperText from "@mui/material/FormHelperText";
import Stack from "@mui/material/Stack";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";

import { FILTER_LINES, type FilterLine } from "@/api/planner";

interface Props {
  value: FilterLine[];
  onChange: (next: FilterLine[]) => void;
  /** When true, render the label + helper text inline. Callers inside
   *  a cramped filter row can set ``false`` to omit both. */
  showLabel?: boolean;
}

const LINE_HINT: Record<FilterLine, string> = {
  Ha: "H-alpha — deep red narrowband (656 nm)",
  SII: "Sulphur II — deep red narrowband (672 nm)",
  OIII: "Oxygen III — blue-green narrowband (501 nm)",
  L: "Luminance — full visible broadband",
  R: "Red broadband (~620 nm)",
  G: "Green broadband (~530 nm)",
  B: "Blue broadband (~430 nm)",
};

export function FilterIntentSelect({ value, onChange, showLabel = true }: Props) {
  const helper =
    value.length === 0
      ? "No filters selected — scoring treats the moon as neutral."
      : `Session: ${value.join(" + ")} — the most-sensitive filter limits scoring.`;

  return (
    <Stack spacing={0.5}>
      {showLabel && (
        <Tooltip
          title={
            <>
              Select every filter you plan to capture tonight. Drives the
              moon dimension of the target score: the most light-sensitive
              filter in your selection bounds the whole session (a single
              OIII frame ruins LRGB+OIII scoring even if Ha/SII are fine).
              Multi-band filters like L-eXtreme → select Ha + OIII.
              Empty → moon is neutral for every target.
            </>
          }
          placement="top"
          arrow
        >
          <Typography variant="caption" sx={{ cursor: "help" }}>
            Filter intent
          </Typography>
        </Tooltip>
      )}
      <ToggleButtonGroup
        value={value}
        onChange={(_e, next: FilterLine[]) => onChange(next)}
        size="small"
        aria-label="Filter intent"
        sx={{ flexWrap: "wrap" }}
      >
        {FILTER_LINES.map((line) => (
          <Tooltip key={line} title={LINE_HINT[line]} placement="top" arrow>
            <ToggleButton
              value={line}
              aria-label={line}
              sx={{ px: 1.25, py: 0.25, fontSize: "0.75rem" }}
            >
              {line}
            </ToggleButton>
          </Tooltip>
        ))}
      </ToggleButtonGroup>
      {showLabel && (
        <FormHelperText sx={{ mt: 0, ml: 0 }}>{helper}</FormHelperText>
      )}
    </Stack>
  );
}
