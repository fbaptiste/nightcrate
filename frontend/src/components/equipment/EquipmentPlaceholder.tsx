import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";

function formatCategory(slug: string): string {
  return slug
    .split("-")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

export function EquipmentPlaceholder({ category }: { category: string }) {
  return (
    <Box
      sx={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        height: "100%",
        gap: 1,
        color: "text.secondary",
      }}
    >
      <Typography variant="h6">{formatCategory(category)}</Typography>
      <Typography variant="body2">Coming soon</Typography>
    </Box>
  );
}
