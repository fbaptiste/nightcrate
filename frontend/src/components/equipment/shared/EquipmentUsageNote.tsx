import { useQuery } from "@tanstack/react-query";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { fetchEquipmentUsage } from "@/api/equipment";

interface EquipmentUsageNoteProps {
  kind: string;
  itemId: number | null | undefined;
}

function countLabel(count: number, singular: string, plural: string): string {
  return `${count} ${count === 1 ? singular : plural}`;
}

export default function EquipmentUsageNote({ kind, itemId }: EquipmentUsageNoteProps) {
  const { data } = useQuery({
    queryKey: ["equipment-usage", kind, itemId],
    queryFn: () => fetchEquipmentUsage(kind, itemId!),
    enabled: itemId != null,
  });

  if (!data || (data.rig_count === 0 && data.project_count === 0)) return null;

  return (
    <Box
      role="note"
      sx={(theme) => ({
        display: "flex",
        alignItems: "flex-start",
        gap: "10px",
        px: "12px",
        py: "10px",
        borderRadius: "6px",
        bgcolor: theme.palette.mode === "dark" ? "#7d9ab824" : "#5b7a9e24",
        mb: 2,
      })}
    >
      <InfoOutlinedIcon
        aria-hidden="true"
        sx={(theme) => ({
          flex: "none",
          mt: "1px",
          fontSize: 20,
          color: theme.palette.mode === "dark" ? "#7d9ab8" : "#5b7a9e",
        })}
      />
      <Typography sx={{ fontSize: "13.5px", lineHeight: "20px" }}>
        Used by {countLabel(data.rig_count, "rig", "rigs")} and{" "}
        {countLabel(data.project_count, "project", "projects")}. The change applies to all
        of them.
      </Typography>
    </Box>
  );
}
