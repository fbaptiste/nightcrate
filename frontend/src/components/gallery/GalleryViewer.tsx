import { useEffect, useState } from "react";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import IconButton from "@mui/material/IconButton";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import CloseIcon from "@mui/icons-material/Close";
import { renderedImageUrl } from "@/api/projects";

export interface ViewerEntry {
  key: string;
  projectId: number;
  imageId: number;
  title: string;
  subtitle: string;
}

interface Props {
  entries: ViewerEntry[];
  startKey: string | null;
  ws: string;
  onClose: (lastKey: string) => void;
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

export default function GalleryViewer({ entries, startKey, ws, onClose }: Props) {
  const [currentKey, setCurrentKey] = useState(startKey);
  const [loaded, setLoaded] = useState(false);
  const [failed, setFailed] = useState(false);
  const index = entries.findIndex((entry) => entry.key === currentKey);
  const entry = index >= 0 ? entries[index] : null;

  useEffect(() => {
    if (startKey != null && currentKey != null && index < 0) onClose(currentKey);
  }, [currentKey, index, onClose, startKey]);

  useEffect(() => {
    for (const neighbor of [entries[index - 1], entries[index + 1]]) {
      if (neighbor) {
        new Image().src = renderedImageUrl(neighbor.projectId, neighbor.imageId, "full", ws);
      }
    }
  }, [entries, index, ws]);

  if (startKey == null || !entry) return null;

  const close = () => onClose(entry.key);
  const step = (delta: number) => {
    const next = entries[index + delta];
    if (!next) return;
    setLoaded(false);
    setFailed(false);
    setCurrentKey(next.key);
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
  const src = renderedImageUrl(entry.projectId, entry.imageId, "full", ws);

  return (
    <Dialog open fullScreen onClose={close} onKeyDown={handleKeyDown} PaperProps={{ sx: { bgcolor: "#000000", backgroundImage: "none" } }}>
      <Box sx={{ height: "100%", display: "grid", gridTemplateRows: "1fr auto", p: "56px 88px 16px", bgcolor: "#000000" }}>
        <Box sx={{ position: "relative", minHeight: 0, display: "grid", placeItems: "center" }}>
          {!loaded && !failed && <CircularProgress sx={{ color: "#e2e0dd" }} />}
          {failed ? (
            <Box sx={{ color: "#e2e0dd" }}>Couldn't load the full-size image.</Box>
          ) : (
            <Box component="img" key={entry.key} src={src} alt={entry.title} onLoad={() => setLoaded(true)} onError={() => setFailed(true)} sx={{ display: loaded ? "block" : "none", width: "100%", height: "100%", minHeight: 0, objectFit: "contain" }} />
          )}
        </Box>
        <Box sx={{ display: "flex", alignItems: "flex-end", gap: "24px", pt: "12px", pr: "72px" }}>
          <Box sx={{ flex: 1, minWidth: 0, color: "#e2e0dd", fontSize: 14 }}>
            {entry.title}
            <Box sx={{ color: "#a3a09b", fontSize: 13, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{entry.subtitle}</Box>
          </Box>
          <Box aria-live="polite" sx={{ position: "fixed", right: 88, bottom: 16, color: "#a3a09b", fontSize: 13, whiteSpace: "nowrap" }}>{index + 1} of {entries.length}</Box>
        </Box>
      </Box>
      <IconButton aria-label="Close" onClick={close} sx={{ position: "fixed", top: 12, right: 16, width: 40, height: 40, color: "common.white", border: "1px solid rgba(255, 255, 255, 0.28)", bgcolor: "rgba(255, 255, 255, 0.08)", "&:hover": { bgcolor: "rgba(255, 255, 255, 0.18)" } }}><CloseIcon /></IconButton>
      <IconButton aria-label="Previous image" disabled={index === 0} onClick={() => step(-1)} sx={{ ...navSx, left: 20 }}><ChevronLeftIcon sx={{ fontSize: 28 }} /></IconButton>
      <IconButton aria-label="Next image" disabled={index === entries.length - 1} onClick={() => step(1)} sx={{ ...navSx, right: 20 }}><ChevronRightIcon sx={{ fontSize: 28 }} /></IconButton>
    </Dialog>
  );
}
