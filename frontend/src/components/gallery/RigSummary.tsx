import Box from "@mui/material/Box";
import Tooltip from "@mui/material/Tooltip";
import type { GalleryRig } from "@/api/gallery";

export default function RigSummary({ rigs }: { rigs: GalleryRig[] }) {
  if (!rigs.length) {
    return (
      <Box component="span" sx={{ color: "text.secondary" }}>
        No rigs
      </Box>
    );
  }

  const others = rigs.slice(1).map((rig) => rig.name);
  return (
    <>
      {rigs[0].name}
      {others.length > 0 && (
        <Tooltip title={others.join(", ")}>
          <Box
            component="span"
            aria-label={`and ${others.join(", ")}`}
            sx={{
              ml: "6px",
              display: "inline-block",
              height: 18,
              lineHeight: "18px",
              px: "6px",
              borderRadius: "9px",
              bgcolor: (theme) =>
                theme.palette.mode === "dark" ? "#31343a" : "#ebe8e3",
              fontSize: 11,
              fontWeight: 600,
            }}
          >
            +{others.length}
          </Box>
        </Tooltip>
      )}
    </>
  );
}
