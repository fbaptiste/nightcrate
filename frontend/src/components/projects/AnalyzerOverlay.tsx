import { useEffect, useRef } from "react";
import Box from "@mui/material/Box";
import Dialog from "@mui/material/Dialog";
import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import CloseIcon from "@mui/icons-material/Close";

import { getActivity, setActivity } from "@/api/client";
import ImageAnalyzerView from "@/components/analyzer/ImageAnalyzerView";
import { monoFontFamily } from "@/theme/theme";

export interface AnalyzerItem {
  id: number;
  path: string;
  name: string;
}

interface Props {
  open: boolean;
  onClose: () => void;
  /** The launching list, already scoped to the active tab + filter pill. */
  items: AnalyzerItem[];
  index: number;
  onIndexChange: (next: number) => void;
  /** Called when stepping past the last loaded item, to pull the next page. */
  onNeedMore?: () => void;
}

/**
 * The Image Analyzer as a full-screen overlay inside a project.
 *
 * The URL stays on `/projects/:id` — closing returns to the catalog exactly
 * where it was. Rendered without a `DialogContent` on purpose: its padding and
 * `overflow-y` would double-scroll and clip the histogram, and the view already
 * expects to fill a height-bounded flex parent.
 */
export default function AnalyzerOverlay({
  open,
  onClose,
  items,
  index,
  onIndexChange,
  onNeedMore,
}: Props) {
  const current = items[index];
  const savedActivity = useRef<string | null>(null);

  // The Activity Console label is set on route change, and opening the overlay
  // changes no route — so without save/restore the overlay's last label would
  // stick to every later project request.
  useEffect(() => {
    if (open) {
      savedActivity.current = getActivity();
    } else if (savedActivity.current !== null) {
      setActivity(savedActivity.current);
      savedActivity.current = null;
    }
  }, [open]);

  const canPrev = index > 0;
  const canNext = index < items.length - 1;

  const step = (delta: number) => {
    const next = index + delta;
    if (next < 0 || next >= items.length) return;
    onIndexChange(next);
    // Pre-fetch the following page as the user approaches the end of what's loaded.
    if (next >= items.length - 2) onNeedMore?.();
  };

  const toolbarStart = current ? (
    <Box sx={{ display: "flex", alignItems: "center", gap: 1, minWidth: 0, flexGrow: 1 }}>
      <Tooltip title="Previous frame">
        <span>
          <IconButton size="small" onClick={() => step(-1)} disabled={!canPrev}>
            <ChevronLeftIcon fontSize="small" />
          </IconButton>
        </span>
      </Tooltip>
      <Tooltip title="Next frame">
        <span>
          <IconButton size="small" onClick={() => step(1)} disabled={!canNext}>
            <ChevronRightIcon fontSize="small" />
          </IconButton>
        </span>
      </Tooltip>
      <Typography
        sx={{
          fontFamily: monoFontFamily,
          fontSize: "0.75rem",
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}
      >
        {current.name}
      </Typography>
      <Typography variant="caption" color="text.secondary" sx={{ flexShrink: 0 }}>
        {index + 1} / {items.length}
      </Typography>
    </Box>
  ) : null;

  const toolbarEnd = (
    <Tooltip title="Close (Esc)">
      <IconButton size="small" onClick={onClose} aria-label="close analyzer">
        <CloseIcon fontSize="small" />
      </IconButton>
    </Tooltip>
  );

  return (
    <Dialog
      open={open}
      onClose={onClose}
      fullScreen
      slotProps={{
        paper: {
          sx: { display: "flex", flexDirection: "column", overflow: "hidden" },
        },
      }}
    >
      <ImageAnalyzerView
        path={current?.path ?? ""}
        displayName={current?.name}
        toolbarStart={toolbarStart}
        toolbarEnd={toolbarEnd}
      />
    </Dialog>
  );
}
