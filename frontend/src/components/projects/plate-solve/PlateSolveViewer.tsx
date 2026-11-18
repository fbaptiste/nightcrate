import {
  forwardRef,
  memo,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Typography from "@mui/material/Typography";

import DsoAnnotationOverlay, {
  type OverlayDso,
} from "@/components/plate-solve/DsoAnnotationOverlay";
import {
  clampView,
  fitScale,
  keepCentre,
  zoomAt,
  type ViewBounds,
  type ViewSize,
  type ViewState,
} from "@/lib/plateSolveObjects";

export interface PlateSolveViewerHandle {
  revealObject: (id: number) => void;
}

interface Props {
  imageHref: string;
  imgW: number;
  imgH: number;
  dsos: OverlayDso[];
  mainIds: Set<number>;
  selectedId: number | null;
  onSelect: (id: number) => void;
  onDoubleSelect: (id: number) => void;
}

interface DragState {
  pointerId: number;
  startX: number;
  startY: number;
  startView: ViewState;
  moved: boolean;
}

const MIN_VIEWPORT_HEIGHT = 200;
const MAX_VIEWPORT_HEIGHT = 640;
const LEGEND_MIN_HEIGHT = 28;
const CULL_MARGIN_CSS_PX = 80;
const CULL_IDLE_MS = 100;

function boundsFor(imgW: number, imgH: number, size: ViewSize): ViewBounds {
  const fit = fitScale(imgW, imgH, size.width, size.height);
  return {
    imageWidth: imgW,
    imageHeight: imgH,
    viewportWidth: size.width,
    viewportHeight: size.height,
    minScale: Math.min(1, fit),
    maxScale: Math.max(8, fit * 8),
  };
}

function fittedView(imgW: number, imgH: number, size: ViewSize): ViewState {
  const scale = fitScale(imgW, imgH, size.width, size.height);
  return {
    scale,
    x: (size.width - imgW * scale) / 2,
    y: (size.height - imgH * scale) / 2,
  };
}

function objectsInView(
  dsos: OverlayDso[],
  view: ViewState,
  size: ViewSize,
): OverlayDso[] {
  if (size.width <= 0 || size.height <= 0) return dsos;
  const margin = CULL_MARGIN_CSS_PX / view.scale;
  const left = -view.x / view.scale - margin;
  const top = -view.y / view.scale - margin;
  const right = (size.width - view.x) / view.scale + margin;
  const bottom = (size.height - view.y) / view.scale + margin;
  return dsos.filter((object) => {
    const rx = object.ellipse_semi_major_px ?? 8 / view.scale;
    const ry = object.ellipse_semi_minor_px ?? rx;
    return (
      object.pixel_x + rx >= left &&
      object.pixel_x - rx <= right &&
      object.pixel_y + ry >= top &&
      object.pixel_y - ry <= bottom
    );
  });
}

function sameObjects(left: OverlayDso[], right: OverlayDso[]): boolean {
  return (
    left.length === right.length &&
    left.every((object, index) => object === right[index])
  );
}

const PlateSolveViewer = memo(
  forwardRef<PlateSolveViewerHandle, Props>(function PlateSolveViewer(
    { imageHref, imgW, imgH, dsos, mainIds, selectedId, onSelect, onDoubleSelect },
    ref,
  ) {
    const viewportRef = useRef<HTMLDivElement | null>(null);
    const sizeRef = useRef<ViewSize>({ width: 0, height: 0 });
    const viewRef = useRef<ViewState>({ scale: 1, x: 0, y: 0 });
    const dragRef = useRef<DragState | null>(null);
    const suppressUntilRef = useRef(0);
    const naturalViewportHeightRef = useRef(MIN_VIEWPORT_HEIGHT);
    const dsosRef = useRef(dsos);
    const cullTimerRef = useRef<number | null>(null);
    const [view, setViewState] = useState<ViewState>({ scale: 1, x: 0, y: 0 });
    const [naturalViewportHeight, setNaturalViewportHeight] = useState(MIN_VIEWPORT_HEIGHT);
    const [visibleDsos, setVisibleDsos] = useState(dsos);

    const cullNow = useCallback((nextView: ViewState = viewRef.current) => {
      const next = objectsInView(dsosRef.current, nextView, sizeRef.current);
      setVisibleDsos((current) => (sameObjects(current, next) ? current : next));
    }, []);

    const scheduleCull = useCallback(
      (nextView: ViewState) => {
        if (cullTimerRef.current != null) window.clearTimeout(cullTimerRef.current);
        cullTimerRef.current = window.setTimeout(() => {
          cullTimerRef.current = null;
          cullNow(nextView);
        }, CULL_IDLE_MS);
      },
      [cullNow],
    );

    const setView = useCallback(
      (next: ViewState) => {
        viewRef.current = next;
        setViewState(next);
        scheduleCull(next);
      },
      [scheduleCull],
    );

    useEffect(() => {
      dsosRef.current = dsos;
      cullNow();
    }, [cullNow, dsos]);

    useEffect(
      () => () => {
        if (cullTimerRef.current != null) window.clearTimeout(cullTimerRef.current);
      },
      [],
    );

    useEffect(() => {
      const viewport = viewportRef.current;
      if (!viewport) return;
      let resizeFrame = 0;
      const resize = () => {
        const rect = viewport.getBoundingClientRect();
        const nextSize = { width: rect.width, height: rect.height };
        if (nextSize.width <= 0 || nextSize.height <= 0) return;
        const nextNaturalHeight = Math.max(
          MIN_VIEWPORT_HEIGHT,
          Math.min(MAX_VIEWPORT_HEIGHT, (nextSize.width * imgH) / imgW),
        );
        if (Math.abs(naturalViewportHeightRef.current - nextNaturalHeight) > 0.5) {
          naturalViewportHeightRef.current = nextNaturalHeight;
          setNaturalViewportHeight(nextNaturalHeight);
          cancelAnimationFrame(resizeFrame);
          resizeFrame = requestAnimationFrame(resize);
          return;
        }
        const oldSize = sizeRef.current;
        const next =
          oldSize.width <= 0 || oldSize.height <= 0
            ? fittedView(imgW, imgH, nextSize)
            : keepCentre(
                viewRef.current,
                oldSize,
                nextSize,
                boundsFor(imgW, imgH, nextSize),
              );
        sizeRef.current = nextSize;
        setView(next);
      };
      resize();
      const observer = new ResizeObserver(resize);
      observer.observe(viewport);
      return () => {
        cancelAnimationFrame(resizeFrame);
        observer.disconnect();
      };
    }, [imgH, imgW, setView]);

    const zoom = useCallback(
      (point: { x: number; y: number }, factor: number) => {
        const size = sizeRef.current;
        if (size.width <= 0) return;
        setView(zoomAt(viewRef.current, point, factor, boundsFor(imgW, imgH, size)));
      },
      [imgH, imgW, setView],
    );

    useEffect(() => {
      const viewport = viewportRef.current;
      if (!viewport) return;
      let wheelFrame = 0;
      let wheelFactor = 1;
      let wheelPoint = { x: 0, y: 0 };
      const wheel = (event: WheelEvent) => {
        event.preventDefault();
        const rect = viewport.getBoundingClientRect();
        wheelPoint = { x: event.clientX - rect.left, y: event.clientY - rect.top };
        wheelFactor *= Math.exp(-event.deltaY * 0.0015);
        if (wheelFrame !== 0) return;
        wheelFrame = requestAnimationFrame(() => {
          const point = wheelPoint;
          const factor = wheelFactor;
          wheelFrame = 0;
          wheelFactor = 1;
          zoom(point, factor);
        });
      };
      viewport.addEventListener("wheel", wheel, { passive: false });
      return () => {
        cancelAnimationFrame(wheelFrame);
        viewport.removeEventListener("wheel", wheel);
      };
    }, [zoom]);

    useImperativeHandle(
      ref,
      () => ({
        revealObject: (id: number) => {
          const object = dsos.find((item) => item.id === id);
          if (!object) return;
          const size = sizeRef.current;
          const current = viewRef.current;
          const radius = Math.max(
            object.ellipse_semi_major_px ?? 0,
            object.ellipse_semi_minor_px ?? 0,
          );
          const left = (object.pixel_x - radius) * current.scale + current.x;
          const right = (object.pixel_x + radius) * current.scale + current.x;
          const top = (object.pixel_y - radius) * current.scale + current.y;
          const bottom = (object.pixel_y + radius) * current.scale + current.y;
          if (left >= 12 && right <= size.width - 12 && top >= 12 && bottom <= size.height - 12) {
            return;
          }
          setView(
            clampView(
              {
                ...current,
                x: size.width / 2 - object.pixel_x * current.scale,
                y: size.height / 2 - object.pixel_y * current.scale,
              },
              boundsFor(imgW, imgH, size),
            ),
          );
        },
      }),
      [dsos, imgH, imgW, setView],
    );

    const centre = () => ({ x: sizeRef.current.width / 2, y: sizeRef.current.height / 2 });
    const fit = () => setView(fittedView(imgW, imgH, sizeRef.current));
    const oneToOne = () => zoom(centre(), 1 / viewRef.current.scale);

    return (
      <Box
        sx={{
          flex: `0 1 ${naturalViewportHeight + LEGEND_MIN_HEIGHT}px`,
          minHeight: MIN_VIEWPORT_HEIGHT + LEGEND_MIN_HEIGHT,
          display: "flex",
          flexDirection: "column",
        }}
      >
        <Box
          ref={viewportRef}
          onPointerDown={(event) => {
            if (event.button !== 0) return;
            // A new pointer sequence is a separate interaction from the drag
            // that armed click suppression, even when it starts on a control.
            suppressUntilRef.current = 0;
            if (event.target instanceof Element && event.target.closest("button")) return;
            dragRef.current = {
              pointerId: event.pointerId,
              startX: event.clientX,
              startY: event.clientY,
              startView: viewRef.current,
              moved: false,
            };
          }}
          onPointerMove={(event) => {
            const drag = dragRef.current;
            if (!drag || drag.pointerId !== event.pointerId) return;
            const dx = event.clientX - drag.startX;
            const dy = event.clientY - drag.startY;
            if (!drag.moved && Math.hypot(dx, dy) <= 4) return;
            if (!drag.moved) event.currentTarget.setPointerCapture(event.pointerId);
            drag.moved = true;
            event.preventDefault();
            setView(
              clampView(
                { ...drag.startView, x: drag.startView.x + dx, y: drag.startView.y + dy },
                boundsFor(imgW, imgH, sizeRef.current),
              ),
            );
          }}
          onPointerUp={(event) => {
            const drag = dragRef.current;
            if (drag?.pointerId === event.pointerId && drag.moved) {
              suppressUntilRef.current = performance.now() + 400;
            }
            dragRef.current = null;
            if (event.currentTarget.hasPointerCapture(event.pointerId)) {
              event.currentTarget.releasePointerCapture(event.pointerId);
            }
          }}
          onPointerCancel={() => {
            dragRef.current = null;
            suppressUntilRef.current = performance.now() + 400;
          }}
          onClickCapture={(event) => {
            if (performance.now() < suppressUntilRef.current) {
              event.preventDefault();
              event.stopPropagation();
            }
          }}
          onDoubleClickCapture={(event) => {
            if (performance.now() < suppressUntilRef.current) {
              event.preventDefault();
              event.stopPropagation();
            }
          }}
          sx={{
            flex: 1,
            minHeight: MIN_VIEWPORT_HEIGHT,
            position: "relative",
            overflow: "hidden",
            bgcolor: "common.black",
            borderRadius: "6px",
            touchAction: "none",
            cursor: "grab",
            "&:active": { cursor: "grabbing" },
          }}
        >
          <Box
            sx={{
              position: "absolute",
              left: 0,
              top: 0,
              width: imgW,
              height: imgH,
              transformOrigin: "0 0",
              transform: `translate(${view.x}px, ${view.y}px) scale(${view.scale})`,
              "--dso-unit": String(1 / view.scale),
            }}
          >
            <DsoAnnotationOverlay
              imageHref={imageHref}
              imgW={imgW}
              imgH={imgH}
              dsos={visibleDsos}
              selectedId={selectedId}
              onSelect={onSelect}
              mainIds={mainIds}
              palette="project"
              onDoubleSelect={onDoubleSelect}
              scaleFromCss
            />
          </Box>
          <Box sx={{ position: "absolute", top: 10, left: 10, display: "flex", gap: 0.5 }}>
            <Button aria-label="Zoom in" onClick={() => zoom(centre(), 1.5)} sx={{ minWidth: 34, width: 34, height: 34, p: 0, bgcolor: "rgba(10,13,18,0.86)", color: "common.white", border: 1, borderColor: "rgba(255,255,255,0.24)" }}>+</Button>
            <Button aria-label="Zoom out" onClick={() => zoom(centre(), 1 / 1.5)} sx={{ minWidth: 34, width: 34, height: 34, p: 0, bgcolor: "rgba(10,13,18,0.86)", color: "common.white", border: 1, borderColor: "rgba(255,255,255,0.24)" }}>−</Button>
            <Button onClick={fit} sx={{ minWidth: 38, height: 34, px: 0.75, bgcolor: "rgba(10,13,18,0.86)", color: "common.white", border: 1, borderColor: "rgba(255,255,255,0.24)" }}>Fit</Button>
            <Button onClick={oneToOne} sx={{ minWidth: 38, height: 34, px: 0.75, bgcolor: "rgba(10,13,18,0.86)", color: "common.white", border: 1, borderColor: "rgba(255,255,255,0.24)" }}>1:1</Button>
          </Box>
          <Typography sx={{ position: "absolute", top: 10, right: 10, px: 1, py: 0.45, borderRadius: "6px", bgcolor: "rgba(10,13,18,0.86)", color: "rgba(255,255,255,0.72)", fontSize: 11.5 }}>
            {Math.round(view.scale * 100)}% of full size
          </Typography>
        </Box>
        <Box sx={{ minHeight: LEGEND_MIN_HEIGHT, display: "flex", alignItems: "center", flexWrap: "wrap", gap: 1.5, px: 0.25 }}>
          <LegendDot color="#ffd400" label="Selected" />
          <LegendDot color="#4fb0ff" outer="#ffd400" label="Selected main target" />
          <LegendDot color="#4fb0ff" label="Main target" />
          <LegendDot color="#9a9894" label="Other objects" />
          <Typography color="text.secondary" sx={{ ml: "auto", fontSize: 11.5 }}>
            Double-click an object to move it into or out of Main targets.
          </Typography>
        </Box>
      </Box>
    );
  }),
);

function LegendDot({ color, outer, label }: { color: string; outer?: string; label: string }) {
  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
      <Box sx={{ width: 13, height: 13, borderRadius: "50%", border: `${outer ? 2 : 2.5}px solid ${outer ?? color}`, display: "grid", placeItems: "center" }}>
        {outer && <Box sx={{ width: 7, height: 7, borderRadius: "50%", border: `2px solid ${color}` }} />}
      </Box>
      <Typography color="text.secondary" sx={{ fontSize: 11.5 }}>{label}</Typography>
    </Box>
  );
}

export default PlateSolveViewer;
