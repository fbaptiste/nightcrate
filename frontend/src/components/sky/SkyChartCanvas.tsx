import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
  type HTMLAttributes,
} from "react";
import { useTheme } from "@mui/material/styles";
import type { SolveField } from "@/api/projectInfo";
import { projectSolveImageUrl } from "@/api/projectSolve";
import type { SkyData } from "@/lib/skyChart/data";
import { drawSkyChart } from "@/lib/skyChart/draw";
import type { Rect, SkyView } from "@/lib/skyChart/geometry";
import { SKY_PALETTES } from "@/lib/skyChart/palette";

interface Props {
  data: SkyData;
  view: SkyView;
  mode: "compact" | "full";
  field: SolveField;
  projectId: number;
  projectName: string;
  /** Areas covered by controls over the canvas, in CSS pixels. */
  reserved?: readonly Rect[];
  canvasProps?: HTMLAttributes<HTMLCanvasElement>;
}

interface LoadedImage { source: HTMLImageElement; width: number; height: number; key: string }
interface LoadedImages { key: string; thumbnail: LoadedImage | null; full: LoadedImage | null }

const SkyChartCanvas = forwardRef<HTMLCanvasElement, Props>(function SkyChartCanvas(
  { data, view, mode, field, projectId, projectName, reserved, canvasProps },
  forwardedRef,
) {
  const theme = useTheme();
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const frameRef = useRef<number | null>(null);
  const loadGenerationRef = useRef(0);
  const generationKeyRef = useRef("");
  const thumbState = useRef({ key: "", status: "idle" as "idle" | "loading" | "done" | "failed" });
  const fullState = useRef({ key: "", status: "idle" as "idle" | "loading" | "done" | "failed" });
  const [size, setSize] = useState({ width: 0, height: 0, dpr: 1 });
  const [images, setImages] = useState<LoadedImages>({ key: "", thumbnail: null, full: null });
  useImperativeHandle(forwardedRef, () => canvasRef.current!, []);

  const imageKey = `${projectId}:${field.solve_id}`;
  const currentImages = images.key === imageKey
    ? images
    : { key: imageKey, thumbnail: null, full: null };

  useEffect(() => {
    const generation = loadGenerationRef.current + 1;
    loadGenerationRef.current = generation;
    generationKeyRef.current = imageKey;
    thumbState.current = { key: imageKey, status: "idle" };
    fullState.current = { key: imageKey, status: "idle" };
    return () => {
      if (loadGenerationRef.current === generation) loadGenerationRef.current += 1;
      if (generationKeyRef.current === imageKey) generationKeyRef.current = "";
    };
  }, [imageKey]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const update = () => {
      const rect = canvas.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 3);
      setSize((current) => rect.width === current.width && rect.height === current.height && dpr === current.dpr
        ? current
        : { width: rect.width, height: rect.height, dpr });
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(canvas);
    return () => observer.disconnect();
  }, []);

  const loadImage = useCallback((variant: "thumb_lg" | "full") => {
    const state = variant === "thumb_lg" ? thumbState : fullState;
    if (state.current.key !== imageKey) state.current = { key: imageKey, status: "idle" };
    if (state.current.status !== "idle") return;
    const generation = loadGenerationRef.current;
    state.current.status = "loading";
    const image = new Image();
    image.onload = async () => {
      if (variant === "full") {
        try {
          await image.decode();
        } catch {
          if (generation === loadGenerationRef.current && generationKeyRef.current === imageKey) {
            state.current = { key: imageKey, status: "failed" };
          }
          return;
        }
      }
      if (generation !== loadGenerationRef.current || generationKeyRef.current !== imageKey) return;
      const loaded = { source: image, width: image.naturalWidth, height: image.naturalHeight, key: imageKey };
      state.current = { key: imageKey, status: "done" };
      setImages((current) => {
        const active = current.key === imageKey
          ? current
          : { key: imageKey, thumbnail: null, full: null };
        return variant === "thumb_lg"
          ? { ...active, thumbnail: loaded }
          : { ...active, full: loaded };
      });
    };
    image.onerror = () => {
      if (generation !== loadGenerationRef.current || generationKeyRef.current !== imageKey) return;
      state.current = { key: imageKey, status: "failed" };
    };
    image.src = projectSolveImageUrl(projectId, variant, field.solve_id);
  }, [field.solve_id, imageKey, projectId]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !size.width || !size.height) return;
    if (frameRef.current != null) cancelAnimationFrame(frameRef.current);
    frameRef.current = requestAnimationFrame(() => {
      frameRef.current = null;
      const backingWidth = Math.max(1, Math.round(size.width * size.dpr));
      const backingHeight = Math.max(1, Math.round(size.height * size.dpr));
      if (canvas.width !== backingWidth || canvas.height !== backingHeight) {
        canvas.width = backingWidth;
        canvas.height = backingHeight;
      }
      const context = canvas.getContext("2d");
      if (!context) return;
      const activeImage = currentImages.full ?? currentImages.thumbnail;
      const result = drawSkyChart(context, {
        data,
        view,
        palette: theme.palette.mode === "dark" ? SKY_PALETTES.night : SKY_PALETTES.paper,
        fontFamily: theme.typography.fontFamily ?? '"DM Sans", sans-serif',
        targetCode: field.constellation,
        wcs: field.wcs,
        pictureCentre: [field.centre_ra_deg, field.centre_dec_deg],
        image: activeImage?.source ?? null,
        imageSize: activeImage ? { width: activeImage.width, height: activeImage.height } : null,
        label: projectName,
        mode,
        reserved,
      }, size);
      if (result.outlineLongerEdgePx >= 46 && (thumbState.current.key !== imageKey || thumbState.current.status === "idle")) loadImage("thumb_lg");
      if (result.pictureDrawnWidthDevicePx > 800 && (fullState.current.key !== imageKey || fullState.current.status === "idle")) loadImage("full");
    });
    return () => {
      if (frameRef.current != null) cancelAnimationFrame(frameRef.current);
      frameRef.current = null;
    };
  }, [currentImages.full, currentImages.thumbnail, data, field, imageKey, loadImage, mode, projectName, reserved, size, theme.palette.mode, theme.typography.fontFamily, view]);

  return <canvas {...canvasProps} ref={canvasRef} />;
});

export default SkyChartCanvas;
