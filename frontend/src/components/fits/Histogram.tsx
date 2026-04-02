import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Checkbox from "@mui/material/Checkbox";
import FormControlLabel from "@mui/material/FormControlLabel";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
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
  shadow?: number;
  midtone?: number;
  highlight?: number;
  isStretching?: boolean;
  channelIntensities?: ChannelIntensity[];
}

const INDICATOR_COLOR = "#d4993f";
const CANVAS_BG = "#12141a";
const CANVAS_HEIGHT = 120;


export function Histogram({ path, hdu, shadow, midtone, highlight, isStretching, channelIntensities }: Props) {
  // Show indicator lines only while user is actively moving sliders
  const [showIndicators, setShowIndicators] = useState(false);
  const hideTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const userInteracting = useRef(false);
  const prevPath = useRef(path);

  // Track whether user manually toggled scale (prevents auto-override)
  const userToggledScale = useRef(false);

  // Reset on image change — suppress indicators, allow auto scale detection
  useEffect(() => {
    prevPath.current = path;
    userInteracting.current = false;
    userToggledScale.current = false;
    setShowIndicators(false);
    if (hideTimerRef.current) clearTimeout(hideTimerRef.current);
  }, [path]);

  // Set log scale based on linearity — updates until user manually toggles
  useEffect(() => {
    if (!userToggledScale.current) {
      setLogScale(isStretching !== false);
    }
  }, [isStretching]);

  // Track slider changes — only after user has started interacting
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

    // Ignore the first few changes after image load (auto-STF settling)
    if (!userInteracting.current) {
      const stabilizeTimer = setTimeout(() => { userInteracting.current = true; }, 500);
      return () => clearTimeout(stabilizeTimer);
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
      userInteracting.current = false;
      if (hideTimerRef.current) clearTimeout(hideTimerRef.current);
      // Re-enable interaction detection after mode switch settles
      const timer = setTimeout(() => { userInteracting.current = true; }, 500);
      return () => clearTimeout(timer);
    }
  }, [isStretching]);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [logScale, setLogScale] = useState(true);
  const [hoverX, setHoverX] = useState<number | null>(null);
  const renderedWidth = useRef(200);

  // Channel visibility — default all on
  const [visibleChannels, setVisibleChannels] = useState<Record<string, boolean>>({
    R: true, G: true, B: true, L: true, Lum: true,
  });

  const histQuery = useQuery({
    queryKey: ["histogram", path, hdu],
    queryFn: () => fetchHistogram(path, hdu),
    enabled: path !== "",
    staleTime: 60_000,
  });

  const data = histQuery.data;

  // Redraw on container resize
  const [resizeKey, setResizeKey] = useState(0);
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setResizeKey((k) => k + 1));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Draw histogram
  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas || !data) return;

    const dpr = window.devicePixelRatio || 1;
    // Use the actual rendered size of the canvas element
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

    const bins = data.channels[0]?.bins.length ?? 0;
    if (bins === 0) return;

    // Collect all visible bin arrays to find max for scaling
    const visibleSeries: { bins: number[]; color: string }[] = [];

    if (data.luminosity && visibleChannels.Lum) {
      visibleSeries.push({ bins: data.luminosity, color: LUMINOSITY_COLOR });
    }
    // Render order: Lum (back) → B → G → R (front)
    const channelOrder = [...data.channels].reverse();
    for (const ch of channelOrder) {
      if (visibleChannels[ch.name] !== false) {
        visibleSeries.push({ bins: ch.bins, color: CHANNEL_COLORS[ch.name] ?? "#888" });
      }
    }

    // Find max bin count across all visible series
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

    // Draw each series as a filled area curve
    for (const series of visibleSeries) {
      const color = series.color;

      // Create gradient fill: ~25% opacity at baseline → ~10% at peaks
      const grad = ctx.createLinearGradient(0, h - padding, 0, padding);
      grad.addColorStop(0, color + "40"); // 25% at baseline
      grad.addColorStop(1, color + "18"); // 10% at peaks

      ctx.beginPath();
      ctx.moveTo(padding, h - padding);

      for (let i = 0; i < bins; i++) {
        const x = padding + (i / bins) * plotW;
        const y = h - padding - transform(series.bins[i]) * plotH;
        ctx.lineTo(x, y);
      }

      // Close the path back to baseline
      ctx.lineTo(padding + plotW, h - padding);
      ctx.closePath();
      ctx.fillStyle = grad;
      ctx.fill();

      // Thin top line for definition
      ctx.beginPath();
      for (let i = 0; i < bins; i++) {
        const x = padding + (i / bins) * plotW;
        const y = h - padding - transform(series.bins[i]) * plotH;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.strokeStyle = color + "cc";
      ctx.lineWidth = 1;
      ctx.stroke();
    }

    // Stretch indicators — all three shown while any slider is being moved
    if (showIndicators) {
      // Shadow and highlight: solid amber lines
      for (const val of [shadow ?? 0, highlight ?? 1]) {
        const x = padding + val * plotW;
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

      // Midtone: dashed amber line
      if (midtone != null) {
        const x = padding + midtone * plotW;
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

    // Hover crosshair
    if (hoverX !== null) {
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
  }, [data, resizeKey, logScale, visibleChannels, showIndicators, shadow, midtone, highlight, hoverX]);

  useEffect(() => {
    draw();
  }, [draw]);

  // Hover handler
  function handleMouseMove(e: React.MouseEvent<HTMLCanvasElement>) {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (rect) setHoverX(e.clientX - rect.left);
  }

  function handleMouseLeave() {
    setHoverX(null);
  }

  // Compute tooltip data
  const tooltip = (() => {
    if (hoverX === null || !data) return null;
    const padding = 2;
    const plotW = renderedWidth.current - padding * 2;
    const fraction = (hoverX - padding) / plotW;
    if (fraction < 0 || fraction > 1) return null;
    const numBins = data.channels[0]?.bins.length ?? 256;
    const binIdx = Math.min(Math.floor(fraction * numBins), numBins - 1);
    const value = fraction.toFixed(3);
    const counts: { name: string; count: number; color: string }[] = [];
    for (const ch of data.channels) {
      counts.push({ name: ch.name, count: ch.bins[binIdx] ?? 0, color: CHANNEL_COLORS[ch.name] ?? "#888" });
    }
    if (data.luminosity) {
      counts.push({ name: "Lum", count: data.luminosity[binIdx] ?? 0, color: LUMINOSITY_COLOR });
    }
    return { value, counts };
  })();

  function toggleChannel(name: string) {
    setVisibleChannels((prev) => ({ ...prev, [name]: !prev[name] }));
  }

  if (histQuery.isLoading) {
    return (
      <Box sx={{ px: 1.5, py: 1 }}>
        <Typography variant="caption" color="text.secondary">Loading histogram…</Typography>
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
      <Box sx={{ flex: 2, minWidth: 0 }}>
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
          style={{ display: "block", width: "100%", height: CANVAS_HEIGHT, cursor: "crosshair" }}
          onMouseMove={handleMouseMove}
          onMouseLeave={handleMouseLeave}
        />

        {/* Hover tooltip — follows cursor, flips side at midpoint */}
        {tooltip && hoverX !== null && (
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
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mt: 0.5 }}>
        {/* Channel checkboxes */}
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

        {/* Log/Linear scale selector */}
        <Box sx={{ display: "flex", gap: 0.5 }}>
          {(["Log", "Linear"] as const).map((label) => {
            const active = label === "Log" ? logScale : !logScale;
            return (
              <Typography
                key={label}
                component="button"
                onClick={() => { userToggledScale.current = true; setLogScale(label === "Log"); }}
                sx={{
                  fontSize: "0.65rem",
                  color: active ? "text.primary" : "text.secondary",
                  fontWeight: active ? 600 : 400,
                  cursor: active ? "default" : "pointer",
                  border: "none",
                  bgcolor: "transparent",
                  textDecoration: active ? "none" : "underline",
                  fontFamily: "inherit",
                  p: 0,
                  "&:hover": active ? {} : { color: "text.primary" },
                }}
              >
                {label}
              </Typography>
            );
          })}
        </Box>
      </Box>
      </Box>

      {/* Right: channel metrics (color images only) */}
      {hasIntensities && (() => {
        const maxMedian = Math.max(...channelIntensities!.map((c) => c.median), 1e-10);
        return (
        <Box sx={{ width: 180, display: "flex", flexDirection: "column", justifyContent: "center", gap: 1.5 }}>
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
                  <Typography sx={{ fontSize: "0.65rem", fontFamily: monoFontFamily, color: "text.secondary", width: 36, textAlign: "right", flexShrink: 0 }}>
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
