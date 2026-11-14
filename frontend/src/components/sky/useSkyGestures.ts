import { useEffect, useRef } from "react";
import {
  anchorView,
  classifyTap,
  makeProjection,
  panView,
  zoomViewAt,
  type SkyCoord,
  type SkyView,
} from "@/lib/skyChart/geometry";

interface Size { width: number; height: number }
interface Options {
  view: SkyView;
  setView: (view: SkyView) => void;
  size: Size;
  onDoubleTap?: () => void;
}

export default function useSkyGestures(
  canvas: HTMLCanvasElement | null,
  container: HTMLElement | null,
  { view, setView, size, onDoubleTap }: Options,
) {
  const viewRef = useRef(view);
  const setViewRef = useRef(setView);
  const sizeRef = useRef(size);
  const doubleTapRef = useRef(onDoubleTap);
  useEffect(() => { viewRef.current = view; }, [view]);
  useEffect(() => { setViewRef.current = setView; }, [setView]);
  useEffect(() => { sizeRef.current = size; }, [size]);
  useEffect(() => { doubleTapRef.current = onDoubleTap; }, [onDoubleTap]);

  useEffect(() => {
    if (!canvas || !container) return;
    const pointers = new Map<number, {
      point: [number, number];
      downPoint: [number, number];
      downTime: number;
      movementPx: number;
      tapBlocked: boolean;
      type: string;
    }>();
    let grabbed: SkyCoord | null = null;
    let pinch: { view: SkyView; distance: number; midpoint: [number, number]; grabbed: SkyCoord } | null = null;
    let lastTap: { time: number; point: [number, number] } | null = null;

    const localPoint = (event: PointerEvent | WheelEvent | MouseEvent): [number, number] => {
      const rect = canvas.getBoundingClientRect();
      return [event.clientX - rect.left, event.clientY - rect.top];
    };
    const startPinch = () => {
      const active = [...pointers.values()];
      if (active.length !== 2) { pinch = null; return; }
      const midpoint: [number, number] = [
        (active[0].point[0] + active[1].point[0]) / 2,
        (active[0].point[1] + active[1].point[1]) / 2,
      ];
      const distance = Math.hypot(active[1].point[0] - active[0].point[0], active[1].point[1] - active[0].point[1]);
      const current = viewRef.current;
      const inverted = makeProjection(current, sizeRef.current.width, sizeRef.current.height).invert?.(midpoint);
      if (inverted) pinch = { view: current, distance: Math.max(distance, 1), midpoint, grabbed: [inverted[0], inverted[1]] };
    };
    const onPointerDown = (event: PointerEvent) => {
      event.preventDefault();
      canvas.setPointerCapture(event.pointerId);
      const point = localPoint(event);
      pointers.set(event.pointerId, {
        point,
        downPoint: point,
        downTime: performance.now(),
        movementPx: 0,
        tapBlocked: false,
        type: event.pointerType,
      });
      if (pointers.size === 1) {
        const inverted = makeProjection(viewRef.current, sizeRef.current.width, sizeRef.current.height).invert?.(point);
        grabbed = inverted ? [inverted[0], inverted[1]] : null;
      } else {
        for (const active of pointers.values()) active.tapBlocked = true;
        if (pointers.size === 2) startPinch();
      }
    };
    const onPointerMove = (event: PointerEvent) => {
      const pointer = pointers.get(event.pointerId);
      if (!pointer) return;
      event.preventDefault();
      const point = localPoint(event);
      pointer.point = point;
      pointer.movementPx = Math.max(
        pointer.movementPx,
        Math.hypot(point[0] - pointer.downPoint[0], point[1] - pointer.downPoint[1]),
      );
      if (pointers.size === 1 && grabbed) {
        setViewRef.current(panView(viewRef.current, grabbed, pointer.point, sizeRef.current.width, sizeRef.current.height));
      } else if (pointers.size === 2 && pinch) {
        const active = [...pointers.values()];
        const midpoint: [number, number] = [
          (active[0].point[0] + active[1].point[0]) / 2,
          (active[0].point[1] + active[1].point[1]) / 2,
        ];
        const distance = Math.max(1, Math.hypot(active[1].point[0] - active[0].point[0], active[1].point[1] - active[0].point[1]));
        const span = pinch.view.spanDeg / (distance / pinch.distance);
        setViewRef.current(anchorView(
          pinch.view,
          span,
          pinch.grabbed,
          midpoint,
          sizeRef.current.width,
          sizeRef.current.height,
        ).view);
      }
    };
    const finishPointer = (event: PointerEvent) => {
      const pointer = pointers.get(event.pointerId);
      if (pointer?.type === "touch") {
        const point = localPoint(event);
        const now = performance.now();
        const result = classifyTap({
          point,
          time: now,
          durationMs: now - pointer.downTime,
          movementPx: Math.max(
            pointer.movementPx,
            Math.hypot(point[0] - pointer.downPoint[0], point[1] - pointer.downPoint[1]),
          ),
          blocked: pointer.tapBlocked || pointers.size !== 1 || event.type !== "pointerup",
        }, lastTap);
        lastTap = result.lastTap;
        if (result.kind === "double") {
          setViewRef.current(zoomViewAt(viewRef.current, 2, point, sizeRef.current.width, sizeRef.current.height));
          doubleTapRef.current?.();
        }
      }
      pointers.delete(event.pointerId);
      if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
      pinch = null;
      grabbed = null;
      if (pointers.size === 1) {
        const remaining = [...pointers.values()][0];
        const inverted = makeProjection(viewRef.current, sizeRef.current.width, sizeRef.current.height).invert?.(remaining.point);
        grabbed = inverted ? [inverted[0], inverted[1]] : null;
      }
    };
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      const delta = event.deltaY * (event.deltaMode === 1 ? 0.05 : event.deltaMode ? 1 : 0.002) * (event.ctrlKey ? 10 : 1);
      setViewRef.current(zoomViewAt(viewRef.current, 2 ** -delta, localPoint(event), sizeRef.current.width, sizeRef.current.height));
    };
    const onDoubleClick = (event: MouseEvent) => {
      event.preventDefault();
      setViewRef.current(zoomViewAt(viewRef.current, 2, localPoint(event), sizeRef.current.width, sizeRef.current.height));
    };
    const preventDefault = (event: Event) => event.preventDefault();

    canvas.addEventListener("pointerdown", onPointerDown);
    canvas.addEventListener("pointermove", onPointerMove);
    canvas.addEventListener("pointerup", finishPointer);
    canvas.addEventListener("pointercancel", finishPointer);
    canvas.addEventListener("wheel", onWheel, { passive: false });
    canvas.addEventListener("dblclick", onDoubleClick);
    canvas.addEventListener("touchstart", preventDefault, { passive: false });
    canvas.addEventListener("touchmove", preventDefault, { passive: false });
    container.addEventListener("gesturestart", preventDefault);
    container.addEventListener("gesturechange", preventDefault);
    container.addEventListener("gestureend", preventDefault);
    return () => {
      canvas.removeEventListener("pointerdown", onPointerDown);
      canvas.removeEventListener("pointermove", onPointerMove);
      canvas.removeEventListener("pointerup", finishPointer);
      canvas.removeEventListener("pointercancel", finishPointer);
      canvas.removeEventListener("wheel", onWheel);
      canvas.removeEventListener("dblclick", onDoubleClick);
      canvas.removeEventListener("touchstart", preventDefault);
      canvas.removeEventListener("touchmove", preventDefault);
      container.removeEventListener("gesturestart", preventDefault);
      container.removeEventListener("gesturechange", preventDefault);
      container.removeEventListener("gestureend", preventDefault);
    };
  }, [canvas, container]);
}
