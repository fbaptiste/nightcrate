import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";

export function HomePage() {
  return (
    <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%", gap: 2, p: 4 }}>
      <Typography variant="h4" fontWeight={600}>Welcome to NightCrate</Typography>
      <Typography variant="body1" color="text.secondary" sx={{ maxWidth: 420, textAlign: "center" }}>
        Astrophotography session cataloging and analysis. Use the sidebar to navigate.
      </Typography>
    </Box>
  );
}
