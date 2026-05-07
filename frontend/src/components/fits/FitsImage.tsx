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

// On iPad, fit-scale start + first pinch step makes WebKit lazily allocate
// the GPU layer mid-gesture, causing the well-known stutter. Starting at 1:1
// pays the layer-allocation cost up front (with the loading spinner already
// visible), and from then on transforms re-composite the existing layer
// smoothly. Desktop continues to start at fit.
const IS_TOUCH_DEVICE = typeof navigator !== "undefined" && navigator.maxTouchPoints > 1;



export const FitsImage = forwardRef<FitsImageHandle, Props>(
  function FitsImage({ path, hdu, linked, perChannel, activity, onZoomChange, onPixelHover, pixelPatchRadius = 50 }, ref) {
    const src = imageUrl(path, hdu, linked, perChannel, activity);
    const containerRef = useRef<HTMLDivElement | null>(null);
    const imgRef = useRef<HTMLImageElement | null>(null);

    // null zoom = fit-to-window (computed from container/image size).
    // Touch devices start at 1:1 so WebKit pre-allocates the GPU layer at
    // native resolution before the user can pinch. A black cover is shown
    // until WebKit finishes the allocation, then we swap to fit.
    const [zoom, setZoom] = useState<number | null>(IS_TOUCH_DEVICE ? 1 : null);
    const [prewarming, setPrewarming] = useState(IS_TOUCH_DEVICE);
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

    // Reset zoom/offset and loading state when a different file is opened.
    // Touch devices restart the prewarm-at-1:1-then-swap-to-fit dance.
    useEffect(() => {
      setZoom(IS_TOUCH_DEVICE ? 1 : null);
      setOffset({ x: 0, y: 0 });
      setImageLoaded(false);
      setImageLoading(false);
      setPrewarming(IS_TOUCH_DEVICE);
    }, [path, hdu]);

    // After the image loads at 1:1 on touch devices, give WebKit time to
    // allocate the native-resolution GPU layer, then swap to fit and reveal
    // the image. Switching scale earlier competes with the in-progress
    // allocation and re-triggers the stutter.
    useEffect(() => {
      if (!IS_TOUCH_DEVICE || !prewarming || !imageLoaded) return;
      const timer = setTimeout(() => {
        setZoom(null);
        requestAnimationFrame(() => setPrewarming(false));
      }, 1500);
      return () => clearTimeout(timer);
    }, [imageLoaded, prewarming]);

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
        // Touch handlers write directly to el.style.transform (inline), which
        // outranks the class-based sx transform. Clear the inline transform
        // so the React-rendered sx (driven by the new state) takes effect.
        if (imageWrapperRef.current) imageWrapperRef.current.style.transform = "";
        setZoom(null);
        setOffset({ x: 0, y: 0 });
      },
      oneToOne() {
        if (imageWrapperRef.current) imageWrapperRef.current.style.transform = "";
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

      const LONG_PRESS_MS = 400;
      const LONG_PRESS_MOVE_THRESHOLD = 10;
      const PIXEL_INSPECT_OFFSET_Y = -60;

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

      function samplePixelAt(clientX: number, clientY: number) {
        const img = imgRef.current;
        const ctx = samplingCtx.current;
        const onHover = onPixelHoverRef.current;
        if (!img || !onHover || !container || !img.naturalWidth) return;
        const rect = container.getBoundingClientRect();
        const sampleClientY = clientY + PIXEL_INSPECT_OFFSET_Y;
        const ch = crosshairRef.current;
        if (ch) {
          ch.style.display = "block";
          ch.style.left = `${clientX - rect.left - 12}px`;
          ch.style.top = `${sampleClientY - rect.top - 12}px`;
        }
        if (!ctx) return;
        const ez = zoomRef.current ?? currentZoom();
        const off = offsetRef.current;
        const mx = clientX - rect.left - rect.width / 2;
        const my = sampleClientY - rect.top - rect.height / 2;
        const imgX = (mx - off.x) / ez + img.naturalWidth / 2;
        const imgY = (my - off.y) / ez + img.naturalHeight / 2;
        const px = Math.floor(imgX);
        const py = Math.floor(imgY);
        if (px >= 0 && px < img.naturalWidth && py >= 0 && py < img.naturalHeight) {
          // 9-arg drawImage extracts just the patch region from the source
          // <img>. Avoids ever allocating a full-image canvas (iOS WebKit
          // silently fails for large canvases — see canvas-build effect).
          const patchRadius = 50;
          const patchSize = patchRadius * 2 + 1;
          const sx = Math.max(0, px - patchRadius);
          const sy = Math.max(0, py - patchRadius);
          const ex = Math.min(img.naturalWidth, px + patchRadius + 1);
          const ey = Math.min(img.naturalHeight, py + patchRadius + 1);
          const sw = ex - sx;
          const sh = ey - sy;
          // Destination offset on the small canvas so in-image pixels land
          // at the right spot (handles edge clamping).
          const ox = sx - (px - patchRadius);
          const oy = sy - (py - patchRadius);
          ctx.clearRect(0, 0, patchSize, patchSize);
          ctx.drawImage(img, sx, sy, sw, sh, ox, oy, sw, sh);
          const patch = ctx.getImageData(0, 0, patchSize, patchSize);
          // Center pixel = exact crosshair location
          const centerIdx = (patchRadius * patchSize + patchRadius) * 4;
          const r = patch.data[centerIdx] / 255;
          const g = patch.data[centerIdx + 1] / 255;
          const b = patch.data[centerIdx + 2] / 255;
          const k = 0.2126 * r + 0.7152 * g + 0.0722 * b;
          onHover({ x: px, y: py, R: r, G: g, B: b, K: k, patch });
        } else {
          onHover(null);
        }
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
        const img = imgRef.current;
        if (!el || !img) return;
        // Use pixel-valued centering translate (-W/2, -H/2) instead of the
        // percentage `translate(-50%, -50%)`. Mathematically identical, but
        // WebKit on iPad takes a slow path for percentage transforms that
        // depend on the element's box size.
        const halfW = img.naturalWidth / 2;
        const halfH = img.naturalHeight / 2;
        el.style.transform = `translate(${ox - halfW}px, ${oy - halfH}px) scale(${z})`;
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
            samplePixelAt(gesture.touchOriginX, gesture.touchOriginY);
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
            samplePixelAt(t.clientX, t.clientY);
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
        }
      }

      // iOS Safari fires proprietary gesturestart/change/end alongside touch
      // events; without preventDefault on these, native pinch-to-zoom of the
      // page engages even though touch-action is "none" — visible as the
      // "freeze then jump" stutter during two-finger zoom.
      function preventGesture(e: Event) {
        e.preventDefault();
      }

      container.addEventListener("touchstart", onTouchStart, { passive: false });
      container.addEventListener("touchmove", onTouchMove, { passive: false });
      container.addEventListener("touchend", onTouchEnd);
      container.addEventListener("gesturestart", preventGesture);
      container.addEventListener("gesturechange", preventGesture);
      container.addEventListener("gestureend", preventGesture);
      return () => {
        container.removeEventListener("touchstart", onTouchStart);
        container.removeEventListener("touchmove", onTouchMove);
        container.removeEventListener("touchend", onTouchEnd);
        container.removeEventListener("gesturestart", preventGesture);
        container.removeEventListener("gesturechange", preventGesture);
        container.removeEventListener("gestureend", preventGesture);
      };
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    // ── Pixel sampling (client-side via offscreen canvas) ──────────────────

    // Allocate a single small sampling canvas, big enough for the maximum
    // patch size (radius slider goes 10-150, so max patch = 301×301). We
    // never copy the whole image into a canvas — iOS WebKit silently fails
    // to allocate the backing store for huge canvases (a 6000×4000 image
    // needs ~96 MB), making drawImage a no-op and getImageData return
    // zeros. Using a tiny canvas + the 9-arg drawImage with source crop
    // lets us pull just the region we need per sample.
    useEffect(() => {
      const c = document.createElement("canvas");
      c.width = 301;
      c.height = 301;
      const ctx = c.getContext("2d", { willReadFrequently: true });
      if (ctx) {
        samplingCanvas.current = c;
        samplingCtx.current = ctx;
      }
      return () => {
        samplingCanvas.current = null;
        samplingCtx.current = null;
      };
    }, []);

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
        // Use 9-arg drawImage to copy just the patch region into the small
        // sampling canvas (see canvas-build effect for rationale).
        const patchRadius = pixelPatchRadius;
        const patchSize = patchRadius * 2 + 1;
        const sx = Math.max(0, px - patchRadius);
        const sy = Math.max(0, py - patchRadius);
        const ex = Math.min(img.naturalWidth, px + patchRadius + 1);
        const ey = Math.min(img.naturalHeight, py + patchRadius + 1);
        const sw = ex - sx;
        const sh = ey - sy;
        const ox = sx - (px - patchRadius);
        const oy = sy - (py - patchRadius);
        ctx.clearRect(0, 0, patchSize, patchSize);
        ctx.drawImage(img, sx, sy, sw, sh, ox, oy, sw, sh);
        const patch = ctx.getImageData(0, 0, patchSize, patchSize);
        const centerIdx = (patchRadius * patchSize + patchRadius) * 4;
        const r = patch.data[centerIdx] / 255;
        const g = patch.data[centerIdx + 1] / 255;
        const b = patch.data[centerIdx + 2] / 255;
        const k = 0.2126 * r + 0.7152 * g + 0.0722 * b;

        onPixelHover({ x: px, y: py, R: r, G: g, B: b, K: k, patch });
      } else {
        onPixelHover(null);
      }
    }

    function handleMouseLeaveForPixel() {
      onPixelHover?.(null);
    }

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
    const halfImgW = (imgRef.current?.naturalWidth ?? 0) / 2;
    const halfImgH = (imgRef.current?.naturalHeight ?? 0) / 2;

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
        {/* Touch-device prewarm cover — hides the image while it loads at
            1:1 and WebKit allocates the GPU layer, before we swap to fit. */}
        {prewarming && (
          <Box sx={{ position: "absolute", inset: 0, bgcolor: "#000", zIndex: 1 }} />
        )}
        {/* Loading spinner — initial load, src change (stretch applied), or prewarm. */}
        {(!imageLoaded || imageLoading || prewarming) && (
          <Box sx={{ position: "absolute", top: "50%", left: "50%", transform: "translate(-50%, -50%)", zIndex: 2 }}>
            <CircularProgress size={32} sx={{ color: "rgba(255,255,255,0.4)" }} />
          </Box>
        )}
        <Box
          ref={imageWrapperRef}
          sx={{
            position: "absolute",
            top: "50%",
            left: "50%",
            // Explicit width/height (matching FovSimulator's panGroup pattern)
            // gives WebKit a fixed-size layout box up front, so it can allocate
            // a stable GPU layer instead of re-resolving on every transform.
            width: halfImgW * 2 || undefined,
            height: halfImgH * 2 || undefined,
            transform: `translate(${offset.x - halfImgW}px, ${offset.y - halfImgH}px) scale(${ez})`,
            transformOrigin: "center center",
            imageRendering: ez >= 2 ? "pixelated" : "auto",
            // Pre-allocate the GPU layer at the wrapper's native size so the
            // first pinch doesn't trigger an incremental re-rasterize cascade.
            willChange: "transform",
          }}
        >
          <Box
            component="img"
            ref={imgRef}
            src={src}
            alt="Astronomical image"
            draggable={false}
            width={halfImgW * 2 || undefined}
            height={halfImgH * 2 || undefined}
            onLoad={() => { setImageLoaded(true); setImageLoading(false); forceRender((n) => n + 1); }}
            onError={() => { setImageLoaded(true); setImageLoading(false); forceRender((n) => n + 1); }}
            sx={{
              display: "block",
              width: "100%",
              height: "100%",
              visibility: imageLoaded ? "visible" : "hidden",
            }}
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
            zIndex: 3,
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
