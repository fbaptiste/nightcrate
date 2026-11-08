import type { CropSize, ThumbnailCropDef } from "@/api/projects";

export const MIN_FRAME_SIZE = 0.05;

export interface FitBox {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface CanvasFrame {
  u: number;
  v: number;
  s: number;
}

export type ResizeHandle = "nw" | "ne" | "sw" | "se";
export type NudgeKey =
  | "ArrowLeft"
  | "ArrowRight"
  | "ArrowUp"
  | "ArrowDown"
  | "+"
  | "="
  | "-"
  | "−";

export interface ThumbnailFrameSizeState {
  source_image_id: number | null;
  frame: CanvasFrame | null;
}

export interface CropPayloadState {
  sizes: Record<CropSize, ThumbnailFrameSizeState>;
  dirty: ReadonlySet<CropSize>;
  fitBySize: Partial<Record<CropSize, FitBox>>;
}

const FULL_FRAME: CanvasFrame = { u: 0, v: 0, s: 1 };

function clamp(value: number, low: number, high: number): number {
  return Math.min(high, Math.max(low, value));
}

/**
 * Return the smallest centred 4:3 image-fraction box containing an image.
 *
 * | Image | aspect | result `(x, y, w, h)` |
 * |---|---:|---|
 * | 2000×1000 | 2 | `(0, -1/4, 1, 3/2)` |
 * | 1000×2000 | 1/2 | `(-5/6, 0, 8/3, 1)` |
 * | 1000×1000 | 1 | `(-1/6, 0, 4/3, 1)` |
 * | 1200×900 | 4/3 | `(0, 0, 1, 1)` |
 * | 120×100 | 6/5 | `(-1/18, 0, 10/9, 1)` |
 */
export function fitBox(aspect: number): FitBox {
  if (aspect >= 4 / 3) {
    const h = 0.75 * aspect;
    return { x: 0, y: (1 - h) / 2, w: 1, h };
  }
  const w = 4 / (3 * aspect);
  return { x: (1 - w) / 2, y: 0, w, h: 1 };
}

/**
 * Convert an image-fraction crop to a valid canvas frame, clamping old rows.
 *
 * | Image | fit box | its fit box becomes `(u, v, s)` |
 * |---|---|---|
 * | 2000×1000 | `(0, -1/4, 1, 3/2)` | `(0, 0, 1)` |
 * | 1000×2000 | `(-5/6, 0, 8/3, 1)` | `(0, 0, 1)` |
 * | 1000×1000 | `(-1/6, 0, 4/3, 1)` | `(0, 0, 1)` |
 * | 1200×900 | `(0, 0, 1, 1)` | `(0, 0, 1)` |
 * | 120×100 | `(-1/18, 0, 10/9, 1)` | `(0, 0, 1)` |
 */
export function toCanvas(frame: FitBox, fit: FitBox): CanvasFrame {
  const s = clamp(frame.w / fit.w, MIN_FRAME_SIZE, 1);
  return {
    u: clamp((frame.x - fit.x) / fit.w, 0, 1 - s),
    v: clamp((frame.y - fit.y) / fit.h, 0, 1 - s),
    s,
  };
}

/**
 * Convert a normalized canvas frame to image fractions for the API.
 *
 * | Image | fit box | `toImage({0,0,1}, fit)` |
 * |---|---|---|
 * | 2000×1000 | `(0, -1/4, 1, 3/2)` | `(0, -1/4, 1, 3/2)` |
 * | 1000×2000 | `(-5/6, 0, 8/3, 1)` | `(-5/6, 0, 8/3, 1)` |
 * | 1000×1000 | `(-1/6, 0, 4/3, 1)` | `(-1/6, 0, 4/3, 1)` |
 * | 1200×900 | `(0, 0, 1, 1)` | `(0, 0, 1, 1)` |
 * | 120×100 | `(-1/18, 0, 10/9, 1)` | `(-1/18, 0, 10/9, 1)` |
 */
export function toImage(frame: CanvasFrame, fit: FitBox): FitBox {
  return {
    x: fit.x + frame.u * fit.w,
    y: fit.y + frame.v * fit.h,
    w: frame.s * fit.w,
    h: frame.s * fit.h,
  };
}

/**
 * Move a frame without allowing it outside the 4:3 canvas.
 *
 * | Image fit | start | delta | result |
 * |---|---|---|---|
 * | 2000×1000 | `(0,0,1)` | `(1,1)` | `(0,0,1)` |
 * | 1000×2000 | `(0,0,1/2)` | `(1,1)` | `(1/2,1/2,1/2)` |
 * | 1000×1000 | `(1/4,1/4,1/2)` | `(-1,-1)` | `(0,0,1/2)` |
 * | 1200×900 | `(0,0,1/2)` | `(1/4,1/4)` | `(1/4,1/4,1/2)` |
 * | 120×100 | `(1/4,1/4,1/2)` | `(1,0)` | `(1/2,1/4,1/2)` |
 */
export function moveFrame(frame: CanvasFrame, du: number, dv: number): CanvasFrame {
  return {
    u: clamp(frame.u + du, 0, 1 - frame.s),
    v: clamp(frame.v + dv, 0, 1 - frame.s),
    s: frame.s,
  };
}

/**
 * Resize a frame about the corner opposite the dragged handle.
 *
 * | Image fit | handle | start; delta | result size |
 * |---|---|---|---:|
 * | 2000×1000 | SE | `(0,0,1); (1,1)` | `1` |
 * | 1000×2000 | NW | `(1/2,1/2,1/2); (1,1)` | `0.05` |
 * | 1000×1000 | NE | `(0,1/2,1/2); (1,-1)` | `1` |
 * | 1200×900 | SW | `(1/2,0,1/2); (-1,1)` | `1` |
 * | 120×100 | SE | `(0,0,1/2); (1/4,1/4)` | `3/4` |
 */
export function resizeFrame(
  handle: ResizeHandle,
  start: CanvasFrame,
  du: number,
  dv: number,
): CanvasFrame {
  const fromLeft = handle === "nw" || handle === "sw";
  const fromTop = handle === "nw" || handle === "ne";
  const anchorU = fromLeft ? start.u + start.s : start.u;
  const anchorV = fromTop ? start.v + start.s : start.v;
  const horizontalGrowth = fromLeft ? -du : du;
  const verticalGrowth = fromTop ? -dv : dv;
  const maxSize = Math.min(fromLeft ? anchorU : 1 - anchorU, fromTop ? anchorV : 1 - anchorV);
  const s = clamp(
    Math.max(start.s + horizontalGrowth, start.s + verticalGrowth),
    Math.min(MIN_FRAME_SIZE, maxSize),
    maxSize,
  );
  return {
    u: fromLeft ? anchorU - s : anchorU,
    v: fromTop ? anchorV - s : anchorV,
    s,
  };
}

/**
 * Apply the editor's keyboard movement or centred resize step.
 *
 * | Image fit | key | start | result |
 * |---|---|---|---|
 * | 2000×1000 | Right | `(0,0,1)` | `(0,0,1)` |
 * | 1000×2000 | Shift+Right | `(0,0,1/2)` | `(0.05,0,1/2)` |
 * | 1000×1000 | Up | `(1/4,0,1/2)` | `(1/4,0,1/2)` |
 * | 1200×900 | `+` | `(1/4,1/4,1/2)` | `(0.24,0.24,0.52)` |
 * | 120×100 | `−` | `(1/4,1/4,1/2)` | `(0.26,0.26,0.48)` |
 */
export function nudge(frame: CanvasFrame, key: NudgeKey, shift = false): CanvasFrame {
  const step = shift ? 0.05 : 0.01;
  if (key === "ArrowLeft") return moveFrame(frame, -step, 0);
  if (key === "ArrowRight") return moveFrame(frame, step, 0);
  if (key === "ArrowUp") return moveFrame(frame, 0, -step);
  if (key === "ArrowDown") return moveFrame(frame, 0, step);

  const growing = key === "+" || key === "=";
  const centerU = frame.u + frame.s / 2;
  const centerV = frame.v + frame.s / 2;
  const s = clamp(frame.s + (growing ? 0.02 : -0.02), MIN_FRAME_SIZE, 1);
  return {
    u: clamp(centerU - s / 2, 0, 1 - s),
    v: clamp(centerV - s / 2, 0, 1 - s),
    s,
  };
}

/**
 * Apply the server's strict overlap rule to an image-fraction frame.
 *
 * | Image | fit box | overlaps the image? |
 * |---|---|---|
 * | 2000×1000 | `(0, -1/4, 1, 3/2)` | yes |
 * | 1000×2000 | `(-5/6, 0, 8/3, 1)` | yes |
 * | 1000×1000 | `(-1/6, 0, 4/3, 1)` | yes |
 * | 1200×900 | `(0, 0, 1, 1)` | yes |
 * | 120×100 | `(-1/18, 0, 10/9, 1)` | yes |
 */
export function overlapsImage(frame: FitBox): boolean {
  return frame.x < 1 && frame.x + frame.w > 0 && frame.y < 1 && frame.y + frame.h > 0;
}

/**
 * Build the API request from dirty sizes only; null frames mean the fit box.
 *
 * | Image fit | dirty size | emitted frame |
 * |---|---|---|
 * | 2000×1000 | small | `(0, -1/4, 1, 3/2)` |
 * | 1000×2000 | medium | `(-5/6, 0, 8/3, 1)` |
 * | 1000×1000 | large | `(-1/6, 0, 4/3, 1)` |
 * | 1200×900 | small | `(0, 0, 1, 1)` |
 * | 120×100 | medium | `(-1/18, 0, 10/9, 1)` |
 */
export function buildCropPayload(
  state: CropPayloadState,
): Partial<Record<CropSize, ThumbnailCropDef>> {
  const payload: Partial<Record<CropSize, ThumbnailCropDef>> = {};
  for (const size of state.dirty) {
    const fit = state.fitBySize[size];
    if (!fit) continue;
    const item = state.sizes[size];
    const frame = toImage(item.frame ?? FULL_FRAME, fit);
    payload[size] = {
      source_image_id: item.source_image_id,
      crop_x: frame.x,
      crop_y: frame.y,
      crop_w: frame.w,
      crop_h: frame.h,
    };
  }
  return payload;
}
