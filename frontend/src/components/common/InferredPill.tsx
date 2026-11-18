import Box from "@mui/material/Box";
import Tooltip from "@mui/material/Tooltip";

interface Props {
  label: string;
  title: string;
}

/** Shared marker for a value NightCrate inferred instead of reading directly. */
export default function InferredPill({ label, title }: Props) {
  return (
    <Tooltip title={title} placement="top">
      <Box
        component="span"
        sx={(theme) => ({
          display: "inline-flex",
          alignItems: "center",
          height: "18px",
          ml: "6px",
          px: "7px",
          border: `1px solid ${theme.palette.mode === "dark" ? "rgba(255,255,255,0.23)" : "#c4c1bb"}`,
          borderRadius: "9px",
          color: "text.secondary",
          fontFamily: theme.typography.body1.fontFamily,
          fontSize: "11px",
          letterSpacing: "normal",
          lineHeight: "18px",
          whiteSpace: "nowrap",
        })}
      >
        {label}
      </Box>
    </Tooltip>
  );
}
