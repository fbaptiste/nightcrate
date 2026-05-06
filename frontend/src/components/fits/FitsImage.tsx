import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from "react";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import { imageUrl, type StretchParams } from "@/api/images";

export interface PixelInfo {
  x: number;
  y: number;
  R: number;
  G: number;
  B: number;
  K: number;
  patch?: ImageData;
}

interface Props {
  path: string;
  hdu: number;
  linked: StretchParams;
  perChannel?: [StretchParams, StretchParams, StretchParams];
  /** Stable activity label for request tracking (set once on file open, doesn't change on tab switch). */
  activity?: string;
  onZoomChange?: (zoom: number) => void;
  onPixelHover?: (info: PixelInfo | null) => void;
  pixelPatchRadius?: number;
}

export interface FitsImageHandle {
  fitToWindow: () => void;
  oneToOne: () => void;
}

const MIN_ZOOM = 0.01;
const MAX_ZOOM = 40;
const ZOOM_FACTOR = 1.15;

export const FitsImage = forwardRef<FitsImageHandle, Props>(
  function FitsImage({ path, hdu, linked, perChannel, activity, onZoomChange, onPixelHover, pixelPatchRadius = 50 }, ref) {
    const src = imageUrl(path, hdu, linked, perChannel, activity);
    const containerRef = useRef<HTMLDivElement | null>(null);
    const imgRef = useRef<HTMLImageElement | null>(null);

    // null zoom = fit-to-window (computed from container/image size)
    const [zoom, setZoom] = useState<number | null>(null);
    const [imageLoaded, setImageLoaded] = useState(false);
    // Show spinner overlay when src changes (e.g., Apply stretch).
    // Old image stays visible behind spinner.
    const [imageLoading, setImageLoading] = useState(false);
    const prevSrc = useRef(src);
    const [offset, setOffset] = useState({ x: 0, y: 0 });
    const [isPanning, setIsPanning] = useState(false);
    const crosshairRef = useRef<SVGSVGElement | null>(null);
    const panStart = useRef({ x: 0, y: 0, ox: 0, oy: 0 });
    const imageWrapperRef = useRef<HTMLDivElement | null>(null);
    const samplingCanvas = useRef<HTMLCanvasElement | null>(null);
    const samplingCtx = useRef<CanvasRenderingContext2D | null>(null);

    // Cache the last valid fit scale so we don't lose it when the container
    // is hidden (display:none → 0×0) during tab switches.
    const lastFitScale = useRef(1);

    // Detect src changes for loading spinner (stretch param changes, etc.)
    if (src !== prevSrc.current) {
      prevSrc.current = src;
      if (imageLoaded) {
        setImageLoading(true);
      }
    }

    // Reset zoom/offset and loading state when a different file is opened
    useEffect(() => {
      setZoom(null);
      setOffset({ x: 0, y: 0 });
      setImageLoaded(false);
      setImageLoading(false);
    }, [path, hdu]);

    // Compute the fit-to-window scale
    function getFitScale(): number {
      const container = containerRef.current;
      const img = imgRef.current;
      if (!container || !img || !img.naturalWidth || !imageLoaded) return lastFitScale.current;
      const sx = container.clientWidth / img.naturalWidth;
      const sy = container.clientHeight / img.naturalHeight;
      const scale = Math.min(sx, sy);
      if (scale > 0) lastFitScale.current = scale;
      return lastFitScale.current;
    }

    // The effective zoom: if null, use fit scale
    function effectiveZoom(): number {
      return zoom ?? getFitScale();
    }

    useImperativeHandle(ref, () => ({
      fitToWindow() {
        setZoom(null);
        setOffset({ x: 0, y: 0 });
      },
      oneToOne() {
        setZoom(1);
        setOffset({ x: 0, y: 0 });
      },
    }));

    // ── Scroll-wheel zoom ────────────────────────────────────────────────────

    useEffect(() => {
      const container = containerRef.current;
      if (!container) return;

      function onWheel(e: WheelEvent) {
        e.preventDefault();
        const rect = container!.getBoundingClientRect();
        const mx = e.clientX - rect.left - rect.width / 2;
        const my = e.clientY - rect.top - rect.height / 2;

        const prevZoom = effectiveZoom();
        const direction = e.deltaY < 0 ? 1 : -1;
        const newZoom = Math.min(
          MAX_ZOOM,
          Math.max(MIN_ZOOM, prevZoom * (direction > 0 ? ZOOM_FACTOR : 1 / ZOOM_FACTOR)),
        );
        const ratio = newZoom / prevZoom;

        setOffset((prev) => ({
          x: mx - ratio * (mx - prev.x),
          y: my - ratio * (my - prev.y),
        }));
        setZoom(newZoom);
      }

      container.addEventListener("wheel", onWheel, { passive: false });
      return () => container.removeEventListener("wheel", onWheel);
      // No dependency array: re-binds each render so onWheel captures current zoom/offset
    });

    // ── Mouse panning ────────────────────────────────────────────────────────

    const handleMouseDown = useCallback(
      (e: React.MouseEvent) => {
        e.preventDefault();
        // Blur any focused element (e.g. Autocomplete) so dropdowns close
        if (document.activeElement instanceof HTMLElement) {
          document.activeElement.blur();
        }
        setIsPanning(true);
        panStart.current = { x: e.clientX, y: e.clientY, ox: offset.x, oy: offset.y };
      },
      [offset],
    );

    useEffect(() => {
      if (!isPanning) return;

      function onMove(e: MouseEvent) {
        const dx = e.clientX - panStart.current.x;
        const dy = e.clientY - panStart.current.y;
        setOffset({ x: panStart.current.ox + dx, y: panStart.current.oy + dy });
      }

      function onUp() {
        setIsPanning(false);
      }

      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
      return () => {
        window.removeEventListener("mousemove", onMove);
        window.removeEventListener("mouseup", onUp);
      };
    }, [isPanning]);

    // ── Touch pan + pinch-to-zoom ─────────────────────────────────────────

    const twoFingerRef = useRef(false);
    const zoomRef = useRef(zoom);
    const offsetRef = useRef(offset);
    const onPixelHoverRef = useRef(onPixelHover);
    zoomRef.current = zoom;
    offsetRef.current = offset;
    onPixelHoverRef.current = onPixelHover;

    useEffect(() => {
      const container = containerRef.current;
      if (!container) return;

      const LONG_PRESS_MS = 250;
      const LONG_PRESS_MOVE_THRESHOLD = 10;

      const gesture = {
        startDist: 0,
        startZoom: 0,
        startOffsetX: 0,
        startOffsetY: 0,
        midX: 0,
        midY: 0,
        panTouchId: null as number | null,
        panStartX: 0,
        panStartY: 0,
        panStartOx: 0,
        panStartOy: 0,
        longPressTimer: null as ReturnType<typeof setTimeout> | null,
        isInspecting: false,
        touchOriginX: 0,
        touchOriginY: 0,
      };

      function fingerDist(t1: Touch, t2: Touch): number {
        return Math.hypot(t1.clientX - t2.clientX, t1.clientY - t2.clientY);
      }

      function currentZoom(): number {
        if (zoomRef.current != null) return zoomRef.current;
        const img = imgRef.current;
        if (!container || !img || !img.naturalWidth) return 1;
        const sx = container.clientWidth / img.naturalWidth;
        const sy = container.clientHeight / img.naturalHeight;
        return Math.min(sx, sy);
      }

      function applyTransformDirect(ox: number, oy: number, z: number) {
        const el = imageWrapperRef.current;
        if (el) {
          el.style.transform = `translate(${ox}px, ${oy}px) translate(-50%, -50%) scale(${z})`;
          el.style.imageRendering = z >= 2 ? "pixelated" : "auto";
        }
      }

      function cancelLongPress() {
        if (gesture.longPressTimer) {
          clearTimeout(gesture.longPressTimer);
          gesture.longPressTimer = null;
        }
      }

      function onTouchStart(e: TouchEvent) {
        if (e.touches.length === 2) {
          e.preventDefault();
          cancelLongPress();
          gesture.isInspecting = false;
          twoFingerRef.current = true;
          gesture.panTouchId = null;
          gesture.startDist = fingerDist(e.touches[0], e.touches[1]);
          gesture.startZoom = currentZoom();
          gesture.startOffsetX = offsetRef.current.x;
          gesture.startOffsetY = offsetRef.current.y;
          const rect = container!.getBoundingClientRect();
          gesture.midX = (e.touches[0].clientX + e.touches[1].clientX) / 2 - rect.left - rect.width / 2;
          gesture.midY = (e.touches[0].clientY + e.touches[1].clientY) / 2 - rect.top - rect.height / 2;
        } else if (e.touches.length === 1 && !twoFingerRef.current) {
          gesture.panTouchId = e.touches[0].identifier;
          gesture.panStartX = e.touches[0].clientX;
          gesture.panStartY = e.touches[0].clientY;
          gesture.panStartOx = offsetRef.current.x;
          gesture.panStartOy = offsetRef.current.y;
          gesture.touchOriginX = e.touches[0].clientX;
          gesture.touchOriginY = e.touches[0].clientY;
          gesture.isInspecting = false;
          gesture.longPressTimer = setTimeout(() => {
            gesture.longPressTimer = null;
            gesture.isInspecting = true;
            gesture.panTouchId = null;
            samplePixelRef.current?.(gesture.touchOriginX, gesture.touchOriginY);
          }, LONG_PRESS_MS);
        }
      }

      function onTouchMove(e: TouchEvent) {
        if (e.touches.length === 2 && twoFingerRef.current) {
          e.preventDefault();
          const curDist = fingerDist(e.touches[0], e.touches[1]);
          const factor = curDist / gesture.startDist;
          const newZoom = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, gesture.startZoom * factor));
          const ratio = newZoom / gesture.startZoom;
          const mx = gesture.midX;
          const my = gesture.midY;
          const ox = mx - ratio * (mx - gesture.startOffsetX);
          const oy = my - ratio * (my - gesture.startOffsetY);
          offsetRef.current = { x: ox, y: oy };
          zoomRef.current = newZoom;
          applyTransformDirect(ox, oy, newZoom);
        } else if (e.touches.length === 1 && !twoFingerRef.current) {
          const t = e.touches[0];
          if (gesture.isInspecting) {
            e.preventDefault();
            samplePixelRef.current?.(t.clientX, t.clientY);
          } else {
            if (gesture.longPressTimer) {
              const dx = Math.abs(t.clientX - gesture.touchOriginX);
              const dy = Math.abs(t.clientY - gesture.touchOriginY);
              if (dx > LONG_PRESS_MOVE_THRESHOLD || dy > LONG_PRESS_MOVE_THRESHOLD) {
                cancelLongPress();
              }
            }
            if (gesture.panTouchId != null) {
              e.preventDefault();
              const dx = t.clientX - gesture.panStartX;
              const dy = t.clientY - gesture.panStartY;
              const ox = gesture.panStartOx + dx;
              const oy = gesture.panStartOy + dy;
              offsetRef.current = { x: ox, y: oy };
              applyTransformDirect(ox, oy, zoomRef.current ?? currentZoom());
            }
          }
        }
      }

      function onTouchEnd(e: TouchEvent) {
        cancelLongPress();
        if (gesture.isInspecting) {
          gesture.isInspecting = false;
          const onHover = onPixelHoverRef.current;
          if (onHover) onHover(null);
          const ch = crosshairRef.current;
          if (ch) ch.style.display = "none";
        }
        if (e.touches.length < 2) {
          twoFingerRef.current = false;
          gesture.startDist = 0;
        }
        if (e.touches.length === 0) {
          gesture.panTouchId = null;
          setOffset(offsetRef.current);
          if (zoomRef.current != null) setZoom(zoomRef.current);
          requestAnimationFrame(() => {
            const el = imageWrapperRef.current;
            if (el) {
              el.style.transform = "";
              el.style.imageRendering = "";
            }
          });
        }
      }

      container.addEventListener("touchstart", onTouchStart, { passive: false });
      container.addEventListener("touchmove", onTouchMove, { passive: false });
      container.addEventListener("touchend", onTouchEnd);
      return () => {
        container.removeEventListener("touchstart", onTouchStart);
        container.removeEventListener("touchmove", onTouchMove);
        container.removeEventListener("touchend", onTouchEnd);
      };
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    // ── Pixel sampling (client-side via offscreen canvas) ──────────────────

    // Rebuild the offscreen canvas when the image loads
    useEffect(() => {
      const img = imgRef.current;
      if (!img || !imageLoaded || !img.naturalWidth) {
        samplingCanvas.current = null;
        samplingCtx.current = null;
        return;
      }
      const c = document.createElement("canvas");
      c.width = img.naturalWidth;
      c.height = img.naturalHeight;
      const ctx = c.getContext("2d", { willReadFrequently: true });
      if (ctx) {
        ctx.drawImage(img, 0, 0);
        samplingCanvas.current = c;
        samplingCtx.current = ctx;
      }
    }, [imageLoaded, src]);

    function handleMouseMoveForPixel(e: React.MouseEvent) {
      if (!onPixelHover || !imgRef.current || !containerRef.current || isPanning) return;
      const img = imgRef.current;
      if (!img.naturalWidth || !samplingCtx.current) return;

      const container = containerRef.current;
      const rect = container.getBoundingClientRect();
      const ez = effectiveZoom();

      const mx = e.clientX - rect.left - rect.width / 2;
      const my = e.clientY - rect.top - rect.height / 2;

      const imgX = (mx - offset.x) / ez + img.naturalWidth / 2;
      const imgY = (my - offset.y) / ez + img.naturalHeight / 2;

      const px = Math.floor(imgX);
      const py = Math.floor(imgY);

      if (px >= 0 && px < img.naturalWidth && py >= 0 && py < img.naturalHeight) {
        const ctx = samplingCtx.current;
        const pixel = ctx.getImageData(px, py, 1, 1).data;
        const r = pixel[0] / 255;
        const g = pixel[1] / 255;
        const b = pixel[2] / 255;
        const k = 0.2126 * r + 0.7152 * g + 0.0722 * b;

        // Extract surrounding patch centered on the target pixel
        const patchRadius = pixelPatchRadius;
        const patchSize = patchRadius * 2 + 1;
        const sx = Math.max(0, px - patchRadius);
        const sy = Math.max(0, py - patchRadius);
        const ex = Math.min(img.naturalWidth, px + patchRadius + 1);
        const ey = Math.min(img.naturalHeight, py + patchRadius + 1);
        const sw = ex - sx;
        const sh = ey - sy;
        const srcPatch = ctx.getImageData(sx, sy, sw, sh);

        // Place into a full-size patch (handles edge clamping)
        const patch = new ImageData(patchSize, patchSize);
        const ox = px - patchRadius - sx;
        const oy = py - patchRadius - sy;
        for (let row = 0; row < sh; row++) {
          for (let col = 0; col < sw; col++) {
            const srcIdx = (row * sw + col) * 4;
            const dstIdx = ((row - oy) * patchSize + (col - ox)) * 4;
            patch.data[dstIdx] = srcPatch.data[srcIdx];
            patch.data[dstIdx + 1] = srcPatch.data[srcIdx + 1];
            patch.data[dstIdx + 2] = srcPatch.data[srcIdx + 2];
            patch.data[dstIdx + 3] = 255;
          }
        }

        onPixelHover({ x: px, y: py, R: r, G: g, B: b, K: k, patch });
      } else {
        onPixelHover(null);
      }
    }

    function handleMouseLeaveForPixel() {
      onPixelHover?.(null);
    }

    const PIXEL_INSPECT_OFFSET_Y = -60;
    function samplePixelAtClient(clientX: number, clientY: number) {
      if (!onPixelHover || !imgRef.current || !containerRef.current) return;
      const img = imgRef.current;
      if (!img.naturalWidth || !samplingCtx.current) return;
      const container = containerRef.current;
      const rect = container.getBoundingClientRect();
      const ez = effectiveZoom();
      const sampleClientY = clientY + PIXEL_INSPECT_OFFSET_Y;
      const mx = clientX - rect.left - rect.width / 2;
      const my = sampleClientY - rect.top - rect.height / 2;
      const ch = crosshairRef.current;
      if (ch) {
        ch.style.display = "block";
        ch.style.left = `${clientX - rect.left - 12}px`;
        ch.style.top = `${sampleClientY - rect.top - 12}px`;
      }
      const imgX = (mx - offset.x) / ez + img.naturalWidth / 2;
      const imgY = (my - offset.y) / ez + img.naturalHeight / 2;
      const px = Math.floor(imgX);
      const py = Math.floor(imgY);
      if (px >= 0 && px < img.naturalWidth && py >= 0 && py < img.naturalHeight) {
        const ctx = samplingCtx.current;
        const pixel = ctx.getImageData(px, py, 1, 1).data;
        const r = pixel[0] / 255;
        const g = pixel[1] / 255;
        const b = pixel[2] / 255;
        const k = 0.2126 * r + 0.7152 * g + 0.0722 * b;
        const patchRadius = pixelPatchRadius;
        const patchSize = patchRadius * 2 + 1;
        const sx2 = Math.max(0, px - patchRadius);
        const sy2 = Math.max(0, py - patchRadius);
        const ex = Math.min(img.naturalWidth, px + patchRadius + 1);
        const ey = Math.min(img.naturalHeight, py + patchRadius + 1);
        const sw = ex - sx2;
        const sh = ey - sy2;
        const srcPatch = ctx.getImageData(sx2, sy2, sw, sh);
        const patch = new ImageData(patchSize, patchSize);
        const pox = px - patchRadius - sx2;
        const poy = py - patchRadius - sy2;
        for (let row = 0; row < sh; row++) {
          for (let col = 0; col < sw; col++) {
            const srcIdx = (row * sw + col) * 4;
            const dstIdx = ((row - poy) * patchSize + (col - pox)) * 4;
            patch.data[dstIdx] = srcPatch.data[srcIdx];
            patch.data[dstIdx + 1] = srcPatch.data[srcIdx + 1];
            patch.data[dstIdx + 2] = srcPatch.data[srcIdx + 2];
            patch.data[dstIdx + 3] = 255;
          }
        }
        onPixelHover({ x: px, y: py, R: r, G: g, B: b, K: k, patch });
      } else {
        onPixelHover(null);
      }
    }
    const samplePixelRef = useRef(samplePixelAtClient);
    samplePixelRef.current = samplePixelAtClient;

    // ── Re-render when container resizes (e.g. tab becomes visible) ────────

    const [, forceRender] = useState(0);
    useEffect(() => {
      const container = containerRef.current;
      if (!container) return;
      const observer = new ResizeObserver(() => forceRender((n) => n + 1));
      observer.observe(container);
      return () => observer.disconnect();
    }, []);

    // ── Notify parent of zoom changes ──────────────────────────────────────

    const ez = effectiveZoom();

    useEffect(() => {
      onZoomChange?.(ez);
    }, [ez, onZoomChange]);

    // ── Render ───────────────────────────────────────────────────────────────

    return (
      <Box
        ref={containerRef}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMoveForPixel}
        onMouseLeave={handleMouseLeaveForPixel}
        sx={{
          height: "100%",
          overflow: "hidden",
          bgcolor: "#000",
          position: "relative",
          cursor: isPanning ? "grabbing" : onPixelHover ? `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24'%3E%3Ccircle cx='12' cy='12' r='8' fill='none' stroke='%23000' stroke-width='3'/%3E%3Cline x1='12' y1='0' x2='12' y2='8' stroke='%23000' stroke-width='3'/%3E%3Cline x1='12' y1='16' x2='12' y2='24' stroke='%23000' stroke-width='3'/%3E%3Cline x1='0' y1='12' x2='8' y2='12' stroke='%23000' stroke-width='3'/%3E%3Cline x1='16' y1='12' x2='24' y2='12' stroke='%23000' stroke-width='3'/%3E%3Ccircle cx='12' cy='12' r='8' fill='none' stroke='%23d4993f' stroke-width='1'/%3E%3Cline x1='12' y1='0' x2='12' y2='8' stroke='%23d4993f' stroke-width='1'/%3E%3Cline x1='12' y1='16' x2='12' y2='24' stroke='%23d4993f' stroke-width='1'/%3E%3Cline x1='0' y1='12' x2='8' y2='12' stroke='%23d4993f' stroke-width='1'/%3E%3Cline x1='16' y1='12' x2='24' y2='12' stroke='%23d4993f' stroke-width='1'/%3E%3C/svg%3E") 12 12, crosshair` : "default",
          userSelect: "none",
          WebkitTouchCallout: "none",
          WebkitUserSelect: "none",
          touchAction: "none",
        }}
      >
        {/* Loading spinner — initial load or src change (e.g., stretch applied) */}
        {(!imageLoaded || imageLoading) && (
          <Box sx={{ position: "absolute", top: "50%", left: "50%", transform: "translate(-50%, -50%)", zIndex: 1 }}>
            <CircularProgress size={32} sx={{ color: "rgba(255,255,255,0.4)" }} />
          </Box>
        )}
        <Box
          ref={imageWrapperRef}
          sx={{
            position: "absolute",
            top: "50%",
            left: "50%",
            transform: `translate(${offset.x}px, ${offset.y}px) translate(-50%, -50%) scale(${ez})`,
            transformOrigin: "center center",
            imageRendering: ez >= 2 ? "pixelated" : "auto",
          }}
        >
          <Box
            component="img"
            ref={imgRef}
            src={src}
            alt="Astronomical image"
            draggable={false}
            onLoad={() => { setImageLoaded(true); setImageLoading(false); forceRender((n) => n + 1); }}
            onError={() => { setImageLoaded(true); setImageLoading(false); forceRender((n) => n + 1); }}
            sx={{ display: "block", visibility: imageLoaded ? "visible" : "hidden" }}
          />
        </Box>
        <svg
          ref={crosshairRef}
          style={{
            position: "absolute",
            display: "none",
            width: 24,
            height: 24,
            pointerEvents: "none",
            zIndex: 2,
          }}
        >
          <circle cx={12} cy={12} r={8} fill="none" stroke="#d4993f" strokeWidth={1.5} />
          <line x1={12} y1={0} x2={12} y2={8} stroke="#d4993f" strokeWidth={1.5} />
          <line x1={12} y1={16} x2={12} y2={24} stroke="#d4993f" strokeWidth={1.5} />
          <line x1={0} y1={12} x2={8} y2={12} stroke="#d4993f" strokeWidth={1.5} />
          <line x1={16} y1={12} x2={24} y2={12} stroke="#d4993f" strokeWidth={1.5} />
        </svg>
      </Box>
    );
  },
);
