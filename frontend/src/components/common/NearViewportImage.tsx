import { useEffect, useRef, useState, type ReactNode } from "react";
import Box from "@mui/material/Box";
import type { SxProps, Theme } from "@mui/material/styles";
import ProjectImage from "./ProjectImage";

interface Props {
  src: string;
  alt: string;
  fallback: ReactNode;
  sx?: SxProps<Theme>;
}

export default function NearViewportImage({ src, alt, fallback, sx }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [near, setNear] = useState(false);

  useEffect(() => {
    if (near || !ref.current) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setNear(true);
          observer.disconnect();
        }
      },
      { rootMargin: "400px" },
    );
    observer.observe(ref.current);
    return () => observer.disconnect();
  }, [near]);

  return (
    <Box
      ref={ref}
      sx={{
        display: "block",
        width: "100%",
        height: "100%",
      }}
    >
      {near ? (
        <ProjectImage key={src} src={src} alt={alt} fallback={fallback} sx={sx} />
      ) : null}
    </Box>
  );
}
