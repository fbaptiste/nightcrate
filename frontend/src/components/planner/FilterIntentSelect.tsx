/**
 * Filter-intent multi-select (v0.21.0). MUI Autocomplete with chip
 * pills for each selected filter line. Drives the scoring moon
 * dimension. Tonight mode only.
 */
import Autocomplete from "@mui/material/Autocomplete";
import FormControl from "@mui/material/FormControl";
import FormHelperText from "@mui/material/FormHelperText";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";

import { FILTER_LINES, type FilterLine } from "@/api/planner";

interface Props {
  value: FilterLine[];
  onChange: (next: FilterLine[]) => void;
  showLabel?: boolean;
}

const LINE_HINT: Record<FilterLine, string> = {
  Ha: "H-alpha (656 nm)",
  SII: "Sulphur II (672 nm)",
  OIII: "Oxygen III (501 nm)",
  L: "Luminance — broadband",
  R: "Red (~620 nm)",
  G: "Green (~530 nm)",
  B: "Blue (~430 nm)",
};

export function FilterIntentSelect({ value, onChange, showLabel = true }: Props) {
  const helper =
    value.length === 0
      ? "Moon is neutral for scoring."
      : `${value.join(" + ")} — most-sensitive limits scoring.`;

  return (
    <Tooltip
      title={
        "Select every filter you plan to capture tonight. The most " +
        "light-sensitive filter bounds the moon scoring dimension."
      }
      placement="top"
      arrow
    >
      <FormControl size="small" sx={{ minWidth: 220 }}>
        <Autocomplete
          multiple
          size="small"
          options={FILTER_LINES as unknown as FilterLine[]}
          value={value}
          onChange={(_e, next) => onChange(next)}
          disableCloseOnSelect
          getOptionLabel={(opt) => opt}
          renderOption={(props, option) => (
            <li {...props} key={option} style={{ ...props.style, padding: "8px 16px" }}>
              <strong>{option}</strong>
              <span style={{ marginLeft: 10, fontSize: "0.8rem", opacity: 0.7 }}>
                {LINE_HINT[option]}
              </span>
            </li>
          )}
          renderInput={(params) => (
            <TextField
              {...params}
              label={showLabel ? "Filter intent" : undefined}
              placeholder={value.length === 0 ? "Add filters..." : undefined}
            />
          )}
          ChipProps={{
            size: "small",
            color: "warning",
            sx: { height: 20, "& .MuiChip-label": { px: 0.75, fontSize: "0.7rem" } },
          }}
        />
        {showLabel && (
          <FormHelperText sx={{ mt: 0.25, ml: 0 }}>{helper}</FormHelperText>
        )}
      </FormControl>
    </Tooltip>
  );
}
