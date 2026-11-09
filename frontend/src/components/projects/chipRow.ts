/** Chips in a multi-select field: a 6 px gap between chips and rows, so
 *  neighbouring chips (and the open chip's outline) never touch. */
export const CHIP_ROW_GAP = "6px";

export const CHIP_ROW_SX = {
  "& .MuiAutocomplete-inputRoot": { gap: CHIP_ROW_GAP, py: "7px" },
  "& .MuiAutocomplete-inputRoot .MuiAutocomplete-tag": { m: 0 },
  "& .MuiAutocomplete-inputRoot .MuiChip-root": { m: 0 },
} as const;
