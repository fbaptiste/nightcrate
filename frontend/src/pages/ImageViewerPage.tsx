import { useEffect } from "react";
import Box from "@mui/material/Box";

export function ImageViewerPage() {
  const params = new URLSearchParams(window.location.search);
  const requestedSrc = params.get("src") ?? "";
  const src = requestedSrc.startsWith("/api/") ? requestedSrc : null;
  const title = params.get("title") || "NightCrate image";

  useEffect(() => {
    document.title = title;
  }, [title]);

  return (
    <Box
      sx={{
        width: "100vw",
        height: "100vh",
        bgcolor: "common.black",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        overflow: "hidden",
      }}
    >
      {src && (
        <Box
          component="img"
          src={src}
          alt={title}
          sx={{ width: "100%", height: "100%", objectFit: "contain" }}
        />
      )}
    </Box>
  );
}
