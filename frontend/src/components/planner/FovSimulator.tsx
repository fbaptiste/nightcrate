/**
 * FOV Simulator — v0.18.0 / Pass C.
 *
 * A single composite of sky-tile cells (shared region tangent,
 * pixel-perfect stitching) with the rig's sensor rectangle overlaid.
 * Users pan / zoom / rotate the rectangle over the sky to plan
 * framing.
 *
 * Layout:
 *
 *   ┌──────── viewport (size × size CSS px) ────────┐
 *   │                                                │
 *   │    ┌─── pan group (composite source px) ────┐ │
 *   │    │   SkyTileComposite                       │
 *   │    │   DsoAnnotationOverlay                   │
 *   │    │   Rig rectangle (sensor)                 │
 *   │    └──────────────────────────────────────────┘ │
 *   └────────────────────────────────────────────────┘
 *
 * The pan group is the composite's **native** source-pixel size
 * (narrow tier: ~4000 px across, med: ~2000, wide: ~5000). A CSS
 * transform ``translate(…) scale(zoom)`` positions it inside the
 * viewport. ``zoom = 1`` shows one source pixel per CSS pixel (native
 * resolution); ``zoom = viewport / max(composite)`` fits the whole
 * composite in the viewport.
 *
 * The DSO's screen position is anchored on the composite's
 * ``view_center_pixel_x/y`` — cell boundaries don't have to align with
 * the DSO centre, so we pin the viewport centre on that pixel rather
 * than on the composite centre.
 *
 * Drag performance: pointermove writes ``el.style.transform`` directly
 * via refs; state catches up on pointerup. Mirrors the v0.17.0
 * pattern so the UX stays responsive when the user drags fast.
 */
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import IconButton from "@mui/material/IconButton";
import Slider from "@mui/material/Slider";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import RestartAltIcon from "@mui/icons-material/RestartAlt";
import VisibilityIcon from "@mui/icons-material/Visibility";
import VisibilityOffIcon from "@mui/icons-material/VisibilityOff";
import { RIG_ORANGE } from "@/lib/rigColors";
import { formatDec, formatRa } from "@/lib/dsoFormatters";
import { arcminToSlider, sliderToArcmin } from "@/lib/dsoAnnotations";
import {
  fetchNearbyDsos,
  type NearbyDsoItem,
  type SkyTileGridLayout,
  type SkyTileTier,
} from "@/api/planner";
import SkyTileComposite from "./SkyTileComposite";
import DsoAnnotationOverlay from "./DsoAnnotationOverlay";
import DsoAnnotationPopover from "./DsoAnnotationPopover";

interface Props {
  dsoId: number;
  fovMajorDeg: number;
  fovMinorDeg: number;
  dsoMajAxisArcmin?: number | null;
  centerRaDeg?: number | null;
  centerDecDeg?: number | null;
  primaryDesignation?: string | null;
  onSelectDso?: (dsoId: number) => void;
  /** CSS pixel size of the viewport (square). */
  size?: number;
}

// ── Utilities ────────────────────────────────────────────────────────────────

function tierForFov(fov: number): SkyTileTier {
  // Must stay in lockstep with the backend's ``tier_for_fov`` in
  // ``services/sky_tiles.py``. Same thresholds, same fallback.
  if (fov <= 1.0) return "narrow";
  if (fov <= 3.0) return "med";
  return "wide";
}

function cellSizeForTier(tier: SkyTileTier): number {
  return tier === "narrow" ? 0.5 : tier === "med" ? 2.0 : 8.0;
}

// View side — 5 cells across, same ~25-cell budget regardless of tier.
const VIEW_CELLS_ACROSS = 5;

function normalizeAngle(deg: number): number {
  return ((deg % 360) + 360) % 360;
}
function wrapRa(deg: number): number {
  return ((deg % 360) + 360) % 360;
}
function clampDec(deg: number): number {
  return Math.max(-90, Math.min(90, deg));
}
function clamp(v: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, v));
}
function angleFromCenter(
  px: number,
  py: number,
  cx: number,
  cy: number,
): number {
  return (Math.atan2(py - cy, px - cx) * 180) / Math.PI;
}

const ROTATE_CURSOR =
  "url(\"data:image/svg+xml;utf8," +
  "<svg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24' fill='none' stroke='white' stroke-width='2.5'>" +
  "<path d='M3 12a9 9 0 1015 -6.7L21 3M21 3v6h-6'/>" +
  "</svg>\") 12 12, crosshair";

function buildRectTransform(
  offsetX: number,
  offsetY: number,
  rotation: number,
): string {
  return `translate(calc(-50% + ${offsetX}px), calc(-50% + ${offsetY}px)) rotate(${-rotation}deg)`;
}

function offsetPxToSkyDelta(
  offsetX: number,
  offsetY: number,
  pxPerDeg: number,
  centreDecDeg: number,
): { dRaDeg: number; dDecDeg: number } {
  const cosDec = Math.max(Math.cos((centreDecDeg * Math.PI) / 180), 1e-6);
  const dRaDeg = -offsetX / pxPerDeg / cosDec;
  const dDecDeg = -offsetY / pxPerDeg;
  return { dRaDeg, dDecDeg };
}

function formatDelta(deg: number, positive: string, negative: string): string {
  const absDeg = Math.abs(deg);
  const label = deg >= 0 ? positive : negative;
  if (absDeg < 1 / 60) return `${(absDeg * 3600).toFixed(1)}\u2033 ${label}`;
  if (absDeg < 1) return `${(absDeg * 60).toFixed(1)}\u2032 ${label}`;
  return `${absDeg.toFixed(2)}\u00B0 ${label}`;
}

// ── Component ────────────────────────────────────────────────────────────────

export default function FovSimulator({
  dsoId,
  fovMajorDeg,
  fovMinorDeg,
  dsoMajAxisArcmin,
  centerRaDeg,
  centerDecDeg,
  primaryDesignation,
  onSelectDso,
  size = 520,
}: Props) {
  const [rotation, setRotation] = useState(0);
  const [rectOffsetX, setRectOffsetX] = useState(0);
  const [rectOffsetY, setRectOffsetY] = useState(0);
  const [panX, setPanX] = useState(0);
  const [panY, setPanY] = useState(0);
  // ``null`` before the first layout arrives — we then default to
  // fit-to-viewport. After that the user can zoom anywhere in
  // [fit, 1].
  const [zoom, setZoom] = useState<number | null>(null);
  const [layout, setLayout] = useState<SkyTileGridLayout | null>(null);
  const [isShiftHeld, setIsShiftHeld] = useState(false);
  const [showAnnotations, setShowAnnotations] = useState(true);
  const [annotationSlider, setAnnotationSlider] = useState(0);
  const [popover, setPopover] = useState<
    { anchor: Element; item: NearbyDsoItem } | null
  >(null);

  const containerRef = useRef<HTMLDivElement | null>(null);
  const panGroupRef = useRef<HTMLDivElement | null>(null);
  const rectRef = useRef<HTMLDivElement | null>(null);
  const rotationDisplayRef = useRef<HTMLSpanElement | null>(null);
  const raDisplayRef = useRef<HTMLSpanElement | null>(null);
  const decDisplayRef = useRef<HTMLSpanElement | null>(null);

  const rotationRef = useRef(0);
  const rectOffsetXRef = useRef(0);
  const rectOffsetYRef = useRef(0);
  const panXRef = useRef(0);
  const panYRef = useRef(0);
  const zoomRef = useRef(0);
  const layoutRef = useRef<SkyTileGridLayout | null>(null);

  const dragStateRef = useRef<
    | {
        pointerId: number;
        mode: "pan" | "rect";
        lastX: number;
        lastY: number;
      }
    | null
  >(null);

  const tier = useMemo(() => tierForFov(fovMajorDeg), [fovMajorDeg]);
  const extentDeg = useMemo(
    () => cellSizeForTier(tier) * VIEW_CELLS_ACROSS,
    [tier],
  );

  // Derived from the layout (null until the first grid-layout response).
  const sourcePxPerDeg = layout ? layout.cell_width_px / layout.cell_size_deg : 0;
  const rectWidth = sourcePxPerDeg * fovMajorDeg;
  const rectHeight = sourcePxPerDeg * fovMinorDeg;

  // Zoom bounds.
  //   zoomFit — whole composite visible in the viewport (floor).
  //   zoomMax = 1 — one source pixel per CSS pixel (native resolution).
  //   zoomDefault — chosen so the rig rectangle's major axis fills
  //     about 75% of the viewport: plenty of target prominence, still
  //     enough surrounding sky to sanity-check framing.
  const zoomFit = layout
    ? size / Math.max(layout.composite_width_px, layout.composite_height_px)
    : 1;
  const zoomMax = 1;
  const TARGET_RECT_FRACTION = 0.75;
  const zoomDefault = useMemo(() => {
    if (!layout) return 1;
    const pxPerDeg = layout.cell_width_px / layout.cell_size_deg;
    const rectMajorSourcePx = fovMajorDeg * pxPerDeg;
    if (rectMajorSourcePx <= 0) return zoomFit;
    // rect_on_screen_px = rectMajorSourcePx × zoom; solve for zoom such
    // that rect_on_screen_px = TARGET_RECT_FRACTION × size.
    return Math.max(
      zoomFit,
      Math.min(zoomMax, (TARGET_RECT_FRACTION * size) / rectMajorSourcePx),
    );
  }, [layout, fovMajorDeg, size, zoomFit]);
  const zoomEff = zoom ?? zoomDefault;

  // Pan group transform — composites the scale + centre-on-view-center + pan.
  function panGroupTransformFromRefs(): string {
    const l = layoutRef.current;
    if (!l) return "";
    const z = zoomRef.current;
    const cx = size / 2 - l.view_center_pixel_x * z;
    const cy = size / 2 - l.view_center_pixel_y * z;
    return `translate(${cx + panXRef.current}px, ${cy + panYRef.current}px) scale(${z})`;
  }

  function panGroupTransformFromState(
    panXv: number,
    panYv: number,
    zoomV: number,
    l: SkyTileGridLayout | null,
  ): string {
    if (!l) return "";
    const cx = size / 2 - l.view_center_pixel_x * zoomV;
    const cy = size / 2 - l.view_center_pixel_y * zoomV;
    return `translate(${cx + panXv}px, ${cy + panYv}px) scale(${zoomV})`;
  }

  function currentPanLimit(): { x: number; y: number } {
    const l = layoutRef.current;
    if (!l) return { x: 0, y: 0 };
    const z = zoomRef.current;
    // Bound pan so the DSO's pixel never leaves the viewport. Allow
    // the composite edges to enter the viewport — useful when the DSO
    // sits near the region edge and we want to peek at the opposite
    // side.
    const xLim = Math.max(
      0,
      Math.max(l.view_center_pixel_x, l.composite_width_px - l.view_center_pixel_x) * z,
    );
    const yLim = Math.max(
      0,
      Math.max(l.view_center_pixel_y, l.composite_height_px - l.view_center_pixel_y) * z,
    );
    return { x: xLim, y: yLim };
  }

  function applyLive() {
    const rect = rectRef.current;
    if (rect) {
      rect.style.transform = buildRectTransform(
        rectOffsetXRef.current,
        rectOffsetYRef.current,
        rotationRef.current,
      );
    }
    const pg = panGroupRef.current;
    if (pg) {
      pg.style.transform = panGroupTransformFromRefs();
    }
    const rotEl = rotationDisplayRef.current;
    if (rotEl) rotEl.textContent = `${Math.round(rotationRef.current)}\u00B0`;
    if (centerRaDeg != null && centerDecDeg != null && sourcePxPerDeg > 0) {
      const { dRaDeg, dDecDeg } = offsetPxToSkyDelta(
        rectOffsetXRef.current,
        rectOffsetYRef.current,
        sourcePxPerDeg,
        centerDecDeg,
      );
      const rectRa = wrapRa(centerRaDeg + dRaDeg);
      const rectDec = clampDec(centerDecDeg + dDecDeg);
      if (raDisplayRef.current) raDisplayRef.current.textContent = formatRa(rectRa);
      if (decDisplayRef.current) decDisplayRef.current.textContent = formatDec(rectDec);
    }
  }

  useLayoutEffect(() => {
    rotationRef.current = rotation;
    rectOffsetXRef.current = rectOffsetX;
    rectOffsetYRef.current = rectOffsetY;
    panXRef.current = panX;
    panYRef.current = panY;
    zoomRef.current = zoomEff;
    layoutRef.current = layout;
    applyLive();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    rotation,
    rectOffsetX,
    rectOffsetY,
    panX,
    panY,
    zoomEff,
    layout,
    centerRaDeg,
    centerDecDeg,
    sourcePxPerDeg,
    size,
  ]);

  // Re-clamp pan when the zoom or layout changes.
  useEffect(() => {
    const { x, y } = currentPanLimit();
    setPanX((px) => clamp(px, -x, x));
    setPanY((py) => clamp(py, -y, y));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [zoomEff, layout]);

  // Scroll-wheel zoom. React's ``onWheel`` handlers are passive by
  // default, so ``preventDefault()`` there doesn't stop page scroll.
  // Attach a native ``wheel`` listener with ``{ passive: false }``
  // instead. Zoom is cursor-anchored — the source pixel under the
  // cursor stays under the cursor across the zoom change — for
  // natural "zoom into what I'm looking at" behaviour.
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const handler = (e: WheelEvent) => {
      const l = layoutRef.current;
      if (!l) return;
      e.preventDefault();
      const rect = container.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;

      const zOld = zoomRef.current;
      const vcx = l.view_center_pixel_x;
      const vcy = l.view_center_pixel_y;
      const panXOld = panXRef.current;
      const panYOld = panYRef.current;

      // Source pixel under the cursor pre-zoom.
      const sourceX = (mx - size / 2 + vcx * zOld - panXOld) / zOld;
      const sourceY = (my - size / 2 + vcy * zOld - panYOld) / zOld;

      // Each wheel notch changes zoom by ~10%. ``deltaMode`` 1 = lines,
      // 2 = pages — scale accordingly so line-mode mice (Firefox on
      // Windows) feel similar to pixel-mode.
      const lineScale = e.deltaMode === 1 ? 40 : e.deltaMode === 2 ? 400 : 1;
      const scroll = e.deltaY * lineScale;
      const factor = Math.exp(-scroll * 0.0015);
      const zNew = Math.max(zoomFit, Math.min(zoomMax, zOld * factor));
      if (zNew === zOld) return;

      // Solve for the new pan that keeps ``sourceX / sourceY`` under
      // the cursor after the zoom change.
      let panXNew = mx - size / 2 + vcx * zNew - sourceX * zNew;
      let panYNew = my - size / 2 + vcy * zNew - sourceY * zNew;
      const limX = Math.max(
        0,
        Math.max(vcx, l.composite_width_px - vcx) * zNew,
      );
      const limY = Math.max(
        0,
        Math.max(vcy, l.composite_height_px - vcy) * zNew,
      );
      panXNew = clamp(panXNew, -limX, limX);
      panYNew = clamp(panYNew, -limY, limY);

      // Fast path via refs + applyLive so the pan/zoom updates on the
      // same frame as the wheel event. State catches up for React.
      zoomRef.current = zNew;
      panXRef.current = panXNew;
      panYRef.current = panYNew;
      applyLive();

      setZoom(zNew);
      setPanX(panXNew);
      setPanY(panYNew);
    };

    container.addEventListener("wheel", handler, { passive: false });
    return () => container.removeEventListener("wheel", handler);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [size, zoomFit, zoomMax]);

  useEffect(() => {
    const onDown = (e: KeyboardEvent) => {
      if (e.key === "Shift") setIsShiftHeld(true);
    };
    const onUp = (e: KeyboardEvent) => {
      if (e.key === "Shift") setIsShiftHeld(false);
    };
    window.addEventListener("keydown", onDown);
    window.addEventListener("keyup", onUp);
    return () => {
      window.removeEventListener("keydown", onDown);
      window.removeEventListener("keyup", onUp);
    };
  }, []);

  useEffect(() => {
    function onMove(e: PointerEvent) {
      const drag = dragStateRef.current;
      if (!drag || drag.pointerId !== e.pointerId) return;
      const container = containerRef.current;
      if (!container) return;
      e.preventDefault();
      const dx = e.clientX - drag.lastX;
      const dy = e.clientY - drag.lastY;

      if (drag.mode === "rect") {
        if (e.shiftKey) {
          const r = container.getBoundingClientRect();
          const cx = r.left + r.width / 2;
          const cy = r.top + r.height / 2;
          const prev = angleFromCenter(drag.lastX, drag.lastY, cx, cy);
          const next = angleFromCenter(e.clientX, e.clientY, cx, cy);
          rotationRef.current = normalizeAngle(
            rotationRef.current - (next - prev),
          );
        } else {
          // Drag in screen CSS px; rect offset is in composite source
          // pixels, so divide by zoom.
          const z = zoomRef.current || 1;
          rectOffsetXRef.current += dx / z;
          rectOffsetYRef.current += dy / z;
        }
      } else {
        const { x: xLim, y: yLim } = currentPanLimit();
        panXRef.current = clamp(panXRef.current + dx, -xLim, xLim);
        panYRef.current = clamp(panYRef.current + dy, -yLim, yLim);
      }
      drag.lastX = e.clientX;
      drag.lastY = e.clientY;
      applyLive();
    }
    function onEnd(e: PointerEvent) {
      const drag = dragStateRef.current;
      if (!drag || drag.pointerId !== e.pointerId) return;
      dragStateRef.current = null;
      setRotation(rotationRef.current);
      setRectOffsetX(rectOffsetXRef.current);
      setRectOffsetY(rectOffsetYRef.current);
      setPanX(panXRef.current);
      setPanY(panYRef.current);
    }
    window.addEventListener("pointermove", onMove, { passive: false });
    window.addEventListener("pointerup", onEnd);
    window.addEventListener("pointercancel", onEnd);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onEnd);
      window.removeEventListener("pointercancel", onEnd);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [size, sourcePxPerDeg, centerRaDeg, centerDecDeg]);

  function tryCapture(pointerId: number) {
    try {
      containerRef.current?.setPointerCapture(pointerId);
    } catch {
      // Synthetic events can't be captured; window listeners still work.
    }
  }

  // A focusable ``<div>`` doesn't pick up keyboard focus on click —
  // only on Tab. Pulling focus on every pointer-down means the user's
  // first interaction (drag-to-rotate, pan, annotation click) also
  // arms the keyboard controls (arrow keys, R) without a separate
  // Tab-to-focus step.
  function focusContainer(): void {
    containerRef.current?.focus({ preventScroll: true });
  }

  function handleRectPointerDown(e: React.PointerEvent<HTMLDivElement>) {
    e.preventDefault();
    e.stopPropagation();
    tryCapture(e.pointerId);
    focusContainer();
    dragStateRef.current = {
      pointerId: e.pointerId,
      mode: "rect",
      lastX: e.clientX,
      lastY: e.clientY,
    };
  }

  function handleContainerPointerDown(e: React.PointerEvent<HTMLDivElement>) {
    if (centerRaDeg == null || centerDecDeg == null) return;
    e.preventDefault();
    tryCapture(e.pointerId);
    focusContainer();
    dragStateRef.current = {
      pointerId: e.pointerId,
      mode: "pan",
      lastX: e.clientX,
      lastY: e.clientY,
    };
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    // Arrow keys pan the background mosaic (conventional — matches
    // Stellarium / PixInsight / image-editor muscle memory).
    // Shift+Arrow rotates the sensor rectangle ±5° per tap.
    // Pan step: 40 px in the composite's source-pixel space per tap.
    const PAN_STEP = 40;
    const ROT_STEP = 5;
    const { x: xLim, y: yLim } = currentPanLimit();

    if (e.key === "ArrowLeft") {
      e.preventDefault();
      if (e.shiftKey) {
        setRotation((r) => normalizeAngle(r - ROT_STEP));
      } else {
        setPanX((px) => clamp(px + PAN_STEP, -xLim, xLim));
      }
    } else if (e.key === "ArrowRight") {
      e.preventDefault();
      if (e.shiftKey) {
        setRotation((r) => normalizeAngle(r + ROT_STEP));
      } else {
        setPanX((px) => clamp(px - PAN_STEP, -xLim, xLim));
      }
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (e.shiftKey) {
        setRotation((r) => normalizeAngle(r + ROT_STEP));
      } else {
        setPanY((py) => clamp(py + PAN_STEP, -yLim, yLim));
      }
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      if (e.shiftKey) {
        setRotation((r) => normalizeAngle(r - ROT_STEP));
      } else {
        setPanY((py) => clamp(py - PAN_STEP, -yLim, yLim));
      }
    } else if (e.key === "r" || e.key === "R") {
      e.preventDefault();
      recenterView();
    } else if (e.key === "Escape") {
      (e.currentTarget as HTMLElement).blur();
    }
  }

  function recenterView() {
    // Re-centres the DSO and resets the rig rectangle to the frame
    // centre. Leaves zoom + rotation alone — those have their own
    // dedicated reset controls in the sidebar, and users often want
    // to recentre an image without losing the zoom they've dialled in.
    setRectOffsetX(0);
    setRectOffsetY(0);
    setPanX(0);
    setPanY(0);
  }
  function resetRotation() {
    setRotation(0);
  }

  const rectangleCursor = isShiftHeld ? ROTATE_CURSOR : "grab";
  const showCoords = centerRaDeg != null && centerDecDeg != null;

  const initialRectSky = useMemo(() => {
    if (!showCoords || sourcePxPerDeg === 0) return null;
    const { dRaDeg, dDecDeg } = offsetPxToSkyDelta(
      rectOffsetX,
      rectOffsetY,
      sourcePxPerDeg,
      centerDecDeg!,
    );
    return {
      raDeg: wrapRa(centerRaDeg! + dRaDeg),
      decDeg: clampDec(centerDecDeg! + dDecDeg),
    };
  }, [showCoords, rectOffsetX, rectOffsetY, sourcePxPerDeg, centerRaDeg, centerDecDeg]);

  const deltaEastDeg = sourcePxPerDeg > 0 ? -rectOffsetX / sourcePxPerDeg : 0;
  const deltaNorthDeg = sourcePxPerDeg > 0 ? -rectOffsetY / sourcePxPerDeg : 0;

  // Annotations — fetch a region around the DSO spanning the view.
  // Same endpoint the v0.17.0 path uses; only the overlay's projection
  // changes.
  const nearbyQuery = useQuery({
    queryKey: ["nearby-dsos", dsoId, extentDeg.toFixed(4)],
    queryFn: () =>
      fetchNearbyDsos({
        raCenterDeg: centerRaDeg!,
        decCenterDeg: centerDecDeg!,
        extentDeg,
        excludeId: dsoId,
      }),
    enabled: showCoords,
    staleTime: 60_000,
  });
  const nearbyItems = nearbyQuery.data?.items ?? [];

  const sliderMaxArcmin = useMemo(() => {
    let max = 0;
    for (const it of nearbyItems) {
      if (it.maj_axis_arcmin != null && it.maj_axis_arcmin > max) {
        max = it.maj_axis_arcmin;
      }
    }
    if (dsoMajAxisArcmin != null && dsoMajAxisArcmin > max) max = dsoMajAxisArcmin;
    return Math.max(1, max);
  }, [nearbyItems, dsoMajAxisArcmin]);
  const thresholdArcmin = sliderToArcmin(annotationSlider, sliderMaxArcmin);
  const anyHasSize =
    nearbyItems.some((i) => i.maj_axis_arcmin != null) || dsoMajAxisArcmin != null;

  return (
    <>
      <Stack
        direction={{ xs: "column", md: "row" }}
        gap={2}
        alignItems={{ md: "flex-start" }}
      >
        <Box
          ref={containerRef}
          tabIndex={0}
          onKeyDown={handleKeyDown}
          onPointerDown={handleContainerPointerDown}
          sx={{
            position: "relative",
            width: "100%",
            maxWidth: size,
            aspectRatio: "1 / 1",
            border: 1,
            borderColor: "divider",
            borderRadius: 1,
            overflow: "hidden",
            outline: "none",
            flexShrink: 0,
            touchAction: "none",
            userSelect: "none",
            cursor: showCoords ? "grab" : "default",
            "&:active": { cursor: showCoords ? "grabbing" : "default" },
            "&:focus": {
              boxShadow: (t) => `0 0 0 2px ${t.palette.primary.main}`,
            },
          }}
        >
          {/* Pan group — composite source-pixel dimensions, transformed
              by pan/zoom to fit the viewport. */}
          <Box
            ref={panGroupRef}
            style={{
              transform: panGroupTransformFromState(panX, panY, zoomEff, layout),
              transformOrigin: "0 0",
            }}
            sx={{
              position: "absolute",
              top: 0,
              left: 0,
              width: layout?.composite_width_px ?? 0,
              height: layout?.composite_height_px ?? 0,
            }}
          >
            {showCoords && (
              <SkyTileComposite
                raDeg={centerRaDeg!}
                decDeg={centerDecDeg!}
                tier={tier}
                extentDeg={extentDeg}
                onLayout={setLayout}
                rigMajorDeg={fovMajorDeg}
                rigMinorDeg={fovMinorDeg}
              />
            )}

            {/* Rig rectangle — anchored at the composite's view centre,
                offset by rectOffsetX/Y in source pixels. Painted
                BEFORE annotations so annotation circles/labels land on
                top. The annotation overlay's SVG root has
                ``pointer-events: none``, so clicks on empty space
                pass through to the rect beneath; only the
                annotation's own ``<g>`` elements intercept clicks —
                exactly the "click the object, not the pan" behaviour
                users expect. */}
            {layout && (
              <Box
                ref={rectRef}
                onPointerDown={handleRectPointerDown}
                style={{
                  transform: buildRectTransform(rectOffsetX, rectOffsetY, rotation),
                  transformOrigin: "center center",
                }}
                sx={{
                  position: "absolute",
                  top: layout.view_center_pixel_y,
                  left: layout.view_center_pixel_x,
                  width: rectWidth,
                  height: rectHeight,
                  border: `2px solid ${RIG_ORANGE}`,
                  boxSizing: "border-box",
                  cursor: rectangleCursor,
                  touchAction: "none",
                  "&:active": {
                    cursor: isShiftHeld ? ROTATE_CURSOR : "grabbing",
                  },
                }}
              >
                {(["tl", "tr", "bl", "br"] as const).map((corner) => {
                  const style: React.CSSProperties = {
                    position: "absolute",
                    width: 8,
                    height: 8,
                    borderColor: RIG_ORANGE,
                    borderStyle: "solid",
                    borderWidth: 0,
                    pointerEvents: "none",
                  };
                  if (corner === "tl") {
                    style.top = -1;
                    style.left = -1;
                    style.borderTopWidth = 3;
                    style.borderLeftWidth = 3;
                  } else if (corner === "tr") {
                    style.top = -1;
                    style.right = -1;
                    style.borderTopWidth = 3;
                    style.borderRightWidth = 3;
                  } else if (corner === "bl") {
                    style.bottom = -1;
                    style.left = -1;
                    style.borderBottomWidth = 3;
                    style.borderLeftWidth = 3;
                  } else {
                    style.bottom = -1;
                    style.right = -1;
                    style.borderBottomWidth = 3;
                    style.borderRightWidth = 3;
                  }
                  return <div key={corner} style={style} />;
                })}

                <Box
                  sx={{
                    position: "absolute",
                    top: "50%",
                    left: "50%",
                    width: 6,
                    height: 6,
                    borderRadius: "50%",
                    bgcolor: RIG_ORANGE,
                    transform: "translate(-50%, -50%)",
                    boxShadow: "0 0 3px rgba(0,0,0,0.7)",
                    pointerEvents: "none",
                  }}
                />
              </Box>
            )}

            {showAnnotations && showCoords && layout && (
              <DsoAnnotationOverlay
                items={nearbyItems}
                primary={{
                  id: dsoId,
                  primary_designation: primaryDesignation ?? "",
                  ra_deg: centerRaDeg!,
                  dec_deg: centerDecDeg!,
                  maj_axis_arcmin: dsoMajAxisArcmin ?? null,
                }}
                tangentRaDeg={layout.tangent_ra_deg}
                tangentDecDeg={layout.tangent_dec_deg}
                cellSizeDeg={layout.cell_size_deg}
                cellPxSize={layout.cell_width_px}
                compositePxWidth={layout.composite_width_px}
                compositePxHeight={layout.composite_height_px}
                viewCenterPxX={layout.view_center_pixel_x}
                viewCenterPxY={layout.view_center_pixel_y}
                thresholdArcmin={thresholdArcmin}
                zoom={zoomEff}
                onAnnotationClick={(item, anchor) =>
                  setPopover({ item, anchor })
                }
              />
            )}
          </Box>

          {/* North indicator — fixed in the viewport. */}
          <Box
            sx={{
              position: "absolute",
              top: 6,
              left: 8,
              color: "#ffffff",
              fontSize: 12,
              fontWeight: 600,
              textShadow: "0 0 4px rgba(0,0,0,0.8)",
              pointerEvents: "none",
            }}
          >
            N ↑
          </Box>
        </Box>

        {/* Sidebar */}
        <Box sx={{ flex: 1, minWidth: 200, display: "flex", flexDirection: "column", gap: 2 }}>
          {showCoords && (
            <>
              <Box>
                <Stack direction="row" alignItems="center" gap={0.5}>
                  <Typography
                    variant="caption"
                    color="text.secondary"
                    sx={{ textTransform: "uppercase", letterSpacing: 0.5, fontSize: "0.65rem", flex: 1 }}
                  >
                    Object (J2000)
                  </Typography>
                  <Tooltip title="Re-center the view on the object (keeps zoom + rotation)">
                    <IconButton size="small" onClick={recenterView} aria-label="Re-center view">
                      <RestartAltIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </Stack>
                <Stack direction="column" gap={0.25} sx={{ mt: 0.25 }}>
                  <Typography variant="body2" sx={{ fontFamily: "monospace" }}>
                    <Box component="span" sx={{ color: "text.secondary", mr: 1 }}>RA</Box>
                    {formatRa(centerRaDeg!)}
                  </Typography>
                  <Typography variant="body2" sx={{ fontFamily: "monospace" }}>
                    <Box component="span" sx={{ color: "text.secondary", mr: 1 }}>Dec</Box>
                    {formatDec(centerDecDeg!)}
                  </Typography>
                </Stack>
              </Box>

              <Box>
                <Typography
                  variant="caption"
                  color="text.secondary"
                  sx={{ textTransform: "uppercase", letterSpacing: 0.5, fontSize: "0.65rem" }}
                >
                  Frame center (J2000)
                </Typography>
                <Tooltip
                  placement="right"
                  title={
                    <Box sx={{ lineHeight: 1.4 }}>
                      <Box sx={{ opacity: 0.8, fontSize: "0.7rem" }}>Offset from object</Box>
                      <Box sx={{ fontFamily: "monospace" }}>{formatDelta(deltaEastDeg, "E", "W")}</Box>
                      <Box sx={{ fontFamily: "monospace" }}>{formatDelta(deltaNorthDeg, "N", "S")}</Box>
                    </Box>
                  }
                >
                  <Stack direction="column" gap={0.25} sx={{ mt: 0.25, cursor: "help" }}>
                    <Typography variant="body2" sx={{ fontFamily: "monospace" }}>
                      <Box component="span" sx={{ color: "text.secondary", mr: 1 }}>RA</Box>
                      <Box component="span" ref={raDisplayRef}>
                        {initialRectSky ? formatRa(initialRectSky.raDeg) : "—"}
                      </Box>
                    </Typography>
                    <Typography variant="body2" sx={{ fontFamily: "monospace" }}>
                      <Box component="span" sx={{ color: "text.secondary", mr: 1 }}>Dec</Box>
                      <Box component="span" ref={decDisplayRef}>
                        {initialRectSky ? formatDec(initialRectSky.decDeg) : "—"}
                      </Box>
                    </Typography>
                  </Stack>
                </Tooltip>
              </Box>
            </>
          )}

          {showCoords && layout && (
            <Box>
              <Stack direction="row" alignItems="center" gap={0.5}>
                <Typography
                  variant="caption"
                  color="text.secondary"
                  sx={{ textTransform: "uppercase", letterSpacing: 0.5, fontSize: "0.65rem", flex: 1 }}
                >
                  Zoom
                </Typography>
                <Tooltip title="Reset zoom">
                  <IconButton size="small" onClick={() => setZoom(zoomDefault)} aria-label="Reset zoom">
                    <RestartAltIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
              </Stack>
              <Stack direction="row" alignItems="center" gap={1} sx={{ mt: 0.5 }}>
                <Typography variant="caption" color="text.secondary" sx={{ minWidth: 56 }}>
                  {((zoomEff / zoomDefault) * 100).toFixed(0)}%
                </Typography>
                <Slider
                  size="small"
                  value={zoomEff}
                  min={zoomFit}
                  max={zoomMax}
                  step={(zoomMax - zoomFit) / 100 || 0.01}
                  onChange={(_, v) => {
                    const next = Array.isArray(v) ? v[0] : v;
                    setZoom(Math.max(zoomFit, Math.min(zoomMax, next)));
                  }}
                />
              </Stack>
              <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
                {tier} tier · {layout.cells.length} cells · region {layout.ipix}
              </Typography>
            </Box>
          )}

          <Box>
            <Stack direction="row" alignItems="center" gap={0.5}>
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ textTransform: "uppercase", letterSpacing: 0.5, fontSize: "0.65rem", flex: 1 }}
              >
                Rotation
              </Typography>
              <Tooltip title="Reset rotation">
                <IconButton size="small" onClick={resetRotation} aria-label="Reset rotation">
                  <RestartAltIcon fontSize="small" />
                </IconButton>
              </Tooltip>
            </Stack>
            <Tooltip
              placement="left"
              title={
                "Rotation is the Position Angle — measured from sky north, " +
                "going east. Matches NINA, Telescopius, and PixInsight, so " +
                "framing plans transfer directly."
              }
            >
              <Typography
                variant="body2"
                sx={{ mt: 0.25, fontFamily: "monospace", cursor: "help", width: "fit-content" }}
              >
                <Box component="span" ref={rotationDisplayRef}>
                  {Math.round(rotation)}
                  {"\u00B0"}
                </Box>
              </Typography>
            </Tooltip>
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.25 }}>
              position angle (east of north)
            </Typography>
          </Box>

          {showCoords && (
            <Box>
              <Stack direction="row" alignItems="center" gap={0.5}>
                <Typography
                  variant="caption"
                  color="text.secondary"
                  sx={{ textTransform: "uppercase", letterSpacing: 0.5, fontSize: "0.65rem", flex: 1 }}
                >
                  Annotations
                </Typography>
                <Tooltip title={showAnnotations ? "Hide annotations" : "Show annotations"}>
                  <IconButton
                    size="small"
                    onClick={() => setShowAnnotations((v) => !v)}
                    aria-label="Toggle annotations"
                  >
                    {showAnnotations ? (
                      <VisibilityIcon fontSize="small" />
                    ) : (
                      <VisibilityOffIcon fontSize="small" />
                    )}
                  </IconButton>
                </Tooltip>
              </Stack>
              {showAnnotations && (
                <>
                  <Stack direction="row" alignItems="center" gap={1} sx={{ mt: 0.5 }}>
                    <Typography variant="caption" color="text.secondary" sx={{ minWidth: 90 }}>
                      Min: {thresholdArcmin.toFixed(1)}
                      {"\u2032"}
                    </Typography>
                    <Tooltip
                      title={
                        anyHasSize
                          ? ""
                          : "No in-frame objects have size data — slider is disabled."
                      }
                      placement="top"
                      disableHoverListener={anyHasSize}
                    >
                      <Box sx={{ flex: 1, display: "flex", alignItems: "center" }}>
                        <Slider
                          size="small"
                          value={annotationSlider}
                          min={0}
                          max={1}
                          step={0.001}
                          disabled={!anyHasSize}
                          onChange={(_, v) => {
                            const raw = Array.isArray(v) ? v[0] : v;
                            const target = sliderToArcmin(raw, sliderMaxArcmin);
                            const snapped = Math.round(target * 10) / 10;
                            setAnnotationSlider(arcminToSlider(snapped, sliderMaxArcmin));
                          }}
                        />
                      </Box>
                    </Tooltip>
                  </Stack>
                  <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
                    up to {sliderMaxArcmin.toFixed(0)}
                    {"\u2032"}
                  </Typography>
                </>
              )}
            </Box>
          )}

          <Box>
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ textTransform: "uppercase", letterSpacing: 0.5, fontSize: "0.65rem" }}
            >
              How to use
            </Typography>
            <Box component="ul" sx={{ pl: 2.5, mt: 0.5, mb: 0, "& li": { mb: 0.25 } }}>
              <Typography component="li" variant="caption" color="text.secondary">
                <b>Drag the image</b> to pan
              </Typography>
              <Typography component="li" variant="caption" color="text.secondary">
                <b>Drag the rectangle</b> to move the frame
              </Typography>
              <Typography component="li" variant="caption" color="text.secondary">
                <b>Shift + drag rectangle</b> to rotate
              </Typography>
              <Typography component="li" variant="caption" color="text.secondary">
                Arrow keys rotate ±5° (Shift ±1°) — focus the image
              </Typography>
              <Typography component="li" variant="caption" color="text.secondary">
                <b>R</b> re-centers the view (zoom + rotation untouched)
              </Typography>
              <Typography component="li" variant="caption" color="text.secondary">
                <b>Scroll wheel</b> zooms toward the cursor
              </Typography>
            </Box>
          </Box>
        </Box>
      </Stack>

      <DsoAnnotationPopover
        anchorEl={popover?.anchor ?? null}
        dsoId={popover?.item.id ?? null}
        fallbackDesignation={popover?.item.primary_designation ?? ""}
        fallbackObjType={popover?.item.obj_type ?? null}
        onClose={() => setPopover(null)}
        onSelectDso={(id) => {
          if (onSelectDso) onSelectDso(id);
        }}
      />
    </>
  );
}

// Empty state — rendered when no rig is selected.
export function FovSimulatorEmpty() {
  return (
    <Box
      sx={{
        width: "100%",
        aspectRatio: "1 / 1",
        maxWidth: 520,
        mx: "auto",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        border: 1,
        borderColor: "divider",
        borderRadius: 1,
        color: "text.secondary",
        textAlign: "center",
        p: 2,
      }}
    >
      <Box>
        <Typography variant="body2">Select a rig to preview framing</Typography>
        <Button size="small" sx={{ mt: 1 }} disabled>
          (no rig selected)
        </Button>
      </Box>
    </Box>
  );
}
