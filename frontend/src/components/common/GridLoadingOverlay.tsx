/**
 * Visible loading overlay for MUI X DataGrid.
 *
 * Wire via ``slots.loadingOverlay``:
 *
 *     slots={{ loadingOverlay: GridLoadingOverlay }}
 *
 * Default MUI X loading UI is a single thin line at the top of the
 * grid which is easy to miss on first render — especially with
 * server-side pagination where the grid starts empty while the
 * initial fetch is in flight. This overlay centres a spinner + a
 * short caption on the grid body so users never stare at a blank
 * table wondering if the page is broken.
 */
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import Typography from "@mui/material/Typography";

export default function GridLoadingOverlay() {
  return (
    <Box
      sx={{
        position: "absolute",
        inset: 0,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 1.5,
        // Opaque backdrop — on a filter / sort change the old rows
        // underneath would read as ghost artifacts if they showed
        // through. ``background.paper`` keeps theme consistency
        // across light / dark modes without a separate selector.
        bgcolor: "background.paper",
        pointerEvents: "none",
        zIndex: 3,
      }}
    >
      <CircularProgress size={32} thickness={4} />
      <Typography variant="body2" color="text.secondary">
        Loading…
      </Typography>
    </Box>
  );
}
