/**
 * PHD2 guiding time-series chart.
 *
 * D3 + SVG. X axis: elapsed seconds from section start (wall-clock toggle
 * lands in Pass B). Y axis: RA + Dec raw distance in pixels. Below the main
 * traces: correction-duration bars encoding direction via sign. Two
 * stacked sub-panels for SNR and StarMass. Crosshair cursor with all-trace
 * readouts at the cursor position.
 *
 * Null values break the line — DROP frames and missing fields must never
 * visually interpolate to zero (that's the quiet correctness win that
 * justifies the whole parser discipline).
 */
import { useEffect, useMemo, useRef, useState } from "react";
import * as d3 from "d3";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import RestartAltIcon from "@mui/icons-material/RestartAlt";
import { useTheme } from "@mui/material/styles";
import type { GuidingSample } from "@/api/guideLogs";
import { RIG_BLUE, RIG_ORANGE } from "@/lib/rigColors";

interface Props {
  samples: GuidingSample[];
  height?: number;
}

const COLOR_RA = RIG_BLUE;
const COLOR_DEC = RIG_ORANGE;

const MARGIN = { top: 16, right: 16, bottom: 40, left: 56 };
const MAIN_H_RATIO = 0.55;
const CORR_H_RATIO = 0.15;
const SNR_H_RATIO = 0.15;
const MASS_H_RATIO = 0.15;
// Gap between stacked panels (px).
const PANEL_GAP = 4;

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
}

export default function TimeSeriesChart({ samples, height = 360 }: Props) {
  const theme = useTheme();
  const isDark = theme.palette.mode === "dark";
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [width, setWidth] = useState(640);
  const [zoomX, setZoomX] = useState<[number, number] | null>(null);
  const [hover, setHover] = useState<HoverInfo | null>(null);

  // Responsive width — observe the wrapper.
  useEffect(() => {
    if (!wrapperRef.current) return;
    const obs = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width ?? 640;
      if (w > 0) setWidth(w);
    });
    obs.observe(wrapperRef.current);
    return () => obs.disconnect();
  }, []);

  // Panel bands (pixel y-ranges within the SVG)
  const innerW = Math.max(100, width - MARGIN.left - MARGIN.right);
  const innerH = height - MARGIN.top - MARGIN.bottom;
  const mainH = innerH * MAIN_H_RATIO - PANEL_GAP;
  const corrH = innerH * CORR_H_RATIO - PANEL_GAP;
  const snrH = innerH * SNR_H_RATIO - PANEL_GAP;
  const massH = innerH * MASS_H_RATIO;

  const mainY0 = MARGIN.top;
  const corrY0 = mainY0 + mainH + PANEL_GAP;
  const snrY0 = corrY0 + corrH + PANEL_GAP;
  const massY0 = snrY0 + snrH + PANEL_GAP;

  // Scales derived from samples
  const { xScale, yDistScale, ySnrScale, yMassScale, yCorrScale } = useMemo(() => {
    const times = samples.map((s) => s.time_seconds);
    const tmin = times.length ? times[0] : 0;
    const tmax = times.length ? times[times.length - 1] : 1;

    const distVals = samples.flatMap((s) =>
      [s.ra_raw_px, s.dec_raw_px].filter((v): v is number => v !== null),
    );
    const maxAbs = distVals.length
      ? Math.max(1.0, d3.max(distVals.map((v) => Math.abs(v))) ?? 1.0)
      : 1.0;

    const snrs = samples.map((s) => s.snr).filter((v): v is number => v !== null);
    const snrMax = snrs.length ? Math.max(10, d3.max(snrs) ?? 10) : 10;

    const masses = samples.map((s) => s.star_mass).filter((v): v is number => v !== null);
    const massMax = masses.length ? d3.max(masses) ?? 1 : 1;

    const durations = samples.flatMap((s) =>
      [s.ra_duration_ms ?? 0, s.dec_duration_ms ?? 0].filter((v) => v > 0),
    );
    const durMax = durations.length ? d3.max(durations) ?? 500 : 500;

    const domain = zoomX ?? [tmin, tmax];
    return {
      xScale: d3
        .scaleLinear()
        .domain(domain)
        .range([MARGIN.left, MARGIN.left + innerW]),
      yDistScale: d3
        .scaleLinear()
        .domain([-maxAbs * 1.1, maxAbs * 1.1])
        .range([mainY0 + mainH, mainY0]),
      yCorrScale: d3
        .scaleLinear()
        .domain([-durMax, durMax])
        .range([corrY0 + corrH, corrY0]),
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
  }, [samples, width, height, zoomX, innerW, mainH, corrH, snrH, massH]);

  // D3 zoom — pan + zoom X only.
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
        const t = e.transform;
        const rescaled = t.rescaleX(base);
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

  // Correction bars — each sample becomes one thin rect in the correction
  // panel. Height = pulse duration; sign = direction (above=W/N, below=E/S).
  const correctionBars = useMemo(() => {
    if (samples.length < 2) return [];
    const barW = Math.max(
      1,
      Math.min(6, (innerW / samples.length) * 0.45),
    );
    return samples.map((s, i) => {
      const cx = xScale(s.time_seconds);
      const raDur = s.ra_duration_ms ?? 0;
      const decDur = s.dec_duration_ms ?? 0;
      // RA bars — signed by W (above, blue, +) or E (below, blue, -).
      const raSign = s.ra_direction === "W" ? 1 : s.ra_direction === "E" ? -1 : 0;
      const decSign = s.dec_direction === "N" ? 1 : s.dec_direction === "S" ? -1 : 0;
      return {
        key: i,
        cx,
        barW,
        raHeight: raSign === 0 ? 0 : Math.abs(yCorrScale(raSign * raDur) - yCorrScale(0)),
        raY: raSign >= 0 ? yCorrScale(raSign * raDur) : yCorrScale(0),
        decHeight: decSign === 0 ? 0 : Math.abs(yCorrScale(decSign * decDur) - yCorrScale(0)),
        decY: decSign >= 0 ? yCorrScale(decSign * decDur) : yCorrScale(0),
      };
    });
  }, [samples, xScale, yCorrScale, innerW]);

  // Gridline + axis colours theme-aware
  const gridColor = isDark ? "rgba(255,255,255,0.08)" : "rgba(0,0,0,0.08)";
  const axisColor = isDark ? "rgba(255,255,255,0.6)" : "rgba(0,0,0,0.6)";
  const textColor = isDark ? "rgba(255,255,255,0.87)" : "rgba(0,0,0,0.87)";

  // Y axis ticks for main panel
  const mainTicks = yDistScale.ticks(5);
  const snrTicks = ySnrScale.ticks(3);
  const massTicks = yMassScale.ticks(3);

  // Sample-nearest hover
  function handleMouseMove(e: React.MouseEvent<SVGSVGElement>) {
    if (samples.length === 0) return;
    const svg = e.currentTarget;
    const rect = svg.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    if (mx < MARGIN.left || mx > MARGIN.left + innerW) {
      setHover(null);
      return;
    }
    const t = xScale.invert(mx);
    const bisector = d3.bisector((s: GuidingSample) => s.time_seconds).center;
    const idx = bisector(samples, t);
    const s = samples[Math.max(0, Math.min(samples.length - 1, idx))];
    setHover({
      xPx: xScale(s.time_seconds),
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
          <Box sx={{ width: 12, height: 2, bgcolor: COLOR_RA }} />
          <Typography variant="caption" sx={{ color: COLOR_RA }}>
            RA
          </Typography>
        </Stack>
        <Stack direction="row" spacing={0.5} alignItems="center">
          <Box sx={{ width: 12, height: 2, bgcolor: COLOR_DEC }} />
          <Typography variant="caption" sx={{ color: COLOR_DEC }}>
            Dec
          </Typography>
        </Stack>
        <Box sx={{ flex: 1 }} />
        <Button
          size="small"
          startIcon={<RestartAltIcon />}
          onClick={handleReset}
          disabled={zoomX === null}
        >
          Reset zoom
        </Button>
      </Stack>
      <svg
        ref={svgRef}
        width={width}
        height={height}
        onMouseMove={handleMouseMove}
        onMouseLeave={() => setHover(null)}
        style={{ display: "block", cursor: "crosshair" }}
      >
        {/* Main panel — gridlines */}
        {mainTicks.map((t) => (
          <line
            key={`gm-${t}`}
            x1={MARGIN.left}
            x2={MARGIN.left + innerW}
            y1={yDistScale(t)}
            y2={yDistScale(t)}
            stroke={gridColor}
          />
        ))}
        {/* Main zero-axis emphasised */}
        <line
          x1={MARGIN.left}
          x2={MARGIN.left + innerW}
          y1={yDistScale(0)}
          y2={yDistScale(0)}
          stroke={axisColor}
          strokeWidth={1}
        />

        {/* Correction panel zero axis */}
        <line
          x1={MARGIN.left}
          x2={MARGIN.left + innerW}
          y1={yCorrScale(0)}
          y2={yCorrScale(0)}
          stroke={axisColor}
          strokeWidth={1}
        />

        {/* Correction bars */}
        {correctionBars.map((b) => (
          <g key={`bars-${b.key}`}>
            {b.raHeight > 0 && (
              <rect
                x={b.cx - b.barW / 2}
                y={b.raY}
                width={b.barW}
                height={b.raHeight}
                fill={COLOR_RA}
                opacity={0.65}
              />
            )}
            {b.decHeight > 0 && (
              <rect
                x={b.cx - b.barW / 2}
                y={b.decY}
                width={b.barW}
                height={b.decHeight}
                fill={COLOR_DEC}
                opacity={0.45}
              />
            )}
          </g>
        ))}

        {/* Main traces */}
        <path
          d={raLine(samples) ?? undefined}
          fill="none"
          stroke={COLOR_RA}
          strokeWidth={1.25}
        />
        <path
          d={decLine(samples) ?? undefined}
          fill="none"
          stroke={COLOR_DEC}
          strokeWidth={1.25}
        />

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

        {/* StarMass panel */}
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

        {/* Y-axis ticks — main panel */}
        {mainTicks.map((t) => (
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

        {/* Panel labels */}
        <text
          x={MARGIN.left - 6}
          y={mainY0 + 8}
          fill={textColor}
          fontSize={10}
          textAnchor="end"
        >
          px
        </text>
        <text
          x={MARGIN.left - 6}
          y={corrY0 + corrH / 2}
          fill={textColor}
          fontSize={10}
          textAnchor="end"
          dominantBaseline="central"
        >
          ms
        </text>
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
          x={MARGIN.left - 6}
          y={snrY0 + 8}
          fill={textColor}
          fontSize={10}
          textAnchor="end"
        >
          SNR
        </text>
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
          x={MARGIN.left - 6}
          y={massY0 + 8}
          fill={textColor}
          fontSize={10}
          textAnchor="end"
        >
          mass
        </text>

        {/* X-axis bottom */}
        <line
          x1={MARGIN.left}
          x2={MARGIN.left + innerW}
          y1={massY0 + massH}
          y2={massY0 + massH}
          stroke={axisColor}
        />
        {xScale.ticks(8).map((t) => (
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
              {formatElapsed(t)}
            </text>
          </g>
        ))}
        <text
          x={MARGIN.left + innerW / 2}
          y={height - 6}
          fill={textColor}
          fontSize={10}
          textAnchor="middle"
        >
          elapsed (s)
        </text>

        {/* Crosshair */}
        {hover && (
          <g pointerEvents="none">
            <line
              x1={hover.xPx}
              x2={hover.xPx}
              y1={MARGIN.top}
              y2={massY0 + massH}
              stroke={axisColor}
              strokeDasharray="3 3"
              opacity={0.7}
            />
          </g>
        )}
      </svg>
      {hover && (
        <Box
          sx={{
            position: "absolute",
            top: 8,
            right: 8,
            p: 1,
            bgcolor: "background.paper",
            border: "1px solid",
            borderColor: "divider",
            borderRadius: 1,
            fontSize: 12,
            minWidth: 160,
            pointerEvents: "none",
          }}
        >
          <Typography variant="caption" sx={{ display: "block", fontWeight: 600 }}>
            Frame {hover.frame ?? "?"} · {hover.time.toFixed(2)} s
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
        </Box>
      )}
    </Box>
  );
}

function formatPx(v: number | null): string {
  if (v === null) return "—";
  return v.toFixed(3);
}

function formatElapsed(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds - m * 60);
  return `${m}m${String(s).padStart(2, "0")}`;
}
