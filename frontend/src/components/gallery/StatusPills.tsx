import Box from "@mui/material/Box";

const labels: Record<string, string> = {
  active: "Active",
  paused: "Paused",
  complete: "Complete",
  abandoned: "Abandoned",
};

const pillSx = {
  height: 18,
  lineHeight: "16px",
  px: 1,
  borderRadius: "9px",
  border: "1px solid currentColor",
  fontSize: 11,
  fontWeight: 600,
  whiteSpace: "nowrap",
} as const;

interface Props {
  status: string;
  retired: boolean;
}

export default function StatusPills({ status, retired }: Props) {
  let color: string | ((theme: { palette: { mode: string } }) => string) =
    "text.secondary";
  if (status === "paused") {
    color = (theme) => (theme.palette.mode === "dark" ? "#f0a35e" : "#b85500");
  } else if (status === "complete") {
    color = (theme) => (theme.palette.mode === "dark" ? "#7fb2ea" : "#1f63b0");
  }

  return (
    <Box sx={{ display: "flex", gap: "6px", alignItems: "center" }}>
      <Box component="span" sx={{ ...pillSx, color }}>
        {labels[status] ?? status}
      </Box>
      {retired && (
        <Box component="span" sx={{ ...pillSx, color: "text.secondary" }}>
          Retired
        </Box>
      )}
    </Box>
  );
}
