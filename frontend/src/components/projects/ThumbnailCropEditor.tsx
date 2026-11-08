import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import type { KeyboardEvent, PointerEvent as ReactPointerEvent, RefObject } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Typography from "@mui/material/Typography";
import type {
  CropSize,
  ProjectImage,
  ThumbnailCrop,
  ThumbnailCropDef,
} from "@/api/projects";
import { renderedImageUrl } from "@/api/projects";
import {
  buildCropPayload,
  fitBox,
  moveFrame,
  nudge,
  overlapsImage,
  resizeFrame,
  toCanvas,
  toImage,
  type CanvasFrame,
  type FitBox,
  type NudgeKey,
  type ResizeHandle,
  type ThumbnailFrameSizeState,
} from "@/lib/thumbnailFrame";

const SIZES: CropSize[] = ["small", "medium", "large"];
const FULL_FRAME: CanvasFrame = { u: 0, v: 0, s: 1 };

const USED_TEXT: Record<CropSize, string> = {
  small: "Used for the Gallery's list and small pictures, and the Projects page's compact view.",
  medium: "Used for the Gallery's medium pictures and the Projects page's list.",
  large: "Used for the Gallery's large pictures and the Projects page's pictures.",
};

const PREVIEWS: Record<CropSize, { label: string; width: number }[]> = {
  small: [
    { label: "Gallery small", width: 180 },
    { label: "Gallery list", width: 180 },
    { label: "Projects compact", width: 76 },
  ],
  medium: [
    { label: "Gallery medium", width: 300 },
    { label: "Projects list", width: 160 },
  ],
  large: [
    { label: "Gallery large (shown smaller)", width: 360 },
    { label: "Projects pictures", width: 260 },
  ],
};

type FrameStates = Record<CropSize, ThumbnailFrameSizeState>;

type ImageAspectStatus =
  | { status: "loading"; url: string }
  | { status: "loaded"; url: string; aspect: number }
  | { status: "error"; url: string };

interface StoredFrame extends FitBox {
  source_image_id: number | null;
}

interface DragState {
  pointerId: number;
  handle: "move" | ResizeHandle;
  clientX: number;
  clientY: number;
  width: number;
  height: number;
  frame: CanvasFrame;
}

interface FrameProps {
  frame: CanvasFrame;
  canvasRef: RefObject<HTMLDivElement | null>;
  helpId: string;
  onChange: (frame: CanvasFrame) => void;
  onNudge: (key: NudgeKey, shift: boolean) => void;
}

function ThumbnailFrame({ frame, canvasRef, helpId, onChange, onNudge }: FrameProps) {
  const frameRef = useRef<HTMLDivElement | null>(null);
  const dragRef = useRef<DragState | null>(null);

  const startDrag = useCallback(
    (handle: "move" | ResizeHandle) => (event: ReactPointerEvent<HTMLDivElement>) => {
      if (!event.isPrimary || (event.pointerType === "mouse" && event.button !== 0)) return;
      const canvas = canvasRef.current;
      if (!canvas) return;

      event.preventDefault();
      if (handle !== "move") event.stopPropagation();
      const rect = canvas.getBoundingClientRect();
      dragRef.current = {
        pointerId: event.pointerId,
        handle,
        clientX: event.clientX,
        clientY: event.clientY,
        width: rect.width,
        height: rect.height,
        frame,
      };
      event.currentTarget.setPointerCapture(event.pointerId);
      frameRef.current?.focus({ preventScroll: true });
    },
    [canvasRef, frame],
  );

  const continueDrag = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      const drag = dragRef.current;
      if (!drag || drag.pointerId !== event.pointerId) return;
      event.preventDefault();
      const du = (event.clientX - drag.clientX) / drag.width;
      const dv = (event.clientY - drag.clientY) / drag.height;
      onChange(
        drag.handle === "move"
          ? moveFrame(drag.frame, du, dv)
          : resizeFrame(drag.handle, drag.frame, du, dv),
      );
    },
    [onChange],
  );

  const finishDrag = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    if (dragRef.current?.pointerId === event.pointerId) dragRef.current = null;
  }, []);

  const handleKeyDown = useCallback(
    (event: KeyboardEvent<HTMLDivElement>) => {
      const keys: NudgeKey[] = [
        "ArrowLeft",
        "ArrowRight",
        "ArrowUp",
        "ArrowDown",
        "+",
        "=",
        "-",
        "−",
      ];
      if (!keys.includes(event.key as NudgeKey)) return;
      event.preventDefault();
      onNudge(event.key as NudgeKey, event.shiftKey);
    },
    [onNudge],
  );

  const handleSx = (handle: ResizeHandle) => ({
    position: "absolute" as const,
    width: 28,
    height: 28,
    display: "grid",
    placeItems: "center",
    touchAction: "none",
    cursor: handle === "nw" || handle === "se" ? "nwse-resize" : "nesw-resize",
    ...(handle.includes("n") ? { top: -14 } : { bottom: -14 }),
    ...(handle.includes("w") ? { left: -14 } : { right: -14 }),
    "&::after": {
      content: '""',
      width: 12,
      height: 12,
      bgcolor: "common.white",
      border: 2,
      borderColor: "primary.main",
      borderStyle: "solid",
      borderRadius: "2px",
      boxSizing: "content-box",
    },
    "@media (pointer: coarse)": {
      width: 40,
      height: 40,
      ...(handle.includes("n") ? { top: -20 } : { bottom: -20 }),
      ...(handle.includes("w") ? { left: -20 } : { right: -20 }),
      "&::after": { width: 18, height: 18 },
    },
  });

  return (
    <Box
      ref={frameRef}
      role="slider"
      tabIndex={0}
      aria-label="Thumbnail frame"
      aria-describedby={helpId}
      aria-valuemin={5}
      aria-valuemax={100}
      aria-valuenow={Math.round(frame.s * 100)}
      aria-valuetext={`Frame ${Math.round(frame.s * 100)}% of the full view`}
      onPointerDown={startDrag("move")}
      onPointerMove={continueDrag}
      onPointerUp={finishDrag}
      onPointerCancel={finishDrag}
      onLostPointerCapture={finishDrag}
      onKeyDown={handleKeyDown}
      sx={{
        position: "absolute",
        zIndex: 2,
        left: `${frame.u * 100}%`,
        top: `${frame.v * 100}%`,
        width: `${frame.s * 100}%`,
        height: `${frame.s * 100}%`,
        outline: 2,
        outlineStyle: "solid",
        outlineColor: "primary.main",
        boxShadow: "0 0 0 1px rgba(0, 0, 0, 0.60)",
        cursor: "move",
        touchAction: "none",
        boxSizing: "border-box",
        "&:focus-visible": { outlineWidth: 3 },
      }}
    >
      {(["nw", "ne", "sw", "se"] as ResizeHandle[]).map((handle) => (
        <Box
          key={handle}
          onPointerDown={startDrag(handle)}
          onPointerMove={(event) => {
            event.stopPropagation();
            continueDrag(event);
          }}
          onPointerUp={(event) => {
            event.stopPropagation();
            finishDrag(event);
          }}
          onPointerCancel={(event) => {
            event.stopPropagation();
            finishDrag(event);
          }}
          onLostPointerCapture={(event) => {
            event.stopPropagation();
            finishDrag(event);
          }}
          sx={handleSx(handle)}
        />
      ))}
    </Box>
  );
}

interface PreviewProps {
  label: string;
  width: number;
  imageUrl: string;
  frame: FitBox;
}

function ThumbnailPreview({ label, width, imageUrl, frame }: PreviewProps) {
  return (
    <Box sx={{ color: "text.secondary", fontSize: 12, lineHeight: 1.4 }}>
      <Box
        sx={{
          position: "relative",
          width,
          maxWidth: "100%",
          aspectRatio: "4 / 3",
          bgcolor: "common.black",
          borderRadius: 1,
          overflow: "hidden",
          mb: 0.5,
        }}
      >
        <Box
          component="img"
          src={imageUrl}
          alt=""
          draggable={false}
          sx={{
            position: "absolute",
            display: "block",
            pointerEvents: "none",
            left: `${(-frame.x / frame.w) * 100}%`,
            top: `${(-frame.y / frame.h) * 100}%`,
            width: `${100 / frame.w}%`,
            height: `${100 / frame.h}%`,
          }}
        />
      </Box>
      {label}
    </Box>
  );
}

function emptyFrames(): FrameStates {
  return {
    small: { source_image_id: null, frame: null },
    medium: { source_image_id: null, frame: null },
    large: { source_image_id: null, frame: null },
  };
}

interface EditorState {
  frames: FrameStates;
  dirty: Set<CropSize>;
  saveError: string | null;
}

type EditorAction =
  | { type: "initialize"; frames: FrameStates }
  | { type: "hydrate"; frames: Partial<Record<CropSize, CanvasFrame>> }
  | { type: "update-frame"; size: CropSize; frame: CanvasFrame }
  | { type: "nudge-frame"; size: CropSize; key: NudgeKey; shift: boolean }
  | { type: "reset-frame"; size: CropSize }
  | { type: "change-source"; size: CropSize; sourceImageId: number | null }
  | { type: "clear-error" }
  | { type: "save-error"; message: string };

function framesEqual(left: CanvasFrame, right: CanvasFrame): boolean {
  return left.u === right.u && left.v === right.v && left.s === right.s;
}

function withUpdatedFrame(
  state: EditorState,
  size: CropSize,
  frame: CanvasFrame,
): EditorState {
  const current = state.frames[size].frame ?? FULL_FRAME;
  if (framesEqual(current, frame)) return state;

  const dirty = state.dirty.has(size) ? state.dirty : new Set(state.dirty).add(size);
  return {
    frames: {
      ...state.frames,
      [size]: { ...state.frames[size], frame },
    },
    dirty,
    saveError: null,
  };
}

function editorReducer(state: EditorState, action: EditorAction): EditorState {
  switch (action.type) {
    case "initialize":
      return { frames: action.frames, dirty: new Set(), saveError: null };
    case "hydrate": {
      let frames = state.frames;
      for (const size of SIZES) {
        const frame = action.frames[size];
        if (
          !frame ||
          state.dirty.has(size) ||
          framesEqual(state.frames[size].frame ?? FULL_FRAME, frame)
        ) {
          continue;
        }
        if (frames === state.frames) frames = { ...state.frames };
        frames[size] = { ...state.frames[size], frame };
      }
      return frames === state.frames ? state : { ...state, frames };
    }
    case "update-frame":
      return withUpdatedFrame(state, action.size, action.frame);
    case "nudge-frame":
      return withUpdatedFrame(
        state,
        action.size,
        nudge(state.frames[action.size].frame ?? FULL_FRAME, action.key, action.shift),
      );
    case "reset-frame": {
      const current = state.frames[action.size].frame ?? FULL_FRAME;
      if (framesEqual(current, FULL_FRAME) && state.dirty.has(action.size) && !state.saveError) {
        return state;
      }
      const dirty = state.dirty.has(action.size)
        ? state.dirty
        : new Set(state.dirty).add(action.size);
      return {
        frames: {
          ...state.frames,
          [action.size]: { ...state.frames[action.size], frame: FULL_FRAME },
        },
        dirty,
        saveError: null,
      };
    }
    case "change-source": {
      const current = state.frames[action.size];
      if (
        current.source_image_id === action.sourceImageId &&
        current.frame === null &&
        state.dirty.has(action.size) &&
        !state.saveError
      ) {
        return state;
      }
      const dirty = state.dirty.has(action.size)
        ? state.dirty
        : new Set(state.dirty).add(action.size);
      return {
        frames: {
          ...state.frames,
          [action.size]: { source_image_id: action.sourceImageId, frame: null },
        },
        dirty,
        saveError: null,
      };
    }
    case "clear-error":
      return state.saveError === null ? state : { ...state, saveError: null };
    case "save-error":
      return state.saveError === action.message ? state : { ...state, saveError: action.message };
  }
}

function fileName(path: string, imageId: number): string {
  return path.split(/[\\/]/).pop()?.split("::").pop() ?? `Image ${imageId}`;
}

function serverErrorDetail(error: unknown): string {
  const message = error instanceof Error ? error.message : String(error);
  try {
    const parsed = JSON.parse(message) as { detail?: unknown };
    if (typeof parsed.detail === "string") return parsed.detail;
  } catch {
    // The request wrapper may already have returned a plain-text detail.
  }
  return message;
}

interface Props {
  open: boolean;
  onClose: () => void;
  projectId: number;
  workspaceKey: string;
  images: ProjectImage[];
  mainImageId: number | null;
  existingCrops: ThumbnailCrop[];
  onApply: (crops: Partial<Record<CropSize, ThumbnailCropDef>>) => Promise<unknown>;
}

export default function ThumbnailCropEditor({
  open,
  onClose,
  projectId,
  workspaceKey,
  images,
  mainImageId,
  existingCrops,
  onApply,
}: Props) {
  const [currentSize, setCurrentSize] = useState<CropSize>("large");
  const [editor, dispatch] = useReducer(editorReducer, {
    frames: emptyFrames(),
    dirty: new Set<CropSize>(),
    saveError: null,
  });
  const [aspects, setAspects] = useState<Record<number, ImageAspectStatus>>({});
  const [isSaving, setIsSaving] = useState(false);
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const aspectCacheRef = useRef<Record<number, ImageAspectStatus>>({});
  const pendingStoredRef = useRef<Partial<Record<CropSize, StoredFrame>>>({});
  const helpId = `thumbnail-frame-help-${projectId}`;
  const { frames, dirty, saveError } = editor;

  const imageUrl = useCallback(
    (imageId: number) => renderedImageUrl(projectId, imageId, "thumb_lg", workspaceKey),
    [projectId, workspaceKey],
  );

  const loadAspect = useCallback(
    (imageId: number) => {
      const url = imageUrl(imageId);
      const cached = aspectCacheRef.current[imageId];
      if (cached?.url === url && (cached.status === "loading" || cached.status === "loaded")) {
        return;
      }

      const loading: ImageAspectStatus = { status: "loading", url };
      aspectCacheRef.current = { ...aspectCacheRef.current, [imageId]: loading };
      setAspects(aspectCacheRef.current);
      const preview = new Image();
      preview.onload = () => {
        if (aspectCacheRef.current[imageId]?.url !== url) return;
        const loaded: ImageAspectStatus = {
          status: "loaded",
          url,
          aspect: preview.naturalWidth / preview.naturalHeight,
        };
        aspectCacheRef.current = { ...aspectCacheRef.current, [imageId]: loaded };
        setAspects(aspectCacheRef.current);
        const pending = pendingStoredRef.current;
        const remaining = { ...pending };
        const hydrated: Partial<Record<CropSize, CanvasFrame>> = {};
        for (const size of SIZES) {
          const stored = pending[size];
          const effectiveSource = stored?.source_image_id ?? mainImageId;
          if (!stored || effectiveSource !== imageId) continue;
          hydrated[size] = toCanvas(stored, fitBox(loaded.aspect));
          delete remaining[size];
        }
        pendingStoredRef.current = remaining;
        dispatch({ type: "hydrate", frames: hydrated });
      };
      preview.onerror = () => {
        if (aspectCacheRef.current[imageId]?.url !== url) return;
        const failed: ImageAspectStatus = { status: "error", url };
        aspectCacheRef.current = { ...aspectCacheRef.current, [imageId]: failed };
        setAspects(aspectCacheRef.current);
      };
      preview.src = url;
    },
    [imageUrl, mainImageId],
  );

  useEffect(() => {
    if (!open) return;

    const initial = emptyFrames();
    const pending: Partial<Record<CropSize, StoredFrame>> = {};
    for (const size of SIZES) {
      const saved = existingCrops.find((crop) => crop.size === size);
      if (!saved) continue;
      initial[size].source_image_id = saved.source_image_id;
      const stored: StoredFrame = {
        source_image_id: saved.source_image_id,
        x: saved.crop_x,
        y: saved.crop_y,
        w: saved.crop_w,
        h: saved.crop_h,
      };
      const effectiveSource = saved.source_image_id ?? mainImageId;
      const cached = effectiveSource === null ? undefined : aspectCacheRef.current[effectiveSource];
      if (
        effectiveSource !== null &&
        cached?.status === "loaded" &&
        cached.url === imageUrl(effectiveSource)
      ) {
        initial[size].frame = toCanvas(stored, fitBox(cached.aspect));
      } else {
        pending[size] = stored;
      }
    }

    pendingStoredRef.current = pending;
    dispatch({ type: "initialize", frames: initial });
    setCurrentSize("large");
    setIsSaving(false);
    for (const image of images) loadAspect(image.id);
  }, [existingCrops, imageUrl, images, loadAspect, mainImageId, open]);

  const effectiveSourceId = useCallback(
    (size: CropSize) => frames[size].source_image_id ?? mainImageId,
    [frames, mainImageId],
  );

  const fitBySize = useMemo<Partial<Record<CropSize, FitBox>>>(() => {
    const result: Partial<Record<CropSize, FitBox>> = {};
    for (const size of SIZES) {
      const sourceId = effectiveSourceId(size);
      const status = sourceId === null ? undefined : aspects[sourceId];
      if (status?.status === "loaded") result[size] = fitBox(status.aspect);
    }
    return result;
  }, [aspects, effectiveSourceId]);

  const currentItem = frames[currentSize];
  const currentSourceId = effectiveSourceId(currentSize);
  const currentStatus = currentSourceId === null ? undefined : aspects[currentSourceId];
  const currentFit = fitBySize[currentSize];
  const currentFrame = currentItem.frame ?? FULL_FRAME;
  const currentImageFrame = currentFit ? toImage(currentFrame, currentFit) : null;
  const currentOverlaps = currentImageFrame ? overlapsImage(currentImageFrame) : true;
  const currentImageUrl = currentSourceId === null ? null : imageUrl(currentSourceId);

  const updateCurrentFrame = useCallback(
    (frame: CanvasFrame) => {
      dispatch({ type: "update-frame", size: currentSize, frame });
    },
    [currentSize],
  );

  const nudgeCurrentFrame = useCallback(
    (key: NudgeKey, shift: boolean) => {
      dispatch({ type: "nudge-frame", size: currentSize, key, shift });
    },
    [currentSize],
  );

  const changeSource = (sourceImageId: number | null) => {
    delete pendingStoredRef.current[currentSize];
    dispatch({ type: "change-source", size: currentSize, sourceImageId });
    const effectiveSource = sourceImageId ?? mainImageId;
    if (effectiveSource !== null) loadAspect(effectiveSource);
  };

  const resetCurrentFrame = () => {
    delete pendingStoredRef.current[currentSize];
    dispatch({ type: "reset-frame", size: currentSize });
  };

  const dirtyInvalid = [...dirty].some((size) => {
    const fit = fitBySize[size];
    if (!fit) return true;
    return !overlapsImage(toImage(frames[size].frame ?? FULL_FRAME, fit));
  });
  const currentUnavailable =
    currentSourceId !== null && (!currentStatus || currentStatus.status !== "loaded");

  const handleApply = async () => {
    if (dirty.size === 0) {
      onClose();
      return;
    }
    const payload = buildCropPayload({ sizes: frames, dirty, fitBySize });
    dispatch({ type: "clear-error" });
    setIsSaving(true);
    try {
      await onApply(payload);
      onClose();
    } catch (error) {
      dispatch({ type: "save-error", message: serverErrorDetail(error) });
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Dialog
      open={open}
      onClose={() => {
        if (!isSaving) onClose();
      }}
      fullWidth
      maxWidth="md"
      sx={{ "& .MuiDialog-paper": { maxWidth: 720 } }}
    >
      <DialogTitle sx={{ pb: 1.5 }}>Thumbnails</DialogTitle>
      <DialogContent>
        <Tabs
          value={currentSize}
          onChange={(_, value: CropSize) => setCurrentSize(value)}
          sx={{ minHeight: 40, mb: 1, borderBottom: 1, borderColor: "divider" }}
        >
          {SIZES.map((size) => (
            <Tab
              key={size}
              value={size}
              sx={{ minHeight: 40, minWidth: 0, px: 0.25, mr: 3.5, py: 1, textTransform: "none" }}
              label={
                <Box component="span">
                  {size[0].toUpperCase() + size.slice(1)}
                  {dirty.has(size) && (
                    <Box component="span" sx={{ color: "primary.main", ml: 0.5 }}>
                      •
                    </Box>
                  )}
                </Box>
              }
            />
          ))}
        </Tabs>

        <Typography color="text.secondary" sx={{ fontSize: 13, lineHeight: 1.5, mb: 1.5 }}>
          {USED_TEXT[currentSize]}
        </Typography>

        <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, mb: 1.5, flexWrap: "wrap" }}>
          <Select
            size="small"
            value={currentItem.source_image_id ?? ""}
            displayEmpty
            renderValue={(selected) => {
              const value = selected as number | string;
              if (value === "") return "Main image (default)";
              const image = images.find((item) => item.id === Number(value));
              return image ? fileName(image.file_path, image.id) : `Image ${value}`;
            }}
            inputProps={{ "aria-label": "Image" }}
            onChange={(event) => {
              const value = event.target.value as number | string;
              changeSource(value === "" ? null : Number(value));
            }}
            sx={{ minWidth: 260 }}
          >
            <MenuItem value="">Main image (default)</MenuItem>
            {images.map((image) => (
              <MenuItem key={image.id} value={image.id}>
                {fileName(image.file_path, image.id)}
              </MenuItem>
            ))}
          </Select>
          <Button size="small" onClick={resetCurrentFrame}>
            Whole picture
          </Button>
        </Box>

        {currentStatus?.status === "error" ? (
          <Alert severity="error">No preview, so this image can't be framed.</Alert>
        ) : (
          <Box sx={{ p: 2, mx: -2 }}>
            <Box
              ref={canvasRef}
              sx={{
                position: "relative",
                width: "100%",
                maxWidth: 640,
                aspectRatio: "4 / 3",
                touchAction: "none",
                userSelect: "none",
                WebkitUserSelect: "none",
                WebkitTouchCallout: "none",
              }}
            >
              <Box
                sx={{
                  position: "absolute",
                  inset: 0,
                  bgcolor: "common.black",
                  borderRadius: 1,
                  overflow: "hidden",
                }}
              >
                {currentFit && currentImageUrl && currentImageFrame ? (
                  <>
                    <Box
                      component="img"
                      src={currentImageUrl}
                      alt=""
                      draggable={false}
                      sx={{
                        position: "absolute",
                        display: "block",
                        pointerEvents: "none",
                        left: `${(-currentFit.x / currentFit.w) * 100}%`,
                        top: `${(-currentFit.y / currentFit.h) * 100}%`,
                        width: `${100 / currentFit.w}%`,
                        height: `${100 / currentFit.h}%`,
                      }}
                    />
                    <Box
                      sx={{
                        position: "absolute",
                        pointerEvents: "none",
                        left: `${(-currentFit.x / currentFit.w) * 100}%`,
                        top: `${(-currentFit.y / currentFit.h) * 100}%`,
                        width: `${100 / currentFit.w}%`,
                        height: `${100 / currentFit.h}%`,
                        outline: "1px dashed rgba(255, 255, 255, 0.35)",
                      }}
                    />
                    <Box
                      sx={{
                        position: "absolute",
                        pointerEvents: "none",
                        bgcolor: "rgba(0, 0, 0, 0.55)",
                        left: 0,
                        top: 0,
                        width: "100%",
                        height: `${currentFrame.v * 100}%`,
                      }}
                    />
                    <Box
                      sx={{
                        position: "absolute",
                        pointerEvents: "none",
                        bgcolor: "rgba(0, 0, 0, 0.55)",
                        left: 0,
                        top: `${(currentFrame.v + currentFrame.s) * 100}%`,
                        width: "100%",
                        height: `${(1 - currentFrame.v - currentFrame.s) * 100}%`,
                      }}
                    />
                    <Box
                      sx={{
                        position: "absolute",
                        pointerEvents: "none",
                        bgcolor: "rgba(0, 0, 0, 0.55)",
                        left: 0,
                        top: `${currentFrame.v * 100}%`,
                        width: `${currentFrame.u * 100}%`,
                        height: `${currentFrame.s * 100}%`,
                      }}
                    />
                    <Box
                      sx={{
                        position: "absolute",
                        pointerEvents: "none",
                        bgcolor: "rgba(0, 0, 0, 0.55)",
                        left: `${(currentFrame.u + currentFrame.s) * 100}%`,
                        top: `${currentFrame.v * 100}%`,
                        width: `${(1 - currentFrame.u - currentFrame.s) * 100}%`,
                        height: `${currentFrame.s * 100}%`,
                      }}
                    />
                  </>
                ) : (
                  <Box sx={{ position: "absolute", inset: 0, display: "grid", placeItems: "center" }}>
                    <CircularProgress size={28} aria-label="Loading image preview" />
                  </Box>
                )}
              </Box>
              {currentFit && currentImageFrame && (
                <ThumbnailFrame
                  frame={currentFrame}
                  canvasRef={canvasRef}
                  helpId={helpId}
                  onChange={updateCurrentFrame}
                  onNudge={nudgeCurrentFrame}
                />
              )}
            </Box>
          </Box>
        )}

        <Typography
          id={helpId}
          color="text.secondary"
          sx={{ fontSize: 12, lineHeight: 1.5, mt: 1, maxWidth: 640 }}
        >
          Drag the frame to move it, or drag a corner to resize it. Keyboard: arrow keys move it
          (Shift for bigger steps); + and − resize it.
        </Typography>
        <Typography
          aria-live="polite"
          sx={{
            minHeight: 20,
            mt: 1,
            fontSize: 13,
            lineHeight: 1.5,
            fontWeight: 600,
            color: (theme) => (theme.palette.mode === "dark" ? "#f0a35e" : "#b85500"),
          }}
        >
          {!currentOverlaps && "The frame must include part of the picture."}
        </Typography>

        {currentImageFrame && currentImageUrl && (
          <Box sx={{ display: "flex", gap: 2.25, alignItems: "flex-end", flexWrap: "wrap", mt: 2 }}>
            {PREVIEWS[currentSize].map((preview) => (
              <ThumbnailPreview
                key={preview.label}
                label={preview.label}
                width={preview.width}
                imageUrl={currentImageUrl}
                frame={currentImageFrame}
              />
            ))}
          </Box>
        )}

        {saveError && (
          <Alert severity="error" sx={{ mt: 2 }}>
            {saveError}
          </Alert>
        )}
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose} disabled={isSaving}>
          Cancel
        </Button>
        <Button
          variant="contained"
          onClick={handleApply}
          disabled={isSaving || currentUnavailable || dirtyInvalid}
          startIcon={isSaving ? <CircularProgress size={16} color="inherit" /> : undefined}
        >
          {isSaving ? "Applying…" : "Apply"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
