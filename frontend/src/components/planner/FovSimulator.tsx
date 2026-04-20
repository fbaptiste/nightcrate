/**
 * FOV Simulator — 3×3 grid of DSS2 tiles around the object, with a
 * rotatable + movable sensor frame and sky-anchored DSO annotations.
 *
 * Layout:
 *   ┌─────┬─────┬─────┐
 *   │ NE  │  N  │ NW  │   (9 tiles, each the same angular extent)
 *   ├─────┼─────┼─────┤
 *   │  E  │center│  W │   ← viewport clips to one tile around centre
 *   ├─────┼─────┼─────┤
 *   │ SE  │  S  │ SW  │
 *   └─────┴─────┴─────┘
 *
 * The user can pan within the grid — pan offset clamped to ±1 tile
 * width, so they can slide neighbouring tiles into view without ever
 * hitting a refetch or a black edge. The centre tile loads first; the
 * 8 neighbours preload in the background and snap into place when
 * each one lands.
 *
 * Interactions:
 *   - Drag the image: pan the sky (bounded by the grid).
 *   - Drag the rectangle: move the sensor frame over the sky.
 *   - Shift + drag the rectangle: rotate (Position Angle, east of north).
 *   - Arrow keys: rotate ±5°, Shift ±1°.
 *   - R: reset everything.
 *   - Click an annotation label: popover with info + "Show details".
 *
 * Drag path bypasses React: pointermove writes ``el.style.transform``
 * directly against refs, and readout text nodes are updated via
 * textContent — no re-render per mouse frame. State catches up on
 * pointerup.
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
import {
  arcminToSlider,
  sliderToArcmin,
  tileCenterAt,
} from "@/lib/dsoAnnotations";
import { fetchNearbyDsos, type NearbyDsoItem } from "@/api/planner";
import ThumbnailCell from "./ThumbnailCell";
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
  /** CSS pixel size of the **viewport** (one tile's worth). The total
   *  pan group that holds the 3×3 grid is 3× this in each dimension. */
  size?: number;
}

// Mirror of backend ``compute_angular_extent_deg`` for the simulator
// variant. Must stay in lockstep — the annotation / rectangle
// projection math all flows from this.
function tileExtentDeg(fovMajor: number, fovMinor: number): number {
  // Sensor rectangle fills 50% of the tile's max dimension.
  return Math.max(fovMajor, fovMinor) / 0.5;
}

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
  // +offsetX (screen right) = sky west of centre = -RA.
  // +offsetY (screen down) = sky south of centre = -Dec.
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

// Build the list of tile centres for an N×N grid. ``half`` = (N−1)/2,
// so a 3×3 grid gets (col, row) ∈ {−1, 0, +1}² and a 5×5 grid gets
// {−2, … +2}². col is the screen column (−1 = left, +1 = right); row
// is the screen row (−1 = top, +1 = bottom). Sky: east is left, north
// is up, so col=−1 is higher RA (east) and row=−1 is higher Dec.
function computeTiles(
  objectRaDeg: number,
  objectDecDeg: number,
  tileExtent: number,
  half: number,
): Array<{ col: number; row: number; raDeg: number; decDeg: number }> {
  const out: Array<{ col: number; row: number; raDeg: number; decDeg: number }> = [];
  for (let row = -half; row <= half; row++) {
    for (let col = -half; col <= half; col++) {
      const { raDeg, decDeg } = tileCenterAt(
        objectRaDeg,
        objectDecDeg,
        col,
        row,
        tileExtent,
      );
      out.push({ col, row, raDeg: wrapRa(raDeg), decDeg: clampDec(decDeg) });
    }
  }
  return out;
}

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
  const [zoom, setZoom] = useState(1);
  // Load phases: 1 = centre tile only, 3 = 3×3 inner grid, 5 = 5×5
  // with outer ring. Starting at 1 ensures the backend's 4-slot HiPS
  // fetch semaphore is fully dedicated to the centre tile on first
  // open — users see the image ~4× faster than if all 9 tiles raced
  // for the queue. The ring fills in as soon as the centre lands.
  const [gridN, setGridN] = useState<1 | 3 | 5>(1);
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
  // Mirrors of gridN + zoom so the window pointermove listener can
  // read the current values without re-binding on every state change.
  // Without these, the listener's closure would see the values from
  // the render in which the listener was attached — and when the
  // 5×5 outer-ring promotion fires ``setGridN(5)`` the listener would
  // keep writing the OLD ``gridPx`` transform to the pan group, jumping
  // the image under the user's cursor mid-drag.
  const gridNRef = useRef<1 | 3 | 5>(1);
  const zoomRef = useRef(1);
  // Drag state — ``mode`` disambiguates pan (container) vs rect.
  const dragStateRef = useRef<
    | {
        pointerId: number;
        mode: "pan" | "rect";
        lastX: number;
        lastY: number;
      }
    | null
  >(null);

  const extentDeg = useMemo(
    () => tileExtentDeg(fovMajorDeg, fovMinorDeg),
    [fovMajorDeg, fovMinorDeg],
  );
  // pixels per sky-degree in the pan group's unscaled coordinate
  // system. Tiles don't physically scale until the pan-group
  // ``scale()`` transform applies.
  const pxPerDeg = size / extentDeg;
  const rectWidth = fovMajorDeg * pxPerDeg;
  const rectHeight = fovMinorDeg * pxPerDeg;

  // Grid geometry. ``half`` is how many tiles live on each side of
  // the centre tile; ``gridPx`` is the pan-group's unscaled pixel
  // size. Both update when the 5×5 ring finishes preloading.
  const half = (gridN - 1) / 2;
  const gridPx = size * gridN;
  // Zoom bounds: zoom=1 shows one tile; zoom=1/gridN shows the full
  // grid. Always keep the user inside that range.
  const zoomMin = 1 / gridN;
  // Max screen-pixel pan at the current zoom. At zoom = 1/gridN the
  // scaled grid exactly fills the viewport so pan is 0.
  const panLimit = Math.max(0, (gridPx * zoom - size) / 2);

  const tiles = useMemo(() => {
    if (centerRaDeg == null || centerDecDeg == null) return [];
    return computeTiles(centerRaDeg, centerDecDeg, extentDeg, half);
  }, [centerRaDeg, centerDecDeg, extentDeg, half]);

  // Build the pan-group transform from the *current* refs. Scale is
  // applied first, then translate — so to pin the grid's centre to
  // the viewport centre at any zoom we shift by
  // ``size/2 − gridPx/2 × zoom``. Pan adds on top.
  function gridTransformFromRefs(): string {
    const z = zoomRef.current;
    const curGridPx = size * gridNRef.current;
    const baseT = size * 0.5 - curGridPx * 0.5 * z;
    return `translate(${baseT + panXRef.current}px, ${baseT + panYRef.current}px) scale(${z})`;
  }

  // The same transform derived from React props/state — used to seed
  // the DOM at render time (before applyLive has run post-commit).
  function gridTransformFromState(
    panXv: number,
    panYv: number,
    zoomV: number,
    gridNv: 1 | 3 | 5,
  ): string {
    const curGridPx = size * gridNv;
    const baseT = size * 0.5 - curGridPx * 0.5 * zoomV;
    return `translate(${baseT + panXv}px, ${baseT + panYv}px) scale(${zoomV})`;
  }

  // Current clamp limit for pan, computed fresh from the refs.
  function currentPanLimit(): number {
    return Math.max(
      0,
      (size * gridNRef.current * zoomRef.current - size) / 2,
    );
  }

  // DOM-direct write helper: rect transform + pan transform + readouts.
  // Reads all "live" values from refs so it never sees a stale value
  // captured at window-listener-bind time.
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
      pg.style.transform = gridTransformFromRefs();
    }
    const rotEl = rotationDisplayRef.current;
    if (rotEl) rotEl.textContent = `${Math.round(rotationRef.current)}\u00B0`;
    if (centerRaDeg != null && centerDecDeg != null) {
      const { dRaDeg, dDecDeg } = offsetPxToSkyDelta(
        rectOffsetXRef.current,
        rectOffsetYRef.current,
        pxPerDeg,
        centerDecDeg,
      );
      const rectRa = wrapRa(centerRaDeg + dRaDeg);
      const rectDec = clampDec(centerDecDeg + dDecDeg);
      if (raDisplayRef.current) raDisplayRef.current.textContent = formatRa(rectRa);
      if (decDisplayRef.current) decDisplayRef.current.textContent = formatDec(rectDec);
    }
  }

  // useLayoutEffect (not useEffect) so ``applyLive`` writes the refs-
  // driven transform BEFORE the browser paints. If the 5×5 grid
  // promotion fires mid-drag, React commits a new inline transform on
  // the pan group that corresponds to ``panX`` state (which is stale
  // — state commits on pointerup). Without this synchronous catch-up,
  // the user would see a single frame where the image snaps back to
  // the object-centred view before pan resumes on the next
  // pointermove. Running synchronously closes that window.
  useLayoutEffect(() => {
    rotationRef.current = rotation;
    rectOffsetXRef.current = rectOffsetX;
    rectOffsetYRef.current = rectOffsetY;
    panXRef.current = panX;
    panYRef.current = panY;
    gridNRef.current = gridN;
    zoomRef.current = zoom;
    applyLive();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    rotation,
    rectOffsetX,
    rectOffsetY,
    panX,
    panY,
    gridN,
    zoom,
    centerRaDeg,
    centerDecDeg,
    pxPerDeg,
    size,
  ]);

  // Stage 1 → Stage 3 happens on the centre tile's ``onReady``
  // callback (see the tile render below), so there's no timer here.
  // Stage 3 → Stage 5 promotion: once the inner 3×3 has had a beat
  // to paint, mount the outer 16 tiles. By the time the user zooms
  // out or pans far enough to see them, most are usually loaded.
  useEffect(() => {
    if (gridN !== 3) return;
    if (centerRaDeg == null || centerDecDeg == null) return;
    const timer = setTimeout(() => setGridN(5), 2000);
    return () => clearTimeout(timer);
  }, [gridN, centerRaDeg, centerDecDeg]);

  // Re-clamp pan when zoom or grid size changes (the limit shrinks
  // or grows). Without this, shrinking the limit could leave pan in
  // an out-of-bounds state.
  useEffect(() => {
    setPanX((x) => clamp(x, -panLimit, panLimit));
    setPanY((y) => clamp(y, -panLimit, panLimit));
  }, [panLimit]);

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
          // Screen-space drag converted to pan-group-space — the pan
          // group is scaled by ``zoom`` so a ``dx`` of 20 screen px
          // is ``20 / zoom`` in the unscaled rect-offset coordinates.
          // Reads zoom from the ref so the listener doesn't see stale
          // values if the user changed zoom since it was bound.
          const z = zoomRef.current;
          rectOffsetXRef.current += dx / z;
          rectOffsetYRef.current += dy / z;
        }
      } else {
        // Pan mode. ``currentPanLimit`` derives from the live refs,
        // so a gridN / zoom change mid-drag immediately uses the new
        // bounds — no stale clamp window stuck on the pre-change grid.
        const lim = currentPanLimit();
        panXRef.current = clamp(panXRef.current + dx, -lim, lim);
        panYRef.current = clamp(panYRef.current + dy, -lim, lim);
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
    // Re-bind on target/rig change so ``applyLive`` captures the new
    // ``centerRaDeg`` / ``pxPerDeg`` / ``size`` closure. ``gridN`` and
    // ``zoom`` intentionally stay *out* of the dep list — they're read
    // via refs inside the handler, avoiding a listener teardown
    // mid-drag when the 5×5 ring promotes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [size, pxPerDeg, centerRaDeg, centerDecDeg]);

  function tryCapture(pointerId: number) {
    try {
      containerRef.current?.setPointerCapture(pointerId);
    } catch {
      // Synthetic events can't be captured; window listeners still work.
    }
  }

  function handleRectPointerDown(e: React.PointerEvent<HTMLDivElement>) {
    e.preventDefault();
    e.stopPropagation(); // don't also start a pan
    tryCapture(e.pointerId);
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
    dragStateRef.current = {
      pointerId: e.pointerId,
      mode: "pan",
      lastX: e.clientX,
      lastY: e.clientY,
    };
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    const step = e.shiftKey ? 1 : 5;
    if (e.key === "ArrowRight" || e.key === "ArrowUp") {
      e.preventDefault();
      setRotation((r) => normalizeAngle(r + step));
    } else if (e.key === "ArrowLeft" || e.key === "ArrowDown") {
      e.preventDefault();
      setRotation((r) => normalizeAngle(r - step));
    } else if (e.key === "r" || e.key === "R") {
      e.preventDefault();
      resetAll();
    } else if (e.key === "Escape") {
      (e.currentTarget as HTMLElement).blur();
    }
  }

  function resetAll() {
    setRotation(0);
    setRectOffsetX(0);
    setRectOffsetY(0);
    setPanX(0);
    setPanY(0);
    setZoom(1);
  }
  function resetRotation() {
    setRotation(0);
  }

  const rectangleCursor = isShiftHeld ? ROTATE_CURSOR : "grab";
  const showCoords = centerRaDeg != null && centerDecDeg != null;

  const initialRectSky = useMemo(() => {
    if (!showCoords) return null;
    const { dRaDeg, dDecDeg } = offsetPxToSkyDelta(
      rectOffsetX,
      rectOffsetY,
      pxPerDeg,
      centerDecDeg!,
    );
    return {
      raDeg: wrapRa(centerRaDeg! + dRaDeg),
      decDeg: clampDec(centerDecDeg! + dDecDeg),
    };
  }, [showCoords, rectOffsetX, rectOffsetY, pxPerDeg, centerRaDeg, centerDecDeg]);

  const deltaEastDeg = showCoords ? -rectOffsetX / pxPerDeg : 0;
  const deltaNorthDeg = showCoords ? -rectOffsetY / pxPerDeg : 0;

  // Annotations — region query keyed on DSO + tile extent. The region
  // we fetch covers the full 5×5 grid up-front so the outer ring
  // already has labels by the time tiles load.
  const annotationExtentDeg = extentDeg * 5;
  const nearbyQuery = useQuery({
    queryKey: ["nearby-dsos", dsoId, annotationExtentDeg.toFixed(4)],
    queryFn: () =>
      fetchNearbyDsos({
        raCenterDeg: centerRaDeg!,
        decCenterDeg: centerDecDeg!,
        extentDeg: annotationExtentDeg,
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
  const anyHasSize = nearbyItems.some((i) => i.maj_axis_arcmin != null) ||
    dsoMajAxisArcmin != null;

  const panGroupSize = gridPx;

  return (
    <>
      <Stack
        direction={{ xs: "column", md: "row" }}
        gap={2}
        alignItems={{ md: "flex-start" }}
      >
        {/* Viewport container — clips to one tile width. */}
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
          {/* Pan group — holds the 3×3 tile grid + rectangle + annotations. */}
          <Box
            ref={panGroupRef}
            style={{
              transform: gridTransformFromState(panX, panY, zoom, gridN),
              transformOrigin: "0 0",
            }}
            sx={{
              position: "absolute",
              top: 0,
              left: 0,
              width: panGroupSize,
              height: panGroupSize,
            }}
          >
            {tiles.map((t) => {
              const isCenter = t.col === 0 && t.row === 0;
              return (
                <Box
                  key={`${t.col},${t.row}`}
                  sx={{
                    position: "absolute",
                    left: (t.col + half) * size,
                    top: (t.row + half) * size,
                    width: size,
                    height: size,
                  }}
                >
                  <ThumbnailCell
                    dsoId={dsoId}
                    variant="fov_simulator"
                    fovMajorDeg={fovMajorDeg}
                    fovMinorDeg={fovMinorDeg}
                    // Centre tile pins to the DSO's own coords (no
                    // ``center_*`` params) so it shares the cache
                    // entry with any pre-pan visit. Neighbours carry
                    // explicit sky coords.
                    centerRaDeg={isCenter ? undefined : t.raDeg}
                    centerDecDeg={isCenter ? undefined : t.decDeg}
                    // Long-poll the backend. A CDS gnomonic render
                    // takes ~2.3 s on a fresh tile; with plain polling
                    // we pay the poll-cadence penalty on top of that.
                    // 4 s covers the typical fetch with margin; the
                    // 10 s server cap is the hard ceiling.
                    waitMs={4000}
                    fill
                    onReady={
                      isCenter
                        ? () => {
                            // Promote to the 3×3 inner grid as soon
                            // as the centre is visible. Ignored if
                            // already past stage 1 (e.g., re-ready
                            // on a silent refetch).
                            setGridN((cur) => (cur === 1 ? 3 : cur));
                          }
                        : undefined
                    }
                  />
                </Box>
              );
            })}

            {/* Faint tile-boundary affordance — signals the image is a
                mosaic so subtle seams read as intentional. Stroke
                width + dash lengths counter-scale by zoom so they stay
                ~1 CSS px at any zoom level (``vector-effect`` handles
                this natively but Safari's support is uneven across
                transform chains). */}
            {gridN > 1 && (
              <svg
                width={gridPx}
                height={gridPx}
                style={{
                  position: "absolute",
                  inset: 0,
                  pointerEvents: "none",
                }}
              >
                {Array.from({ length: gridN - 1 }, (_, i) => {
                  const pos = (i + 1) * size;
                  const strokeW = 1 / zoom;
                  const dash = `${6 / zoom} ${4 / zoom}`;
                  const lineProps = {
                    stroke: "#ffffff",
                    strokeOpacity: 0.14,
                    strokeWidth: strokeW,
                    strokeDasharray: dash,
                  } as const;
                  return (
                    <g key={`grid-${i}`}>
                      <line
                        x1={pos}
                        y1={0}
                        x2={pos}
                        y2={gridPx}
                        {...lineProps}
                      />
                      <line
                        x1={0}
                        y1={pos}
                        x2={gridPx}
                        y2={pos}
                        {...lineProps}
                      />
                    </g>
                  );
                })}
              </svg>
            )}

            {showAnnotations && showCoords && (
              <DsoAnnotationOverlay
                items={nearbyItems}
                primary={{
                  id: dsoId,
                  primary_designation: primaryDesignation ?? "",
                  ra_deg: centerRaDeg!,
                  dec_deg: centerDecDeg!,
                  maj_axis_arcmin: dsoMajAxisArcmin ?? null,
                }}
                centerRaDeg={centerRaDeg!}
                centerDecDeg={centerDecDeg!}
                tileExtentDeg={extentDeg}
                gridN={gridN}
                sizePx={gridPx}
                thresholdArcmin={thresholdArcmin}
                onAnnotationClick={(item, anchor) =>
                  setPopover({ item, anchor })
                }
              />
            )}

            {/* Sensor rectangle — positioned at the centre of the pan
                group (middle of the centre tile) + rectOffset. */}
            <Box
              ref={rectRef}
              onPointerDown={handleRectPointerDown}
              style={{
                transform: buildRectTransform(rectOffsetX, rectOffsetY, rotation),
                transformOrigin: "center center",
              }}
              sx={{
                position: "absolute",
                top: "50%",
                left: "50%",
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
          </Box>

          {/* North indicator — fixed in the viewport, not inside the
              pan group, so it always labels the screen's top. */}
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
                  <Tooltip title="Re-center the view on the object">
                    <IconButton size="small" onClick={resetAll} aria-label="Reset view">
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

          {showCoords && (
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
                  <IconButton size="small" onClick={() => setZoom(1)} aria-label="Reset zoom">
                    <RestartAltIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
              </Stack>
              <Stack direction="row" alignItems="center" gap={1} sx={{ mt: 0.5 }}>
                <Typography variant="caption" color="text.secondary" sx={{ minWidth: 56 }}>
                  {(zoom * 100).toFixed(0)}%
                </Typography>
                <Slider
                  size="small"
                  value={zoom}
                  min={zoomMin}
                  max={1}
                  step={0.01}
                  onChange={(_, v) => {
                    const next = Array.isArray(v) ? v[0] : v;
                    setZoom(Math.max(zoomMin, Math.min(1, next)));
                  }}
                />
              </Stack>
              <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
                {gridN === 1
                  ? "loading centre tile…"
                  : gridN === 3
                    ? "3×3 grid — 5×5 ring preloading"
                    : "5×5 grid · pan to explore"}
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
                <b>Drag the image</b> to pan (bounded to ±1 tile)
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
                <b>R</b> resets everything
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
