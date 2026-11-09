import type { CSSProperties } from "react";
import Box from "@mui/material/Box";
import { useTheme } from "@mui/material/styles";
import { filterSwatchStyle, type ResolvedFilter } from "./filterColors";

interface Props {
  filter: ResolvedFilter;
  width?: number | string;
  height?: number | string;
  borderRadius?: number | string;
  outlineWidth?: number;
  display?: CSSProperties["display"];
}

export default function FilterSwatch({
  filter,
  width = 10,
  height = 10,
  borderRadius = "2px",
  outlineWidth = 2,
  display = "inline-block",
}: Props) {
  const theme = useTheme();
  return (
    <Box
      component="span"
      aria-hidden="true"
      sx={{
        display,
        width,
        height,
        flex: "0 0 auto",
        borderRadius,
      }}
      style={filterSwatchStyle(filter, theme.palette.mode, outlineWidth)}
    />
  );
}
