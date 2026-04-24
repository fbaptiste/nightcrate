/**
 * PHD2 time-series chart.
 *
 * Layout follows the PHD2 / PHDLogViewer convention:
 *
 * - One main chart area with *dual y-axes*. Left axis shows the RA/Dec
 *   raw distance (pixels); right axis shows the guide-pulse duration
 *   (milliseconds). Both scales are zero-aligned to the same horizontal
 *   line so a W pulse (positive RA correction) prints above zero along
 *   with any positive star deflection, and an E pulse prints below.
 * - Separate SNR + star-mass sub-panels underneath — these aren't in
 *   PHD2's live graph but PHDLogViewer stacks them the same way and
 *   they give useful context for diagnosing lost-star events.
 * - User-adjustable Y range for the left axis: a small numeric input in
 *   the toolbar lets the user clamp the axis to e.g. ±2 px to see
 *   small-scale jitter, at the cost of clipping large excursions. PHD2
 *   allows this as well.
 *
 * Null values break the line — DROP frames and missing fields must
 * never visually interpolate to zero (the parser's quiet-correctness
 * contract).
 */
import { useEffect, useMemo, useRef, useState } from "react";
import * as d3 from "d3";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import RestartAltIcon from "@mui/icons-material/RestartAlt";
import { useTheme } from "@mui/material/styles";
import type { GuidingSample, LogEvent } from "@/api/phd2";
import { formatWallClock } from "@/lib/phd2Format";
import { RIG_BLUE, RIG_ORANGE } from "@/lib/rigColors";

interface Props {
  samples: GuidingSample[];
  /** Section's INFO events — only ``dither`` events are rendered on
   *  the chart. Pass-through from the parsed section. */
  events?: LogEvent[];
  /** Section start timestamp (naive ISO local) — used to render
   *  X-axis tick labels + cursor tooltip as wall-clock. */
  startIso?: string;
  height?: number;
}

const COLOR_RA = RIG_BLUE;
const COLOR_DEC = RIG_ORANGE;

const MARGIN = { top: 16, right: 56, bottom: 40, left: 56 };
const MAIN_H_RATIO = 0.7;
const SNR_H_RATIO = 0.14;
const MASS_H_RATIO = 0.16;
const PANEL_GAP = 18;

interface HoverInfo {
  xPx: number;
  time: number;
  frame: number | null;
  raRaw: number | null;
  decRaw: number | null;
  raDuration: number | null;
  raDirection: "W" | "E" | null;
  decDuration: number | null;
  decDirection: "N" | "S" | null;
  snr: number | null;
  starMass: number | null;
  /** Non-null when the cursor magnetically snapped to a dither marker
   *  — crosshair paints blue + the tooltip shows Δx/Δy from the event. */
  dither: LogEvent | null;
}

/** Pixel radius within which the cursor snaps to a dither marker. */
const DITHER_SNAP_PX = 8;

export default function TimeSeriesChart({
  samples,
  events = [],
  startIso,
  height = 440,
}: Props) {
  const theme = useTheme();
  const isDark = theme.palette.mode === "dark";
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [width, setWidth] = useState(640);
  const [zoomX, setZoomX] = useState<[number, number] | null>(null);
  const [hover, setHover] = useState<HoverInfo | null>(null);
  // User-adjustable Y range for the main panel. Empty string = auto-fit
  // (domain derived from the data); a positive number clamps to ±value.
  const [yMaxInput, setYMaxInput] = useState<string>("");
  // ``ready`` guards against the first-paint flash where the SVG
  // renders at the default width=640 before the ResizeObserver fires
  // — the pulse bars briefly landed at wrong positions. We show a
  // spinner until the first width measurement lands, then the full
  // chart swaps in.
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!wrapperRef.current) return;
    const obs = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width ?? 640;
      if (w > 0) {
        setWidth(w);
        setReady(true);
      }
    });
    obs.observe(wrapperRef.current);
    return () => obs.disconnect();
  }, []);

  // Panel rectangles.
  const innerW = Math.max(100, width - MARGIN.left - MARGIN.right);
  const innerH = height - MARGIN.top - MARGIN.bottom;
  const mainH = innerH * MAIN_H_RATIO - PANEL_GAP;
  const snrH = innerH * SNR_H_RATIO - PANEL_GAP;
  const massH = innerH * MASS_H_RATIO;
  const mainY0 = MARGIN.top;
  const snrY0 = mainY0 + mainH + PANEL_GAP;
  const massY0 = snrY0 + snrH + PANEL_GAP;

  // Scales.
  const { xScale, yDistScale, yPulseScale, ySnrScale, yMassScale } = useMemo(() => {
    const times = samples.map((s) => s.time_seconds);
    const tmin = times.length ? times[0] : 0;
    const tmax = times.length ? times[times.length - 1] : 1;

    const distVals = samples.flatMap((s) =>
      [s.ra_raw_px, s.dec_raw_px].filter((v): v is number => v !== null),
    );
    const autoMaxAbs = distVals.length
      ? Math.max(1.0, d3.max(distVals.map((v) => Math.abs(v))) ?? 1.0)
      : 1.0;
    const parsedMax = parseFloat(yMaxInput);
    const maxAbs =
      Number.isFinite(parsedMax) && parsedMax > 0 ? parsedMax : autoMaxAbs * 1.1;

    // Pulse axis range — scoped to the samples in the current X zoom
    // so panning to a quieter region shrinks the scale. Uses the 75th
    // percentile rather than the absolute max so the typical pulse
    // fills most of the panel; larger outliers clip off the top / bottom
    // rather than flattening all the other bars.  Combined with the
    // min-bar-height floor below, this keeps pulses distinctly visible
    // regardless of zoom level.
    const visibleSamples = zoomX
      ? samples.filter(
          (s) => s.time_seconds >= zoomX[0] && s.time_seconds <= zoomX[1],
        )
      : samples;
    const visibleDurations = visibleSamples.flatMap((s) =>
      [s.ra_duration_ms ?? 0, s.dec_duration_ms ?? 0].filter((v) => v > 0),
    );
    const sortedDur = [...visibleDurations].sort((a, b) => a - b);
    const p75 = sortedDur[Math.floor(sortedDur.length * 0.75)] ?? 100;
    const durMax = Math.max(100, p75);

    const snrs = samples.map((s) => s.snr).filter((v): v is number => v !== null);
    const snrMax = snrs.length ? Math.max(10, d3.max(snrs) ?? 10) : 10;
    const masses = samples.map((s) => s.star_mass).filter((v): v is number => v !== null);
    const massMax = masses.length ? d3.max(masses) ?? 1 : 1;

    const domain = zoomX ?? [tmin, tmax];
    return {
      xScale: d3
        .scaleLinear()
        .domain(domain)
        .range([MARGIN.left, MARGIN.left + innerW]),
      // Both dist + pulse scales share the same pixel range and zero
      // line. The pulse domain is ±durMax so a 500 ms W pulse prints
      // at the top of the main area when durMax = 500.
      yDistScale: d3
        .scaleLinear()
        .domain([-maxAbs, maxAbs])
        .range([mainY0 + mainH, mainY0]),
      yPulseScale: d3
        .scaleLinear()
        .domain([-durMax, durMax])
        .range([mainY0 + mainH, mainY0]),
      ySnrScale: d3
        .scaleLinear()
        .domain([0, snrMax * 1.1])
        .range([snrY0 + snrH, snrY0]),
      yMassScale: d3
        .scaleLinear()
        .domain([0, massMax * 1.1])
        .range([massY0 + massH, massY0]),
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [samples, width, height, zoomX, yMaxInput, innerW, mainH, snrH, massH]);

  // D3 zoom (X axis only).
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const [x0, x1] = d3.extent(samples, (s) => s.time_seconds) as [number, number];
    if (x0 === undefined || x1 === undefined) return;
    const base = d3.scaleLinear().domain([x0, x1]).range([MARGIN.left, MARGIN.left + innerW]);
    const zoom = d3
      .zoom<SVGSVGElement, unknown>()
      .scaleExtent([1, 50])
      .translateExtent([
        [MARGIN.left, 0],
        [MARGIN.left + innerW, height],
      ])
      .extent([
        [MARGIN.left, 0],
        [MARGIN.left + innerW, height],
      ])
      .on("zoom", (e) => {
        const rescaled = e.transform.rescaleX(base);
        setZoomX(rescaled.domain() as [number, number]);
      });
    d3.select(svg).call(zoom);
    return () => {
      d3.select(svg).on(".zoom", null);
    };
  }, [samples, width, height, innerW]);

  // Line generators — `.defined()` breaks the line on nulls (DROP frames).
  const raLine = useMemo(
    () =>
      d3
        .line<GuidingSample>()
        .defined((s) => s.ra_raw_px !== null)
        .x((s) => xScale(s.time_seconds))
        .y((s) => yDistScale(s.ra_raw_px ?? 0)),
    [xScale, yDistScale],
  );
  const decLine = useMemo(
    () =>
      d3
        .line<GuidingSample>()
        .defined((s) => s.dec_raw_px !== null)
        .x((s) => xScale(s.time_seconds))
        .y((s) => yDistScale(s.dec_raw_px ?? 0)),
    [xScale, yDistScale],
  );
  const snrLine = useMemo(
    () =>
      d3
        .line<GuidingSample>()
        .defined((s) => s.snr !== null)
        .x((s) => xScale(s.time_seconds))
        .y((s) => ySnrScale(s.snr ?? 0)),
    [xScale, ySnrScale],
  );
  const massLine = useMemo(
    () =>
      d3
        .line<GuidingSample>()
        .defined((s) => s.star_mass !== null)
        .x((s) => xScale(s.time_seconds))
        .y((s) => yMassScale(s.star_mass ?? 0)),
    [xScale, yMassScale],
  );

  // Pulse bars — one rect per non-zero pulse per axis. Drawn before the
  // traces so lines render on top. Color matches the axis (RA blue, Dec
  // orange). Fill opacity is low so the trace remains the dominant signal.
  const pulseBars = useMemo(() => {
    if (samples.length < 2) return { ra: [], dec: [] };
    // Bar width scales with the number of VISIBLE samples after zoom
    // (not the full sample count). A session zoomed in to 200 samples
    // gets wider bars than the full 7 500-sample view; at full zoom
    // the floor of 3 px keeps bars readable even when 7 500 samples
    // share 1 200 px.
    const visibleCount = zoomX
      ? samples.filter((s) => s.time_seconds >= zoomX[0] && s.time_seconds <= zoomX[1]).length
      : samples.length;
    const nSamples = Math.max(1, visibleCount);
    const barW = Math.max(3, Math.min(10, (innerW / nSamples) * 0.6));
    // Every non-zero pulse gets at least this much vertical presence so
    // small pulses remain visible even when the scale is set for larger
    // ones. Bars that would exceed the main panel clip at ±mainH/2.
    const minH = 5;
    const panelHalf = mainH / 2;
    const y0 = yPulseScale(0);
    const ra: Array<{ x: number; y: number; h: number }> = [];
    const dec: Array<{ x: number; y: number; h: number }> = [];
    for (const s of samples) {
      const cx = xScale(s.time_seconds);
      const raDur = s.ra_duration_ms ?? 0;
      const decDur = s.dec_duration_ms ?? 0;
      if (raDur > 0 && s.ra_direction) {
        const sign = s.ra_direction === "W" ? 1 : -1;
        const rawH = Math.abs(yPulseScale(sign * raDur) - y0);
        const h = Math.min(panelHalf, Math.max(minH, rawH));
        ra.push({
          x: cx - barW / 2,
          y: sign > 0 ? y0 - h : y0,
          h,
        });
      }
      if (decDur > 0 && s.dec_direction) {
        const sign = s.dec_direction === "N" ? 1 : -1;
        const rawH = Math.abs(yPulseScale(sign * decDur) - y0);
        const h = Math.min(panelHalf, Math.max(minH, rawH));
        dec.push({
          x: cx - barW / 2,
          y: sign > 0 ? y0 - h : y0,
          h,
        });
      }
    }
    return { ra, dec, barW };
  }, [samples, xScale, yPulseScale, innerW, zoomX, mainH]);

  const gridColor = isDark ? "rgba(255,255,255,0.08)" : "rgba(0,0,0,0.08)";
  const axisColor = isDark ? "rgba(255,255,255,0.6)" : "rgba(0,0,0,0.6)";
  const textColor = isDark ? "rgba(255,255,255,0.87)" : "rgba(0,0,0,0.87)";

  const distTicks = yDistScale.ticks(5);
  const pulseTicks = yPulseScale.ticks(5);
  const snrTicks = ySnrScale.ticks(2);
  const massTicks = yMassScale.ticks(2);

  function handleMouseMove(e: React.MouseEvent<SVGSVGElement>) {
    if (samples.length === 0) return;
    const svg = e.currentTarget;
    const rect = svg.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    if (mx < MARGIN.left || mx > MARGIN.left + innerW) {
      setHover(null);
      return;
    }

    // Magnetic snap to dither markers — when the cursor is within
    // DITHER_SNAP_PX of a dither's X, grab that dither. Lets Fred
    // read each dither's Δx/Δy cleanly without pixel-perfect mousing.
    let snapDither: LogEvent | null = null;
    let snapTime: number | null = null;
    let bestDist = DITHER_SNAP_PX + 0.5;
    for (const ev of events) {
      if (ev.kind !== "dither" || ev.time_seconds == null) continue;
      const ex = xScale(ev.time_seconds);
      if (ex < MARGIN.left || ex > MARGIN.left + innerW) continue;
      const d = Math.abs(mx - ex);
      if (d < bestDist) {
        snapDither = ev;
        snapTime = ev.time_seconds;
        bestDist = d;
      }
    }

    const t = snapTime ?? xScale.invert(mx);
    const bisector = d3.bisector((s: GuidingSample) => s.time_seconds).center;
    const idx = bisector(samples, t);
    const s = samples[Math.max(0, Math.min(samples.length - 1, idx))];
    setHover({
      xPx: snapTime !== null ? xScale(snapTime) : xScale(s.time_seconds),
      time: s.time_seconds,
      frame: s.frame,
      raRaw: s.ra_raw_px,
      decRaw: s.dec_raw_px,
      raDuration: s.ra_duration_ms,
      raDirection: s.ra_direction,
      decDuration: s.dec_duration_ms,
      decDirection: s.dec_direction,
      snr: s.snr,
      starMass: s.star_mass,
      dither: snapDither,
    });
  }

  function handleReset() {
    setZoomX(null);
    if (svgRef.current) {
      d3.select(svgRef.current).call(
        d3.zoom<SVGSVGElement, unknown>().transform,
        d3.zoomIdentity,
      );
    }
  }

  if (samples.length === 0) {
    return (
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          height,
          color: "text.secondary",
        }}
      >
        <Typography variant="body2">No guiding samples to display.</Typography>
      </Box>
    );
  }

  return (
    <Box ref={wrapperRef} sx={{ position: "relative", width: "100%" }}>
      <Stack direction="row" spacing={2} alignItems="center" sx={{ pb: 0.5 }}>
        <Stack direction="row" spacing={0.5} alignItems="center">
          <Box sx={{ width: 14, height: 2, bgcolor: COLOR_RA }} />
          <Typography variant="caption" sx={{ color: COLOR_RA }}>
            RA
          </Typography>
        </Stack>
        <Stack direction="row" spacing={0.5} alignItems="center">
          <Box sx={{ width: 14, height: 2, bgcolor: COLOR_DEC }} />
          <Typography variant="caption" sx={{ color: COLOR_DEC }}>
            Dec
          </Typography>
        </Stack>
        <Stack direction="row" spacing={0.5} alignItems="center">
          <Box sx={{ width: 6, height: 10, bgcolor: COLOR_RA, opacity: 0.6 }} />
          <Typography variant="caption" sx={{ color: COLOR_RA }}>
            RA pulse
          </Typography>
        </Stack>
        <Stack direction="row" spacing={0.5} alignItems="center">
          <Box sx={{ width: 6, height: 10, bgcolor: COLOR_DEC, opacity: 0.6 }} />
          <Typography variant="caption" sx={{ color: COLOR_DEC }}>
            Dec pulse
          </Typography>
        </Stack>
        {events.some((e) => e.kind === "dither") && (
          <Stack direction="row" spacing={0.5} alignItems="center">
            <svg width={12} height={10} style={{ display: "block" }}>
              <path d="M 1,1 L 11,1 L 6,9 Z" fill={COLOR_RA} />
            </svg>
            <Typography variant="caption" sx={{ color: "text.secondary" }}>
              Dither
            </Typography>
          </Stack>
        )}
        <Box sx={{ flex: 1 }} />
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ fontStyle: "italic" }}
        >
          Scroll to zoom · drag to pan
        </Typography>
        <TextField
          label="Y max"
          size="small"
          value={yMaxInput}
          onChange={(e) => setYMaxInput(e.target.value)}
          placeholder="auto"
          inputProps={{
            inputMode: "decimal",
            style: { width: 48, textAlign: "right" },
          }}
          sx={{ "& .MuiInputBase-root": { fontSize: 12 } }}
        />
        <Button
          size="small"
          startIcon={<RestartAltIcon />}
          onClick={handleReset}
          disabled={zoomX === null}
        >
          Reset X zoom
        </Button>
      </Stack>
      {!ready && (
        <Box
          sx={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            height,
          }}
        >
          <CircularProgress size={28} />
        </Box>
      )}
      <svg
        ref={svgRef}
        width={width}
        height={height}
        onMouseMove={handleMouseMove}
        onMouseLeave={() => setHover(null)}
        style={{
          display: ready ? "block" : "none",
          // ``grab`` by default signals "drag to pan" (works when
          // zoomed in). Crosshair would also be reasonable but
          // users need a visual cue that the chart is draggable.
          // ``touch-action: none`` prevents the browser from
          // stealing wheel / touch gestures before d3.zoom sees them.
          cursor: zoomX ? "grab" : "crosshair",
          touchAction: "none",
        }}
      >
        {/* Subtle background tint on alternating panels for visual
            separation between main / SNR / mass. */}
        <rect
          x={MARGIN.left}
          y={snrY0}
          width={innerW}
          height={snrH}
          fill={isDark ? "rgba(255,255,255,0.03)" : "rgba(0,0,0,0.03)"}
        />
        <rect
          x={MARGIN.left}
          y={massY0}
          width={innerW}
          height={massH}
          fill={isDark ? "rgba(255,255,255,0.05)" : "rgba(0,0,0,0.05)"}
        />

        {/* Main panel gridlines (left axis) */}
        {distTicks.map((t) => (
          <line
            key={`gm-${t}`}
            x1={MARGIN.left}
            x2={MARGIN.left + innerW}
            y1={yDistScale(t)}
            y2={yDistScale(t)}
            stroke={gridColor}
          />
        ))}
        {/* Main panel zero axis */}
        <line
          x1={MARGIN.left}
          x2={MARGIN.left + innerW}
          y1={yDistScale(0)}
          y2={yDistScale(0)}
          stroke={axisColor}
          strokeWidth={1}
        />

        {/* Pulse bars — drawn BEFORE traces so lines paint on top. */}
        {pulseBars.ra.map((b, i) => (
          <rect
            key={`rab-${i}`}
            x={b.x}
            y={b.y}
            width={pulseBars.barW}
            height={b.h}
            fill={COLOR_RA}
            opacity={0.6}
          />
        ))}
        {pulseBars.dec.map((b, i) => (
          <rect
            key={`decb-${i}`}
            x={b.x}
            y={b.y}
            width={pulseBars.barW}
            height={b.h}
            fill={COLOR_DEC}
            opacity={0.6}
          />
        ))}

        {/* Main traces */}
        <path
          d={raLine(samples) ?? undefined}
          fill="none"
          stroke={COLOR_RA}
          strokeWidth={1.3}
        />
        <path
          d={decLine(samples) ?? undefined}
          fill="none"
          stroke={COLOR_DEC}
          strokeWidth={1.3}
        />

        {/* Dither markers — downward triangles in the top margin. */}
        {events
          .filter((e) => e.kind === "dither" && e.time_seconds != null)
          .map((e) => {
            const cx = xScale(e.time_seconds as number);
            if (cx < MARGIN.left - 4 || cx > MARGIN.left + innerW + 4) return null;
            const topY = MARGIN.top - 9;
            const apexY = MARGIN.top - 1;
            const dx = e.parsed_fields.dx ?? "?";
            const dy = e.parsed_fields.dy ?? "?";
            return (
              <path
                key={`dither-${e.time_seconds}`}
                d={`M ${cx - 5},${topY} L ${cx + 5},${topY} L ${cx},${apexY} Z`}
                fill={COLOR_RA}
                stroke={COLOR_RA}
                strokeWidth={0.5}
              >
                <title>{`Dither at ${(e.time_seconds as number).toFixed(1)}s · Δx=${dx}, Δy=${dy} px`}</title>
              </path>
            );
          })}

        {/* Left-axis ticks (distance, px) */}
        {distTicks.map((t) => (
          <text
            key={`yt-${t}`}
            x={MARGIN.left - 6}
            y={yDistScale(t)}
            fill={textColor}
            fontSize={10}
            textAnchor="end"
            dominantBaseline="central"
          >
            {t.toFixed(1)}
          </text>
        ))}
        <text
          x={MARGIN.left + 4}
          y={mainY0 + 12}
          fill={textColor}
          fillOpacity={0.7}
          fontSize={11}
          fontWeight={600}
          textAnchor="start"
        >
          Guide error (px)
        </text>

        {/* Right-axis ticks (pulse duration, ms) */}
        {pulseTicks.map((t) => (
          <text
            key={`pt-${t}`}
            x={MARGIN.left + innerW + 6}
            y={yPulseScale(t)}
            fill={textColor}
            fillOpacity={0.6}
            fontSize={10}
            textAnchor="start"
            dominantBaseline="central"
          >
            {t}
          </text>
        ))}
        <text
          x={MARGIN.left + innerW - 4}
          y={mainY0 + 12}
          fill={textColor}
          fillOpacity={0.7}
          fontSize={11}
          fontWeight={600}
          textAnchor="end"
        >
          Pulses (ms)
        </text>

        {/* SNR panel */}
        <line
          x1={MARGIN.left}
          x2={MARGIN.left + innerW}
          y1={snrY0 + snrH}
          y2={snrY0 + snrH}
          stroke={axisColor}
        />
        <path
          d={snrLine(samples) ?? undefined}
          fill="none"
          stroke={axisColor}
          strokeWidth={1}
          opacity={0.7}
        />
        {snrTicks.map((t) => (
          <text
            key={`st-${t}`}
            x={MARGIN.left - 6}
            y={ySnrScale(t)}
            fill={textColor}
            fontSize={9}
            textAnchor="end"
            dominantBaseline="central"
          >
            {t}
          </text>
        ))}
        <text
          x={MARGIN.left + 4}
          y={snrY0 + 12}
          fill={textColor}
          fillOpacity={0.7}
          fontSize={11}
          fontWeight={600}
          textAnchor="start"
        >
          Star SNR
        </text>

        {/* Mass panel */}
        <line
          x1={MARGIN.left}
          x2={MARGIN.left + innerW}
          y1={massY0 + massH}
          y2={massY0 + massH}
          stroke={axisColor}
        />
        <path
          d={massLine(samples) ?? undefined}
          fill="none"
          stroke={axisColor}
          strokeWidth={1}
          opacity={0.5}
        />
        {massTicks.map((t) => (
          <text
            key={`mt-${t}`}
            x={MARGIN.left - 6}
            y={yMassScale(t)}
            fill={textColor}
            fontSize={9}
            textAnchor="end"
            dominantBaseline="central"
          >
            {t >= 1000 ? `${Math.round(t / 1000)}k` : t}
          </text>
        ))}
        <text
          x={MARGIN.left + 4}
          y={massY0 + 12}
          fill={textColor}
          fillOpacity={0.7}
          fontSize={11}
          fontWeight={600}
          textAnchor="start"
        >
          Star mass (ADU)
        </text>

        {/* X-axis bottom */}
        <line
          x1={MARGIN.left}
          x2={MARGIN.left + innerW}
          y1={massY0 + massH}
          y2={massY0 + massH}
          stroke={axisColor}
        />
        {(() => {
          const [t0, t1] = xScale.domain() as [number, number];
          const domainSpan = t1 - t0;
          // Fewer ticks for short (<1 min) sections so labels don't
          // overlap, more for wider ranges.
          const tickCount = domainSpan < 60 ? 5 : 8;
          return xScale.ticks(tickCount).map((t) => (
            <g key={`xt-${t}`}>
              <line
                x1={xScale(t)}
                x2={xScale(t)}
                y1={massY0 + massH}
                y2={massY0 + massH + 4}
                stroke={axisColor}
              />
              <text
                x={xScale(t)}
                y={massY0 + massH + 16}
                fill={textColor}
                fontSize={10}
                textAnchor="middle"
              >
                {formatXTick(t, startIso, domainSpan)}
              </text>
            </g>
          ));
        })()}
        <text
          x={MARGIN.left + innerW / 2}
          y={height - 6}
          fill={textColor}
          fontSize={10}
          textAnchor="middle"
        >
          {startIso ? "time (local)" : "elapsed (s)"}
        </text>

        {/* Crosshair — paints solid blue when snapped to a dither. */}
        {hover && (
          <g pointerEvents="none">
            <line
              x1={hover.xPx}
              x2={hover.xPx}
              y1={MARGIN.top}
              y2={massY0 + massH}
              stroke={hover.dither ? COLOR_RA : axisColor}
              strokeDasharray={hover.dither ? undefined : "3 3"}
              opacity={hover.dither ? 0.85 : 0.7}
            />
          </g>
        )}
      </svg>
      {hover && (
        <Box
          sx={{
            position: "absolute",
            top: 40,
            right: 8,
            p: 1,
            bgcolor: "background.paper",
            border: "1px solid",
            borderColor: "divider",
            borderRadius: 1,
            fontSize: 12,
            minWidth: 180,
            pointerEvents: "none",
          }}
        >
          <Typography variant="caption" sx={{ display: "block", fontWeight: 600 }}>
            Frame {hover.frame ?? "?"} ·{" "}
            {startIso ? `${formatWallClock(startIso, hover.time)} · ` : ""}
            {hover.time.toFixed(2)} s
          </Typography>
          <Typography variant="caption" sx={{ display: "block", color: COLOR_RA }}>
            RA: {formatPx(hover.raRaw)} px
            {hover.raDuration !== null && hover.raDuration > 0
              ? ` · ${hover.raDuration} ms ${hover.raDirection ?? ""}`
              : ""}
          </Typography>
          <Typography variant="caption" sx={{ display: "block", color: COLOR_DEC }}>
            Dec: {formatPx(hover.decRaw)} px
            {hover.decDuration !== null && hover.decDuration > 0
              ? ` · ${hover.decDuration} ms ${hover.decDirection ?? ""}`
              : ""}
          </Typography>
          <Typography variant="caption" sx={{ display: "block" }}>
            SNR: {hover.snr?.toFixed(1) ?? "—"} · mass: {hover.starMass ?? "—"}
          </Typography>
          {hover.dither && (
            <Typography
              variant="caption"
              sx={{
                display: "block",
                mt: 0.5,
                pt: 0.5,
                borderTop: 1,
                borderColor: "divider",
                color: COLOR_RA,
                fontWeight: 600,
              }}
            >
              Dither · Δx={hover.dither.parsed_fields.dx ?? "?"}, Δy=
              {hover.dither.parsed_fields.dy ?? "?"} px
            </Typography>
          )}
        </Box>
      )}
    </Box>
  );
}

function formatPx(v: number | null): string {
  if (v === null) return "—";
  return v.toFixed(3);
}

function formatXTick(
  elapsedSec: number,
  startIso: string | undefined,
  domainSpanSec: number,
): string {
  // Short sections (≤ 5 min visible) get HH:MM:SS so seconds aren't
  // lost; longer views show HH:MM so the bar doesn't cram.
  const showSeconds = domainSpanSec <= 300;
  if (!startIso) {
    if (elapsedSec < 60) return `${Math.round(elapsedSec)}s`;
    const m = Math.floor(elapsedSec / 60);
    const s = Math.round(elapsedSec - m * 60);
    return `${m}m${String(s).padStart(2, "0")}`;
  }
  const start = new Date(startIso);
  if (Number.isNaN(start.getTime())) return `${Math.round(elapsedSec)}s`;
  const dt = new Date(start.getTime() + elapsedSec * 1000);
  const hh = String(dt.getHours()).padStart(2, "0");
  const mm = String(dt.getMinutes()).padStart(2, "0");
  if (showSeconds) {
    const ss = String(dt.getSeconds()).padStart(2, "0");
    return `${hh}:${mm}:${ss}`;
  }
  return `${hh}:${mm}`;
}
