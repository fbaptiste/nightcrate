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
  function FitsImage({ path, hdu, linked, perChannel, onZoomChange, onPixelHover, pixelPatchRadius = 50 }, ref) {
    const src = imageUrl(path, hdu, linked, perChannel);
    const containerRef = useRef<HTMLDivElement | null>(null);
    const imgRef = useRef<HTMLImageElement | null>(null);

    // null zoom = fit-to-window (computed from container/image size)
    const [zoom, setZoom] = useState<number | null>(null);
    const [imageLoaded, setImageLoaded] = useState(false);
    const [offset, setOffset] = useState({ x: 0, y: 0 });
    const [isPanning, setIsPanning] = useState(false);
    const panStart = useRef({ x: 0, y: 0, ox: 0, oy: 0 });

    // Reset zoom/offset and loading state when a different file is opened
    useEffect(() => {
      setZoom(null);
      setOffset({ x: 0, y: 0 });
      setImageLoaded(false);
    }, [path, hdu]);

    // Compute the fit-to-window scale
    function getFitScale(): number {
      const container = containerRef.current;
      const img = imgRef.current;
      if (!container || !img || !img.naturalWidth || !imageLoaded) return 1;
      const sx = container.clientWidth / img.naturalWidth;
      const sy = container.clientHeight / img.naturalHeight;
      return Math.min(sx, sy);
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

    // ── Pixel sampling (client-side via offscreen canvas) ──────────────────

    const samplingCanvas = useRef<HTMLCanvasElement | null>(null);
    const samplingCtx = useRef<CanvasRenderingContext2D | null>(null);

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
        }}
      >
        {/* Loading spinner */}
        {!imageLoaded && (
          <Box sx={{ position: "absolute", top: "50%", left: "50%", transform: "translate(-50%, -50%)" }}>
            <CircularProgress size={32} sx={{ color: "rgba(255,255,255,0.4)" }} />
          </Box>
        )}
        <Box
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
            onLoad={() => setImageLoaded(true)}
            onError={() => setImageLoaded(true)}
            sx={{ display: "block", visibility: imageLoaded ? "visible" : "hidden" }}
          />
        </Box>
      </Box>
    );
  },
);
