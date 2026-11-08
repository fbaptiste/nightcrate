import { useEffect, useMemo, useState } from "react";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import IconButton from "@mui/material/IconButton";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import CloseIcon from "@mui/icons-material/Close";
import type { GalleryItem } from "@/api/gallery";
import { renderedImageUrl, type CropSize } from "@/api/projects";
import { viewerImageId, viewerSequence } from "@/lib/galleryRendition";

interface Props {
  items: GalleryItem[];
  startId: number | null;
  ws: string;
  cropSize: CropSize;
  onClose: (lastShownId: number) => void;
}

const navSx = {
  position: "fixed",
  top: "50%",
  transform: "translateY(-50%)",
  width: 52,
  height: 52,
  color: "common.white",
  border: "1px solid rgba(255, 255, 255, 0.28)",
  bgcolor: "rgba(255, 255, 255, 0.08)",
  "&:hover": { bgcolor: "rgba(255, 255, 255, 0.18)" },
  "&.Mui-disabled": { color: "common.white", opacity: 0.25 },
} as const;

export default function GalleryViewer({
  items,
  startId,
  ws,
  cropSize,
  onClose,
}: Props) {
  const sequence = useMemo(() => viewerSequence(items), [items]);
  const [currentId, setCurrentId] = useState(startId);
  const [loaded, setLoaded] = useState(false);
  const [failed, setFailed] = useState(false);
  const index = sequence.findIndex((item) => item.project_id === currentId);
  const item = index >= 0 ? sequence[index] : null;

  useEffect(() => {
    if (startId != null && currentId != null && index < 0) onClose(currentId);
  }, [currentId, index, onClose, startId]);

  useEffect(() => {
    for (const neighbor of [sequence[index - 1], sequence[index + 1]]) {
      const imageId = neighbor ? viewerImageId(neighbor, cropSize) : null;
      if (neighbor && imageId != null) {
        new Image().src = renderedImageUrl(
          neighbor.project_id,
          imageId,
          "full",
          ws,
        );
      }
    }
  }, [cropSize, index, sequence, ws]);

  if (startId == null || !item || item.main_image_id == null) return null;

  const close = () => onClose(item.project_id);
  const step = (delta: number) => {
    const next = sequence[index + delta];
    if (!next) return;
    setLoaded(false);
    setFailed(false);
    setCurrentId(next.project_id);
  };
  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      step(-1);
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      step(1);
    }
  };
  const imageId = viewerImageId(item, cropSize);
  if (imageId == null) return null;
  const src = renderedImageUrl(item.project_id, imageId, "full", ws);

  return (
    <Dialog
      open
      fullScreen
      onClose={close}
      onKeyDown={handleKeyDown}
      PaperProps={{ sx: { bgcolor: "#000000", backgroundImage: "none" } }}
    >
      <Box
        sx={{
          height: "100%",
          display: "grid",
          gridTemplateRows: "1fr auto",
          p: "56px 88px 16px",
          bgcolor: "#000000",
        }}
      >
        <Box
          sx={{
            position: "relative",
            minHeight: 0,
            display: "grid",
            placeItems: "center",
          }}
        >
          {!loaded && !failed && <CircularProgress sx={{ color: "#e2e0dd" }} />}
          {failed ? (
            <Box sx={{ color: "#e2e0dd" }}>
              Couldn't load the full-size image.
            </Box>
          ) : (
            <Box
              component="img"
              key={src}
              src={src}
              alt={item.name}
              onLoad={() => setLoaded(true)}
              onError={() => setFailed(true)}
              sx={{
                display: loaded ? "block" : "none",
                width: "100%",
                height: "100%",
                minHeight: 0,
                objectFit: "contain",
              }}
            />
          )}
        </Box>
        <Box
          sx={{
            display: "flex",
            alignItems: "flex-end",
            gap: "24px",
            pt: "12px",
            pr: "72px",
          }}
        >
          <Box sx={{ flex: 1, minWidth: 0, color: "#e2e0dd", fontSize: 14 }}>
            {item.name}
            <Box
              sx={{
                color: "#a3a09b",
                fontSize: 13,
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
              }}
            >
              {item.targets.map((target) => target.name).join(", ")}
            </Box>
          </Box>
          <Box
            aria-live="polite"
            sx={{
              position: "fixed",
              right: 88,
              bottom: 16,
              color: "#a3a09b",
              fontSize: 13,
              whiteSpace: "nowrap",
            }}
          >
            {index + 1} of {sequence.length}
          </Box>
        </Box>
      </Box>
      <IconButton
        aria-label="Close"
        onClick={close}
        sx={{
          position: "fixed",
          top: 12,
          right: 16,
          width: 40,
          height: 40,
          color: "common.white",
          border: "1px solid rgba(255, 255, 255, 0.28)",
          bgcolor: "rgba(255, 255, 255, 0.08)",
          "&:hover": { bgcolor: "rgba(255, 255, 255, 0.18)" },
        }}
      >
        <CloseIcon />
      </IconButton>
      <IconButton
        aria-label="Previous image"
        disabled={index === 0}
        onClick={() => step(-1)}
        sx={{ ...navSx, left: 20 }}
      >
        <ChevronLeftIcon sx={{ fontSize: 28 }} />
      </IconButton>
      <IconButton
        aria-label="Next image"
        disabled={index === sequence.length - 1}
        onClick={() => step(1)}
        sx={{ ...navSx, right: 20 }}
      >
        <ChevronRightIcon sx={{ fontSize: 28 }} />
      </IconButton>
    </Dialog>
  );
}
