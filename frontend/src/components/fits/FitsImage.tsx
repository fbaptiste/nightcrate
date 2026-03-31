import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from "react";
import Box from "@mui/material/Box";
import { imageUrl, type StretchParams } from "@/api/images";

interface Props {
  path: string;
  hdu: number;
  linked: StretchParams;
  perChannel?: [StretchParams, StretchParams, StretchParams];
  onZoomChange?: (zoom: number) => void;
}

export interface FitsImageHandle {
  fitToWindow: () => void;
  oneToOne: () => void;
}

const MIN_ZOOM = 0.01;
const MAX_ZOOM = 40;
const ZOOM_FACTOR = 1.15;

export const FitsImage = forwardRef<FitsImageHandle, Props>(
  function FitsImage({ path, hdu, linked, perChannel, onZoomChange }, ref) {
    const src = imageUrl(path, hdu, linked, perChannel);
    const containerRef = useRef<HTMLDivElement | null>(null);
    const imgRef = useRef<HTMLImageElement | null>(null);

    // null zoom = fit-to-window (computed from container/image size)
    const [zoom, setZoom] = useState<number | null>(null);
    const [imageLoaded, setImageLoaded] = useState(false);
    const [offset, setOffset] = useState({ x: 0, y: 0 });
    const [isPanning, setIsPanning] = useState(false);
    const panStart = useRef({ x: 0, y: 0, ox: 0, oy: 0 });

    // Reset to fit when image source changes
    useEffect(() => {
      setZoom(null);
      setOffset({ x: 0, y: 0 });
      setImageLoaded(false);
    }, [src]);

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
        sx={{
          height: "100%",
          overflow: "hidden",
          bgcolor: "#000",
          position: "relative",
          cursor: isPanning ? "grabbing" : "grab",
          userSelect: "none",
        }}
      >
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
            alt="FITS image"
            draggable={false}
            onLoad={() => setImageLoaded(true)}
            sx={{ display: "block", visibility: imageLoaded ? "visible" : "hidden" }}
          />
        </Box>
      </Box>
    );
  },
);
