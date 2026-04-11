import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import CircularProgress from "@mui/material/CircularProgress";
import FormControlLabel from "@mui/material/FormControlLabel";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import type { HistogramData } from "@/api/images";
import { fetchHistogram } from "@/api/images";
import { CHANNEL_COLORS, LUMINOSITY_COLOR } from "@/lib/channelColors";
import { monoFontFamily } from "@/theme/theme";

interface ChannelIntensity {
  name: string;
  median: number;
  mad: number;
  color: string;
}

interface Props {
  path: string;
  hdu: number;
  /** Pre-fetched histogram data — if provided, skips internal fetch. */
  histogramData?: HistogramData;
  /** When true, histogram data will be provided via prop — don't fetch independently. */
  histogramPending?: boolean;
  shadow?: number;
  midtone?: number;
  highlight?: number;
  isStretching?: boolean;
  /** Force indicator lines visible (e.g. when a slider is clicked). */
  forceShowIndicators?: boolean;
  channelIntensities?: ChannelIntensity[];
}

const INDICATOR_COLOR = "#d4993f";
const ZOOM_SELECT_COLOR = "rgba(100,160,255,0.25)";
const ZOOM_LINE_COLOR = "rgba(100,160,255,0.7)";
const CANVAS_BG = "#12141a";
const CANVAS_HEIGHT = 120;


export function Histogram({ path, hdu, histogramData, histogramPending, shadow, midtone, highlight, isStretching, forceShowIndicators, channelIntensities }: Props) {
  // Show indicator lines only while user is actively moving sliders
  const [showIndicators, setShowIndicators] = useState(false);
  const hideTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const prevPath = useRef(path);

  // Zoom state: fraction range [0..1] into the bin array
  const [zoomStart, setZoomStart] = useState(0);
  const [zoomEnd, setZoomEnd] = useState(1);
  const isZoomed = zoomStart > 0 || zoomEnd < 1;

  // Drag-to-zoom state
  const [dragging, setDragging] = useState(false);
  const [dragStartX, setDragStartX] = useState<number | null>(null);
  const [dragCurrentX, setDragCurrentX] = useState<number | null>(null);

  // Reset on image change — suppress indicators, reset zoom
  useEffect(() => {
    prevPath.current = path;
    setLogScale(false);
    setShowIndicators(false);
    setZoomStart(0);
    setZoomEnd(1);
    if (hideTimerRef.current) clearTimeout(hideTimerRef.current);
  }, [path]);

  // Track slider changes — show indicators on single-value changes
  const prevVals = useRef({ shadow, midtone, highlight });
  useEffect(() => {
    const prev = prevVals.current;
    const shadowChanged = prev.shadow !== shadow;
    const midtoneChanged = prev.midtone !== midtone;
    const highlightChanged = prev.highlight !== highlight;
    const numChanged = +shadowChanged + +midtoneChanged + +highlightChanged;
    prevVals.current = { shadow, midtone, highlight };

    if (numChanged === 0 || !isStretching) return;

    // Multiple values changing at once = reset/auto-apply, not manual slider
    if (numChanged > 1) {
      setShowIndicators(false);
      if (hideTimerRef.current) clearTimeout(hideTimerRef.current);
      return;
    }

    setShowIndicators(true);
    if (hideTimerRef.current) clearTimeout(hideTimerRef.current);
    hideTimerRef.current = setTimeout(() => setShowIndicators(false), 3000);

    return () => {
      if (hideTimerRef.current) clearTimeout(hideTimerRef.current);
    };
  }, [shadow, midtone, highlight, isStretching]);

  // Hide immediately on stretch mode change or reset
  const prevStretching = useRef(isStretching);
  useEffect(() => {
    if (prevStretching.current !== isStretching) {
      prevStretching.current = isStretching;
      setShowIndicators(false);
      if (hideTimerRef.current) clearTimeout(hideTimerRef.current);
    }
  }, [isStretching]);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [logScale, setLogScale] = useState(false);
  const [hoverX, setHoverX] = useState<number | null>(null);
  const renderedWidth = useRef(200);

  // Channel visibility — default all on
  const [visibleChannels, setVisibleChannels] = useState<Record<string, boolean>>({
    R: true, G: true, B: true, L: true, Lum: true,
  });

  const histQuery = useQuery({
    queryKey: ["histogram", path, hdu],
    queryFn: () => fetchHistogram(path, hdu),
    enabled: path !== "" && !histogramData && !histogramPending,
    staleTime: 60_000,
  });

  const data = histogramData ?? histQuery.data;

  // Redraw on container resize
  const [resizeKey, setResizeKey] = useState(0);
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setResizeKey((k) => k + 1));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  /** Convert a canvas pixel X to a fraction [0..1] within the current zoom range. */
  function canvasXToFraction(x: number): number {
    const padding = 2;
    const plotW = renderedWidth.current - padding * 2;
    return Math.max(0, Math.min(1, (x - padding) / plotW));
  }

  /** Convert a zoom-relative fraction to an absolute fraction [0..1] over all bins. */
  function zoomFractionToAbsolute(f: number): number {
    return Math.max(0, Math.min(1, zoomStart + f * (zoomEnd - zoomStart)));
  }

  // Draw histogram
  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas || !data) return;

    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    const w = Math.floor(rect.width);
    const h = CANVAS_HEIGHT;

    canvas.width = w * dpr;
    canvas.height = h * dpr;

    renderedWidth.current = w;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.scale(dpr, dpr);

    // Background
    ctx.fillStyle = CANVAS_BG;
    ctx.fillRect(0, 0, w, h);

    const totalBins = data.channels[0]?.bins.length ?? 0;
    if (totalBins === 0) return;

    // Compute visible bin range from zoom (clamp to valid indices)
    const startBin = Math.max(0, Math.floor(zoomStart * totalBins));
    const endBin = Math.min(totalBins, Math.ceil(zoomEnd * totalBins));
    const visibleBins = endBin - startBin;
    if (visibleBins <= 0) return;

    // Collect all visible bin arrays to find max for scaling
    const visibleSeries: { bins: number[]; color: string }[] = [];

    if (data.luminosity && visibleChannels.Lum) {
      visibleSeries.push({ bins: data.luminosity, color: LUMINOSITY_COLOR });
    }
    const channelOrder = [...data.channels].reverse();
    for (const ch of channelOrder) {
      if (visibleChannels[ch.name] !== false) {
        visibleSeries.push({ bins: ch.bins, color: CHANNEL_COLORS[ch.name] ?? "#888888" });
      }
    }

    // Find max bin count across ALL bins (not just zoomed range) for stable vertical scale
    let maxCount = 1;
    for (const series of visibleSeries) {
      for (const count of series.bins) {
        if (count > maxCount) maxCount = count;
      }
    }

    const transform = logScale
      ? (v: number) => (v > 0 ? Math.log10(v + 1) / Math.log10(maxCount + 1) : 0)
      : (v: number) => v / maxCount;

    const padding = 2;
    const plotW = w - padding * 2;
    const plotH = h - padding * 2;

    // Draw each series as a filled area curve (only bins in zoomed range)
    for (const series of visibleSeries) {
      const color = series.color;

      const grad = ctx.createLinearGradient(0, h - padding, 0, padding);
      grad.addColorStop(0, color + "40");
      grad.addColorStop(1, color + "18");

      ctx.beginPath();
      ctx.moveTo(padding, h - padding);

      for (let i = startBin; i < endBin; i++) {
        const x = padding + ((i - startBin) / visibleBins) * plotW;
        const y = h - padding - transform(series.bins[i]) * plotH;
        ctx.lineTo(x, y);
      }

      ctx.lineTo(padding + plotW, h - padding);
      ctx.closePath();
      ctx.fillStyle = grad;
      ctx.fill();

      // Thin top line for definition
      ctx.beginPath();
      for (let i = startBin; i < endBin; i++) {
        const x = padding + ((i - startBin) / visibleBins) * plotW;
        const y = h - padding - transform(series.bins[i]) * plotH;
        if (i === startBin) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.strokeStyle = color + "cc";
      ctx.lineWidth = 1;
      ctx.stroke();
    }

    // Stretch indicators — mapped into zoomed range
    if (showIndicators || forceShowIndicators) {
      for (const val of [shadow ?? 0, highlight ?? 1]) {
        // Map absolute [0..1] value into zoomed canvas position
        const zoomFrac = (val - zoomStart) / (zoomEnd - zoomStart);
        if (zoomFrac < 0 || zoomFrac > 1) continue;
        const x = padding + zoomFrac * plotW;
        ctx.shadowColor = INDICATOR_COLOR;
        ctx.shadowBlur = 3;
        ctx.strokeStyle = INDICATOR_COLOR;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(x, padding);
        ctx.lineTo(x, h - padding);
        ctx.stroke();
        ctx.shadowBlur = 0;
      }

      if (midtone != null) {
        const zoomFrac = (midtone - zoomStart) / (zoomEnd - zoomStart);
        if (zoomFrac >= 0 && zoomFrac <= 1) {
          const x = padding + zoomFrac * plotW;
          ctx.shadowColor = INDICATOR_COLOR;
          ctx.shadowBlur = 2;
          ctx.strokeStyle = INDICATOR_COLOR;
          ctx.lineWidth = 1;
          ctx.setLineDash([3, 3]);
          ctx.beginPath();
          ctx.moveTo(x, padding);
          ctx.lineTo(x, h - padding);
          ctx.stroke();
          ctx.setLineDash([]);
          ctx.shadowBlur = 0;
        }
      }
    }

    // Drag-to-zoom selection overlay
    if (dragging && dragStartX != null && dragCurrentX != null) {
      const left = Math.min(dragStartX, dragCurrentX);
      const right = Math.max(dragStartX, dragCurrentX);

      // Shaded selection region
      ctx.fillStyle = ZOOM_SELECT_COLOR;
      ctx.fillRect(left, padding, right - left, plotH);

      // Start and end lines
      for (const x of [dragStartX, dragCurrentX]) {
        ctx.strokeStyle = ZOOM_LINE_COLOR;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(x, padding);
        ctx.lineTo(x, h - padding);
        ctx.stroke();
      }
    }

    // Hover crosshair (only when not dragging)
    if (!dragging && hoverX !== null) {
      const x = hoverX;
      ctx.strokeStyle = "rgba(255,255,255,0.3)";
      ctx.lineWidth = 0.5;
      ctx.setLineDash([2, 2]);
      ctx.beginPath();
      ctx.moveTo(x, padding);
      ctx.lineTo(x, h - padding);
      ctx.stroke();
      ctx.setLineDash([]);
    }
  }, [data, resizeKey, logScale, visibleChannels, showIndicators, forceShowIndicators, shadow, midtone, highlight, hoverX, zoomStart, zoomEnd, dragging, dragStartX, dragCurrentX]);

  useEffect(() => {
    draw();
  }, [draw]);

  // Hover handler (suppressed during drag)
  function handleMouseMove(e: React.MouseEvent<HTMLCanvasElement>) {
    if (dragging) return; // global handler tracks drag
    const rect = canvasRef.current?.getBoundingClientRect();
    if (rect) setHoverX(e.clientX - rect.left);
  }

  function handleMouseLeave() {
    if (!dragging) setHoverX(null);
  }

  function handleMouseDown(e: React.MouseEvent<HTMLCanvasElement>) {
    if (e.button !== 0) return;
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    const x = e.clientX - rect.left;
    setDragging(true);
    setDragStartX(x);
    setDragCurrentX(x);
    setHoverX(null);
    e.preventDefault();
  }

  // Track mouse globally during drag so dragging beyond the canvas edges works
  useEffect(() => {
    if (!dragging) return;

    const clampToCanvas = (clientX: number): number => {
      const rect = canvasRef.current?.getBoundingClientRect();
      if (!rect) return 0;
      const padding = 2;
      return Math.max(padding, Math.min(clientX - rect.left, rect.width - padding));
    };

    const handleGlobalMove = (e: MouseEvent) => {
      setDragCurrentX(clampToCanvas(e.clientX));
    };

    const commitZoom = () => {
      if (dragStartX != null) {
        const finalX = dragCurrentX ?? dragStartX;
        const f1 = canvasXToFraction(dragStartX);
        const f2 = canvasXToFraction(finalX);
        if (Math.abs(f1 - f2) >= 0.02) {
          const abs1 = zoomFractionToAbsolute(Math.min(f1, f2));
          const abs2 = zoomFractionToAbsolute(Math.max(f1, f2));
          setZoomStart(abs1);
          setZoomEnd(abs2);
        }
      }
      setDragging(false);
      setDragStartX(null);
      setDragCurrentX(null);
    };

    window.addEventListener("mousemove", handleGlobalMove);
    window.addEventListener("mouseup", commitZoom);
    return () => {
      window.removeEventListener("mousemove", handleGlobalMove);
      window.removeEventListener("mouseup", commitZoom);
    };
  });

  // Compute tooltip data (only when not dragging)
  const tooltip = (() => {
    if (dragging || hoverX === null || !data) return null;
    const padding = 2;
    const plotW = renderedWidth.current - padding * 2;
    const fraction = (hoverX - padding) / plotW;
    if (fraction < 0 || fraction > 1) return null;

    // Map zoom-relative fraction to absolute
    const absFraction = zoomStart + fraction * (zoomEnd - zoomStart);
    const numBins = data.channels[0]?.bins.length ?? 256;
    const binIdx = Math.min(Math.floor(absFraction * numBins), numBins - 1);
    const value = absFraction.toFixed(3);
    const counts: { name: string; count: number; color: string }[] = [];
    for (const ch of data.channels) {
      counts.push({ name: ch.name, count: ch.bins[binIdx] ?? 0, color: CHANNEL_COLORS[ch.name] ?? "#888888" });
    }
    if (data.luminosity) {
      counts.push({ name: "Lum", count: data.luminosity[binIdx] ?? 0, color: LUMINOSITY_COLOR });
    }
    return { value, counts };
  })();

  function toggleChannel(name: string) {
    setVisibleChannels((prev) => ({ ...prev, [name]: !prev[name] }));
  }

  function resetZoom() {
    setZoomStart(0);
    setZoomEnd(1);
  }

  if (!histogramData && histQuery.isLoading) {
    return (
      <Box sx={{ px: 1.5, py: 1, display: "flex", alignItems: "center", gap: 1 }}>
        <CircularProgress size={16} sx={{ color: "text.secondary" }} />
        <Typography variant="caption" color="text.secondary">Loading histogram...</Typography>
      </Box>
    );
  }

  if (!data) return null;

  // Channel names for checkboxes
  const channelNames = data.channels.map((ch) => ch.name);
  if (data.luminosity) channelNames.push("Lum");

  const hasIntensities = channelIntensities && channelIntensities.length > 0;

  return (
    <Box sx={{ px: 1.5, py: 0.5, display: "flex", gap: 2.5 }}>
      {/* Left: histogram + controls */}
      <Box sx={{ flex: 1, minWidth: 0 }}>
      {/* Canvas */}
      <Box
        ref={containerRef}
        sx={{
          position: "relative",
          border: 1,
          borderColor: "divider",
          borderRadius: "4px",
          overflow: "hidden",
        }}
      >
        <canvas
          ref={canvasRef}
          style={{
            display: "block",
            width: "100%",
            height: CANVAS_HEIGHT,
            cursor: dragging ? "col-resize" : "crosshair",
          }}
          onMouseMove={handleMouseMove}
          onMouseLeave={handleMouseLeave}
          onMouseDown={handleMouseDown}
        />

        {/* Hover tooltip — follows cursor, flips side at midpoint (hidden during drag) */}
        {tooltip && hoverX !== null && !dragging && (
          <Box
            sx={{
              position: "absolute",
              top: 4,
              ...(hoverX < renderedWidth.current / 2
                ? { left: hoverX + 12 }
                : { left: hoverX - 12, transform: "translateX(-100%)" }),
              bgcolor: "rgba(0,0,0,0.85)",
              borderRadius: "3px",
              px: 0.75,
              py: 0.25,
              pointerEvents: "none",
              whiteSpace: "nowrap",
            }}
          >
            <Typography sx={{ fontSize: "0.65rem", fontFamily: monoFontFamily, color: "#ccc" }}>
              {tooltip.value}
            </Typography>
            {tooltip.counts.map((c) => (
              <Typography
                key={c.name}
                sx={{ fontSize: "0.65rem", fontFamily: monoFontFamily, color: c.color }}
              >
                {c.name}: {c.count.toLocaleString()}
              </Typography>
            ))}
          </Box>
        )}
      </Box>

      {/* Controls row */}
      <Box sx={{ display: "flex", alignItems: "center", mt: 0.5 }}>
        {/* Channel checkboxes — left */}
        <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0 }}>
          {channelNames.map((name) => (
            <FormControlLabel
              key={name}
              control={
                <Checkbox
                  checked={visibleChannels[name] !== false}
                  onChange={() => toggleChannel(name)}
                  size="small"
                  sx={{
                    p: 0.25,
                    color: CHANNEL_COLORS[name] ?? LUMINOSITY_COLOR,
                    "&.Mui-checked": { color: CHANNEL_COLORS[name] ?? LUMINOSITY_COLOR },
                  }}
                />
              }
              label={name}
              slotProps={{
                typography: { sx: { fontSize: "0.65rem", color: CHANNEL_COLORS[name] ?? LUMINOSITY_COLOR } },
              }}
              sx={{ mr: 0.5, ml: 0 }}
            />
          ))}
        </Box>

        <Box sx={{ flexGrow: 1 }} />

        {/* Log/Linear scale selector — center */}
        <ToggleButtonGroup
          exclusive
          size="small"
          value={logScale ? "log" : "linear"}
          onChange={(_, v) => { if (v) { setLogScale(v === "log"); } }}
        >
          <ToggleButton value="log" sx={{ fontSize: "0.65rem", py: 0.25 }}>Log</ToggleButton>
          <ToggleButton value="linear" sx={{ fontSize: "0.65rem", py: 0.25 }}>Linear</ToggleButton>
        </ToggleButtonGroup>

        <Box sx={{ flexGrow: 1 }} />

        {/* Reset zoom — right */}
        {isZoomed ? (
          <Button
            size="small"
            onClick={resetZoom}
            sx={{ fontSize: "0.6rem", py: 0, px: 0.5, minWidth: 0, textTransform: "none" }}
          >
            Reset Zoom
          </Button>
        ) : (
          <Box sx={{ width: 70 }} />
        )}
      </Box>
      </Box>

      {/* Right: channel metrics (color images only) */}
      {hasIntensities && (() => {
        const maxMedian = Math.max(...channelIntensities!.map((c) => c.median), 1e-10);
        return (
        <Box sx={{ width: 220, flexShrink: 0, display: "flex", flexDirection: "column", justifyContent: "center", gap: 1.5 }}>
          {channelIntensities!.map((ch) => (
            <Box key={ch.name} sx={{ display: "flex", alignItems: "center", gap: 1 }}>
              <Typography sx={{ fontSize: "0.7rem", fontFamily: monoFontFamily, color: ch.color, fontWeight: 600, width: 14 }}>
                {ch.name}
              </Typography>
              <Tooltip title={`Median brightness: ${ch.median < 0.01 ? ch.median.toExponential(2) : ch.median.toFixed(4)} — bars are relative to the brightest channel`} arrow>
                <Box sx={{ flex: 1, display: "flex", alignItems: "center", gap: 0.5, cursor: "help" }}>
                  <Box sx={{ flex: 1, height: 10, bgcolor: "rgba(255,255,255,0.05)", borderRadius: 1, overflow: "hidden" }}>
                    <Box sx={{ width: `${(ch.median / maxMedian) * 100}%`, height: "100%", bgcolor: ch.color, opacity: 0.6, borderRadius: 1 }} />
                  </Box>
                  <Typography sx={{ fontSize: "0.65rem", fontFamily: monoFontFamily, color: "text.secondary", width: 48, textAlign: "right", flexShrink: 0, whiteSpace: "nowrap" }}>
                    {ch.median < 0.01 ? ch.median.toExponential(1) : ch.median.toFixed(3)}
                  </Typography>
                </Box>
              </Tooltip>
            </Box>
          ))}
        </Box>
        );
      })()}
    </Box>
  );
}
