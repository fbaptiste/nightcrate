import type { ReactNode } from "react";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Tooltip from "@mui/material/Tooltip";

export interface ViewToggleOption<T extends string> {
  value: T;
  label: string;
  icon: ReactNode;
}

interface Props<T extends string> {
  options: ViewToggleOption<T>[];
  value: T;
  onChange: (value: T) => void;
  ariaLabel: string;
}

export default function ViewToggle<T extends string>({
  options,
  value,
  onChange,
  ariaLabel,
}: Props<T>) {
  return (
    <ToggleButtonGroup
      exclusive
      size="small"
      value={value}
      onChange={(_, next: T | null) => {
        if (next != null) onChange(next);
      }}
      aria-label={ariaLabel}
      sx={{
        border: 1,
        borderColor: "divider",
        borderRadius: "6px",
        "& .MuiToggleButtonGroup-grouped": {
          width: 36,
          height: 32,
          p: 0,
          border: 0,
          borderRadius: 0,
          color: "text.secondary",
          "&:not(:first-of-type)": {
            borderLeft: 1,
            borderLeftColor: "divider",
            ml: 0,
          },
          "&:first-of-type": { borderRadius: "5px 0 0 5px" },
          "&:last-of-type": { borderRadius: "0 5px 5px 0" },
          "& svg": { fontSize: 20 },
          "&.Mui-selected, &.Mui-selected:hover": {
            bgcolor: "primary.main",
            color: "primary.contrastText",
          },
          "&:focus-visible": {
            outline: "2px solid",
            outlineColor: "primary.main",
            outlineOffset: 2,
            zIndex: 1,
          },
        },
      }}
    >
      {options.map((option) => (
        <Tooltip
          key={option.value}
          title={option.label}
          placement="bottom"
          slotProps={{
            tooltip: {
              sx: { bgcolor: "grey.800", color: "common.white" },
            },
          }}
        >
          <ToggleButton value={option.value} aria-label={option.label}>
            {option.icon}
          </ToggleButton>
        </Tooltip>
      ))}
    </ToggleButtonGroup>
  );
}
