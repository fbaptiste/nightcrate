import Box from "@mui/material/Box";
import { fitsImageUrl } from "@/api/fits";

interface Props {
  path: string;
  hdu: number;
  fit: boolean;
}

export function FitsImage({ path, hdu, fit }: Props) {
  const src = fitsImageUrl(path, hdu);

  return (
    <Box
      sx={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        height: "100%",
        overflow: "auto",
        bgcolor: "#000",
      }}
    >
      <Box
        component="img"
        src={src}
        alt="FITS image"
        sx={
          fit
            ? { maxWidth: "100%", maxHeight: "100%", objectFit: "contain" }
            : { imageRendering: "pixelated" }
        }
      />
    </Box>
  );
}
