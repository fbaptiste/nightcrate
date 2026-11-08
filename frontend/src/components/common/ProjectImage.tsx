import { useState, type ReactNode } from "react";
import Box from "@mui/material/Box";
import type { SxProps, Theme } from "@mui/material/styles";

interface Props {
  src: string;
  alt: string;
  sx?: SxProps<Theme>;
  fallback?: ReactNode;
}

export default function ProjectImage({ src, alt, sx, fallback }: Props) {
  const [failed, setFailed] = useState(false);

  if (failed) return fallback ?? null;

  return <Box component="img" src={src} alt={alt} sx={sx} onError={() => setFailed(true)} />;
}
