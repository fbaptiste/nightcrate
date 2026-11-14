import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import IconButton from "@mui/material/IconButton";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";
import { useTheme } from "@mui/material/styles";
import type { ProjectInfo } from "@/api/projectInfo";
import { displayConstellation } from "@/lib/constellations";
import { targetLabel } from "@/lib/objectFacts";
import { useSkyData } from "@/lib/skyChart/data";
import {
  fitConstellationView,
  interpolateView,
  panViewBy,
  pictureLongerSideDeg,
  pictureView,
  pxPerDegree,
  scaleBarStep,
  wholeSkyView,
  zoomViewAt,
  type Rect,
  type SkyView,
} from "@/lib/skyChart/geometry";
import { SKY_PALETTES } from "@/lib/skyChart/palette";
import { headerSubtitle } from "@/lib/skyChart/text";
import SkyChartCanvas from "./SkyChartCanvas";
import useSkyGestures from "./useSkyGestures";

interface Props { open: boolean; onClose: () => void; info: ProjectInfo }

export default function SkyChartDialog({ open, onClose, info }: Props) {
  const theme = useTheme();
  const query = useSkyData();
  const field = info.field;
  if (!field) throw new Error("A sky chart requires a solved field");
  if (query.isError) throw query.error;
  const palette = theme.palette.mode === "dark" ? SKY_PALETTES.night : SKY_PALETTES.paper;
  const [canvas, setCanvas] = useState<HTMLCanvasElement | null>(null);
  const [container, setContainer] = useState<HTMLDivElement | null>(null);
  const [toolbar, setToolbar] = useState<HTMLDivElement | null>(null);
  const [toolbarBox, setToolbarBox] = useState<Rect | null>(null);
  const animationRef = useRef<number | null>(null);
  const initializedRef = useRef(false);
  const [size, setSize] = useState({ width: 1000, height: 750 });
  const [view, setView] = useState<SkyView>({
    centre: [field.centre_ra_deg, field.centre_dec_deg],
    spanDeg: 60,
  });
  const viewRef = useRef(view);
  useEffect(() => { viewRef.current = view; }, [view]);

  const constellationName = displayConstellation(field.constellation);
  const constellationView = useMemo(() => query.data
    ? fitConstellationView(
      query.data.boundaries[field.constellation] ?? [],
      [field.centre_ra_deg, field.centre_dec_deg],
      size.width,
      size.height,
    )
    : { centre: [field.centre_ra_deg, field.centre_dec_deg], spanDeg: 60 } as SkyView,
  [field.centre_dec_deg, field.centre_ra_deg, field.constellation, query.data, size.height, size.width]);

  const cancelAnimation = useCallback(() => {
    if (animationRef.current != null) cancelAnimationFrame(animationRef.current);
    animationRef.current = null;
  }, []);
  const setInteractiveView = useCallback((next: SkyView) => {
    cancelAnimation();
    setView(next);
  }, [cancelAnimation]);
  useSkyGestures(canvas, container, { view, setView: setInteractiveView, size });

  useEffect(() => {
    if (!container) return;
    const update = () => {
      const rect = container.getBoundingClientRect();
      if (rect.width && rect.height) {
        setSize({ width: rect.width, height: rect.height });
        if (toolbar) {
          const box = toolbar.getBoundingClientRect();
          setToolbarBox({ x: box.left - rect.left - 4, y: box.top - rect.top - 4, width: box.width + 8, height: box.height + 8 });
        }
        if (query.data && canvas && !initializedRef.current) {
          initializedRef.current = true;
          setView(fitConstellationView(
            query.data.boundaries[field.constellation] ?? [],
            [field.centre_ra_deg, field.centre_dec_deg],
            rect.width,
            rect.height,
          ));
        }
      }
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(container);
    return () => observer.disconnect();
  }, [canvas, container, field.centre_dec_deg, field.centre_ra_deg, field.constellation, open, query.data, toolbar]);

  useEffect(() => () => cancelAnimation(), [cancelAnimation]);

  const animateTo = useCallback((target: SkyView, duration: number) => {
    cancelAnimation();
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setView(target);
      return;
    }
    const started = performance.now();
    const interpolate = interpolateView(viewRef.current, target);
    const tick = (now: number) => {
      const t = Math.min(1, (now - started) / duration);
      const eased = t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2;
      setView(interpolate(eased));
      if (t < 1) animationRef.current = requestAnimationFrame(tick);
      else animationRef.current = null;
    };
    animationRef.current = requestAnimationFrame(tick);
  }, [cancelAnimation]);

  const zoomButton = (factor: number) => animateTo(
    zoomViewAt(viewRef.current, factor, [size.width / 2, size.height / 2], size.width, size.height),
    250,
  );
  const handleKey = (event: KeyboardEvent<HTMLCanvasElement>) => {
    const amount = Math.min(size.width, size.height) * 0.1;
    let target: SkyView | null = null;
    if (event.key === "ArrowLeft") target = panViewBy(viewRef.current, amount, 0, size.width, size.height);
    else if (event.key === "ArrowRight") target = panViewBy(viewRef.current, -amount, 0, size.width, size.height);
    else if (event.key === "ArrowUp") target = panViewBy(viewRef.current, 0, amount, size.width, size.height);
    else if (event.key === "ArrowDown") target = panViewBy(viewRef.current, 0, -amount, size.width, size.height);
    else if (event.key === "+" || event.key === "=") target = zoomViewAt(viewRef.current, 2, [size.width / 2, size.height / 2], size.width, size.height);
    else if (event.key === "-" || event.key === "−") target = zoomViewAt(viewRef.current, 0.5, [size.width / 2, size.height / 2], size.width, size.height);
    else if (event.key === "Home") target = constellationView;
    if (target) {
      event.preventDefault();
      cancelAnimation();
      setView(target);
    }
  };

  const scale = scaleBarStep(pxPerDegree(view, size.width, size.height));
  // Names on the chart keep clear of the buttons and the scale bar drawn over it.
  const reserved = useMemo<Rect[]>(() => [
    ...(toolbarBox ? [toolbarBox] : []),
    { x: 10, y: size.height - 36, width: scale.px + 8, height: 26 },
  ], [scale.px, size.height, toolbarBox]);
  const buttonSx = {
    minWidth: 36,
    height: 34,
    px: "10px",
    borderRadius: "8px",
    border: `1px solid ${palette.buttonBorder}`,
    bgcolor: palette.buttonBackground,
    color: palette.buttonText,
    fontSize: 13,
    lineHeight: 1,
    textTransform: "none",
    backdropFilter: "blur(4px)",
    "&:hover": { bgcolor: palette.buttonBackground, filter: "brightness(1.08)" },
  } as const;
  const descriptionId = `sky-chart-description-${info.project_id}`;

  return (
    <Dialog
      open={open}
      onClose={onClose}
      fullScreen
      TransitionProps={{ onEntered: () => canvas?.focus() }}
    >
      <Box sx={{ display: "flex", alignItems: "center", gap: 2, minHeight: 58, px: 2, bgcolor: "background.paper" }}>
        <Box sx={{ minWidth: 0, flex: 1 }}>
          <Typography sx={{ fontSize: 16, lineHeight: 1.35, fontWeight: 600 }}>{info.name}</Typography>
          <Typography sx={{ color: "text.secondary", fontSize: 13, lineHeight: 1.35 }}>
            {headerSubtitle(info.targets.map(targetLabel), constellationName)}
          </Typography>
        </Box>
        <IconButton aria-label="Close the sky chart" onClick={onClose}><CloseIcon /></IconButton>
      </Box>

      <Box
        ref={setContainer}
        onPointerDownCapture={cancelAnimation}
        onWheelCapture={cancelAnimation}
        sx={{
          position: "relative", flex: 1, minHeight: 0, bgcolor: palette.sky,
          userSelect: "none", WebkitTouchCallout: "none",
          "& canvas:focus-visible": { outline: `2px solid ${theme.palette.primary.main}`, outlineOffset: "-2px" },
        }}
      >
        {query.data && (
          <SkyChartCanvas
            ref={setCanvas}
            data={query.data}
            view={view}
            mode="full"
            field={field}
            projectId={info.project_id}
            projectName={info.name}
            reserved={reserved}
            canvasProps={{
              role: "img",
              "aria-label": `Sky chart showing ${info.name} in ${constellationName}`,
              "aria-describedby": descriptionId,
              tabIndex: 0,
              onKeyDown: handleKey,
              style: { display: "block", width: "100%", height: "100%", touchAction: "none" },
            }}
          />
        )}
        <Box
          component="span"
          id={descriptionId}
          sx={{ position: "absolute", width: 1, height: 1, p: 0, m: -1, overflow: "hidden", clip: "rect(0 0 0 0)", whiteSpace: "nowrap", border: 0 }}
        >
          Drag or use the arrow keys to move around. Scroll, pinch, or press + and − to zoom. Press Home to return to the constellation.
        </Box>
        <Box ref={setToolbar} sx={{ position: "absolute", top: 12, right: 12, display: "flex", flexDirection: "column", alignItems: "stretch", gap: "6px" }}>
          <Button sx={buttonSx} onClick={() => animateTo(pictureView([field.centre_ra_deg, field.centre_dec_deg], pictureLongerSideDeg(field.wcs)), 650)}>Your picture</Button>
          <Button sx={buttonSx} onClick={() => animateTo(constellationView, 650)}>Constellation</Button>
          <Button sx={buttonSx} onClick={() => animateTo(wholeSkyView([field.centre_ra_deg, field.centre_dec_deg]), 650)}>Whole sky</Button>
          <Box sx={{ display: "flex", gap: "6px" }}>
            <Button aria-label="Zoom in" sx={{ ...buttonSx, flex: 1, px: 0 }} onClick={() => zoomButton(2)}>+</Button>
            <Button aria-label="Zoom out" sx={{ ...buttonSx, flex: 1, px: 0 }} onClick={() => zoomButton(0.5)}>−</Button>
          </Box>
        </Box>
        <Box sx={{ position: "absolute", left: 14, bottom: 14, color: palette.names, fontSize: 12, lineHeight: 1, pointerEvents: "none" }}>
          <Box sx={{ width: scale.px, borderTop: `2px solid ${palette.names}`, mb: "4px" }} />
          {scale.label}
        </Box>
      </Box>

      <Box sx={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: "8px 24px", minHeight: 46, px: 2, py: 1, bgcolor: "background.paper", color: "text.secondary", fontSize: 12.5 }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}><Box sx={{ width: 22, height: 12, boxSizing: "border-box", border: `1.6px solid ${palette.target}` }} />Your picture&apos;s outline (its real size and rotation)</Box>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}><Box sx={{ width: 22, borderTop: `1.6px solid ${palette.figures}` }} />Constellation lines</Box>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}><Box sx={{ width: 22, borderTop: `1.6px dashed ${palette.figureHighlight}` }} />{constellationName} boundary</Box>
      </Box>
    </Dialog>
  );
}
