import { useCallback, useEffect, useRef, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Typography from "@mui/material/Typography";
import type { ProjectImage, ThumbnailCrop, ThumbnailCropDef } from "@/api/projects";
import { renderedImageUrl } from "@/api/projects";

const SIZES = ["small", "medium", "large"] as const;
type Size = (typeof SIZES)[number];

const SIZE_LABELS: Record<Size, string> = {
  small: "Small (list view, 1:1)",
  medium: "Medium (1:1)",
  large: "Large (gallery card, 4:3)",
};

const ASPECT_RATIOS: Record<Size, number> = {
  small: 1,
  medium: 1,
  large: 4 / 3,
};

interface CropState {
  source_image_id: number | null;
  crop_x: number;
  crop_y: number;
  crop_w: number;
  crop_h: number;
}

function defaultCrop(): CropState {
  return { source_image_id: null, crop_x: 0, crop_y: 0, crop_w: 1, crop_h: 1 };
}

function cropFromServer(crops: ThumbnailCrop[], size: Size): CropState {
  const found = crops.find((c) => c.size === size);
  if (!found) return defaultCrop();
  return {
    source_image_id: found.source_image_id,
    crop_x: found.crop_x,
    crop_y: found.crop_y,
    crop_w: found.crop_w,
    crop_h: found.crop_h,
  };
}

interface CropRectProps {
  crop: CropState;
  onChange: (c: CropState) => void;
  aspectRatio: number;
  containerRef: React.RefObject<HTMLDivElement | null>;
}

function CropRect({ crop, onChange, aspectRatio, containerRef }: CropRectProps) {
  const dragging = useRef<"move" | "nw" | "ne" | "sw" | "se" | null>(null);
  const startPos = useRef({ mx: 0, my: 0, cx: 0, cy: 0, cw: 0, ch: 0 });

  const getRelative = useCallback(
    (e: React.MouseEvent | MouseEvent) => {
      const el = containerRef.current;
      if (!el) return { rx: 0, ry: 0 };
      const r = el.getBoundingClientRect();
      return {
        rx: Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)),
        ry: Math.max(0, Math.min(1, (e.clientY - r.top) / r.height)),
      };
    },
    [containerRef],
  );

  const handleMouseDown = useCallback(
    (handle: "move" | "nw" | "ne" | "sw" | "se") => (e: React.MouseEvent) => {
      e.preventDefault();
      e.stopPropagation();
      dragging.current = handle;
      const { rx, ry } = getRelative(e);
      startPos.current = {
        mx: rx,
        my: ry,
        cx: crop.crop_x,
        cy: crop.crop_y,
        cw: crop.crop_w,
        ch: crop.crop_h,
      };

      const onMove = (ev: MouseEvent) => {
        const { rx: nx, ry: ny } = getRelative(ev);
        const s = startPos.current;
        const dx = nx - s.mx;
        const dy = ny - s.my;
        let { cx, cy, cw, ch } = s;

        if (dragging.current === "move") {
          cx = Math.max(0, Math.min(1 - cw, cx + dx));
          cy = Math.max(0, Math.min(1 - ch, cy + dy));
        } else {
          const isLeft = dragging.current === "nw" || dragging.current === "sw";
          const isTop = dragging.current === "nw" || dragging.current === "ne";

          if (isLeft) {
            const newX = Math.max(0, Math.min(cx + cw - 0.05, cx + dx));
            cw = cw + (cx - newX);
            cx = newX;
          } else {
            cw = Math.max(0.05, Math.min(1 - cx, cw + dx));
          }

          ch = cw / aspectRatio;
          if (isTop) {
            cy = s.cy + s.ch - ch;
          }
          cy = Math.max(0, Math.min(1 - ch, cy));
          if (cy + ch > 1) ch = 1 - cy;
          cw = ch * aspectRatio;
        }

        onChange({ ...crop, crop_x: cx, crop_y: cy, crop_w: cw, crop_h: ch });
      };

      const onUp = () => {
        dragging.current = null;
        window.removeEventListener("mousemove", onMove);
        window.removeEventListener("mouseup", onUp);
      };

      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
    },
    [crop, onChange, aspectRatio, getRelative],
  );

  const handleStyle = (pos: string): React.CSSProperties => ({
    position: "absolute",
    width: 10,
    height: 10,
    background: "white",
    border: "2px solid #1976d2",
    borderRadius: 2,
    ...(pos === "nw" ? { top: -5, left: -5, cursor: "nw-resize" } : {}),
    ...(pos === "ne" ? { top: -5, right: -5, cursor: "ne-resize" } : {}),
    ...(pos === "sw" ? { bottom: -5, left: -5, cursor: "sw-resize" } : {}),
    ...(pos === "se" ? { bottom: -5, right: -5, cursor: "se-resize" } : {}),
  });

  return (
    <Box
      sx={{
        position: "absolute",
        left: `${crop.crop_x * 100}%`,
        top: `${crop.crop_y * 100}%`,
        width: `${crop.crop_w * 100}%`,
        height: `${crop.crop_h * 100}%`,
        border: "2px solid #1976d2",
        boxShadow: "0 0 0 9999px rgba(0,0,0,0.5)",
        cursor: "move",
      }}
      onMouseDown={handleMouseDown("move")}
    >
      <div style={handleStyle("nw")} onMouseDown={handleMouseDown("nw")} />
      <div style={handleStyle("ne")} onMouseDown={handleMouseDown("ne")} />
      <div style={handleStyle("sw")} onMouseDown={handleMouseDown("sw")} />
      <div style={handleStyle("se")} onMouseDown={handleMouseDown("se")} />
    </Box>
  );
}

interface Props {
  open: boolean;
  onClose: () => void;
  projectId: number;
  images: ProjectImage[];
  mainImageId: number | null;
  existingCrops: ThumbnailCrop[];
  onApply: (crops: Record<string, ThumbnailCropDef>) => void;
}

export default function ThumbnailCropEditor({
  open,
  onClose,
  projectId,
  images,
  mainImageId,
  existingCrops,
  onApply,
}: Props) {
  const [tab, setTab] = useState<number>(0);
  const [crops, setCrops] = useState<Record<Size, CropState>>({
    small: defaultCrop(),
    medium: defaultCrop(),
    large: defaultCrop(),
  });
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (open) {
      setCrops({
        small: cropFromServer(existingCrops, "small"),
        medium: cropFromServer(existingCrops, "medium"),
        large: cropFromServer(existingCrops, "large"),
      });
    }
  }, [open, existingCrops]);

  const currentSize = SIZES[tab];
  const currentCrop = crops[currentSize];
  const sourceId = currentCrop.source_image_id ?? mainImageId;

  const handleCropChange = useCallback(
    (c: CropState) => {
      setCrops((prev) => ({ ...prev, [currentSize]: c }));
    },
    [currentSize],
  );

  const handleApply = () => {
    const result: Record<string, ThumbnailCropDef> = {};
    for (const size of SIZES) {
      const c = crops[size];
      result[size] = {
        source_image_id: c.source_image_id,
        crop_x: c.crop_x,
        crop_y: c.crop_y,
        crop_w: c.crop_w,
        crop_h: c.crop_h,
      };
    }
    onApply(result);
    onClose();
  };

  const handleReset = () => {
    setCrops((prev) => ({ ...prev, [currentSize]: defaultCrop() }));
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>Customize Thumbnails</DialogTitle>
      <DialogContent>
        <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
          {SIZES.map((s) => (
            <Tab key={s} label={SIZE_LABELS[s]} />
          ))}
        </Tabs>

        <Box sx={{ display: "flex", gap: 2, alignItems: "flex-start", mb: 2 }}>
          <FormControl size="small" sx={{ minWidth: 200 }}>
            <InputLabel>Source Image</InputLabel>
            <Select
              value={currentCrop.source_image_id ?? ""}
              label="Source Image"
              onChange={(e) => {
                const val = e.target.value as string | number;
                handleCropChange({
                  ...currentCrop,
                  source_image_id: val === "" ? null : Number(val),
                });
              }}
            >
              <MenuItem value="">Main image (default)</MenuItem>
              {images.map((img) => {
                const name = img.file_path.split("/").pop()?.split("::").pop() ?? `Image ${img.id}`;
                return (
                  <MenuItem key={img.id} value={img.id}>
                    {name}
                  </MenuItem>
                );
              })}
            </Select>
          </FormControl>
          <Button size="small" onClick={handleReset}>
            Reset
          </Button>
        </Box>

        {sourceId ? (
          <Box
            ref={containerRef}
            sx={{
              position: "relative",
              width: "100%",
              maxWidth: 500,
              aspectRatio: "1 / 1",
              bgcolor: "black",
              overflow: "hidden",
              borderRadius: 1,
              userSelect: "none",
            }}
          >
            <Box
              component="img"
              src={renderedImageUrl(projectId, sourceId, "thumb_lg")}
              alt=""
              sx={{
                width: "100%",
                height: "100%",
                objectFit: "contain",
                display: "block",
              }}
            />
            <CropRect
              crop={currentCrop}
              onChange={handleCropChange}
              aspectRatio={ASPECT_RATIOS[currentSize]}
              containerRef={containerRef}
            />
          </Box>
        ) : (
          <Typography color="text.secondary" sx={{ py: 4, textAlign: "center" }}>
            No images in this project. Add images first.
          </Typography>
        )}

        <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: "block" }}>
          Drag the rectangle to select the crop area. Drag corners to resize.
          {` Aspect ratio is constrained to ${ASPECT_RATIOS[currentSize] === 1 ? "1:1" : "4:3"}.`}
        </Typography>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" onClick={handleApply}>
          Apply
        </Button>
      </DialogActions>
    </Dialog>
  );
}
