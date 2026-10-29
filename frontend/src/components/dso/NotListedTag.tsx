import Typography from "@mui/material/Typography";

// This named helper is part of the component's public contract.
// eslint-disable-next-line react-refresh/only-export-components
export function catalogShortName(displayName: string): string {
  return displayName.replace(/\s*\([^()]*\)\s*$/, "");
}

export default function NotListedTag() {
  return (
    <Typography
      component="span"
      variant="caption"
      color="text.secondary"
      sx={{
        display: "inline-flex",
        alignItems: "center",
        border: 1,
        borderColor: "text.secondary",
        borderRadius: 0.5,
        px: 0.35,
        ml: 0.75,
        fontSize: "0.7rem",
        lineHeight: 1.15,
      }}
    >
      Not listed
    </Typography>
  );
}
