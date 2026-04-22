import { useMemo } from "react";
import Autocomplete from "@mui/material/Autocomplete";
import Chip from "@mui/material/Chip";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

export interface PillOption {
  code: string;
  displayName: string;
  count?: number;
}

export interface PillFilterProps {
  value: string[];
  onChange: (codes: string[]) => void;
  options: PillOption[];
  label: string;
  placeholder?: string;
}

/**
 * Generic multi-select pill filter. Shared shape for every
 * multi-select filter on the page (catalog, object type, constellation
 * once it grows beyond single-select, etc.). Parent is expected to
 * constrain the width (typical target: ~320px so two medium chips sit
 * side-by-side before wrapping).
 */
export default function PillFilter({
  value,
  onChange,
  options,
  label,
  placeholder = "Click to add…",
}: PillFilterProps) {
  const sortedOptions = useMemo(() => {
    return [...options]
      .filter((o) => (o.count ?? 1) > 0)
      .sort((a, b) => a.displayName.localeCompare(b.displayName));
  }, [options]);

  const optionByCode = useMemo(() => {
    const map: Record<string, PillOption> = {};
    for (const o of options) map[o.code] = o;
    return map;
  }, [options]);

  return (
    <Autocomplete
      multiple
      size="small"
      disableCloseOnSelect
      // Reopen the popper on click-to-focus. Without this, a post-close
      // click on the input generates a focus event + a click event that
      // race with MUI's internal open flag, leaving the popper closed
      // until the *second* click — classic "needs two clicks" bug.
      openOnFocus
      options={sortedOptions.map((o) => o.code)}
      value={value}
      onChange={(_, next) => onChange(next)}
      getOptionLabel={(code) => optionByCode[code]?.displayName ?? code}
      isOptionEqualToValue={(option, selected) => option === selected}
      renderOption={(props, code) => {
        const opt = optionByCode[code];
        const count = opt?.count;
        const { key, ...liProps } = props as typeof props & { key: string };
        return (
          <li
            key={key}
            {...liProps}
            style={{ display: "flex", alignItems: "baseline" }}
          >
            <span>{opt?.displayName ?? code}</span>
            {count != null && (
              <Typography
                component="span"
                variant="caption"
                color="text.secondary"
                sx={{ ml: 1.25 }}
              >
                ({count.toLocaleString()})
              </Typography>
            )}
          </li>
        );
      }}
      renderTags={(selected, getTagProps) =>
        selected.map((code, index) => {
          const { key, ...tagProps } = getTagProps({ index });
          return (
            <Chip
              key={key}
              size="small"
              label={optionByCode[code]?.displayName ?? code}
              {...tagProps}
            />
          );
        })
      }
      renderInput={(params) => (
        <TextField
          {...params}
          label={label}
          placeholder={value.length === 0 ? placeholder : ""}
        />
      )}
      fullWidth
    />
  );
}
