import Box from "@mui/material/Box";
import { projectStatusLabel, projectStatusPillColor } from "@/lib/projectStatus";

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
  return (
    <Box sx={{ display: "flex", gap: "6px", alignItems: "center" }}>
      <Box
        component="span"
        sx={(theme) => ({
          ...pillSx,
          color: projectStatusPillColor(status, theme.palette.mode),
        })}
      >
        {projectStatusLabel(status)}
      </Box>
      {retired && (
        <Box component="span" sx={{ ...pillSx, color: "text.secondary" }}>
          Retired
        </Box>
      )}
    </Box>
  );
}
