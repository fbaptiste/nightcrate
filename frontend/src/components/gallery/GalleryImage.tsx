import Box from "@mui/material/Box";
import NearViewportImage from "@/components/common/NearViewportImage";

export default function GalleryImage({ src, alt }: { src: string; alt: string }) {
  const fallback = (
    <Box
      sx={{
        display: "grid",
        placeItems: "center",
        width: "100%",
        height: "100%",
        color: "#8e8c88",
        fontSize: 13,
      }}
    >
      No preview
    </Box>
  );

  return (
    <NearViewportImage
      src={src}
      alt={alt}
      fallback={fallback}
      sx={{
        display: "block",
        width: "100%",
        height: "100%",
        objectFit: "contain",
      }}
    />
  );
}
