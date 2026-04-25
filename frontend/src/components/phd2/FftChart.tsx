/**
 * PHD2 spectrum chart — spec v4 §6.1.5–§6.1.7.
 *
 * Dual-trace (RA/Dec) FFT spectrum with log-log axes, top-5 peak dots,
 * snap-to-peak hover, worm-period overlay, and seeing-band shading at < 5 s.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import * as d3 from "d3";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useTheme } from "@mui/material/styles";

import type { FftPeak, FftResult, WormMarker } from "@/api/phd2";
import { RIG_BLUE, RIG_ORANGE } from "@/lib/rigColors";

interface Props {
  fftRa: FftResult | null;
  fftDec: FftResult | null;
  wormMarker: WormMarker | null;
  /** Section duration (s); the X-axis upper edge clamps to duration / 2. */
  durationSeconds: number;
  height?: number;
}

const MARGIN = { top: 16, right: 24, bottom: 56, left: 78 };
const SEEING_BAND_S = 5.0;
// ±8 px snap matches PHDLogViewer's hover behaviour.
const SNAP_RADIUS_PX = 8;

const COLOR_RA = RIG_BLUE;
const COLOR_DEC = RIG_ORANGE;

interface HoverState {
  /** When true, the hairline locks to a peak's period and the tooltip
   *  shows the full peak readout. When false, it tracks the cursor. */
  snapped: boolean;
  cursorX: number;
  period: number;
  raAmp: number | null;
  decAmp: number | null;
  matchedPeak: { trace: "ra" | "dec"; peak: FftPeak } | null;
}

export default function FftChart({
  fftRa,
  fftDec,
  wormMarker,
  durationSeconds,
  height = 360,
}: Props) {
  const theme = useTheme();
  const isDark = theme.palette.mode === "dark";
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [width, setWidth] = useState(640);
  const [hover, setHover] = useState<HoverState | null>(null);
  const [showRa, setShowRa] = useState(true);
  const [showDec, setShowDec] = useState(true);

  useEffect(() => {
    if (!wrapperRef.current) return;
    const obs = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width ?? 640;
      if (w > 0) setWidth(w);
    });
    obs.observe(wrapperRef.current);
    return () => obs.disconnect();
  }, []);

  const innerW = Math.max(100, width - MARGIN.left - MARGIN.right);
  const innerH = Math.max(80, height - MARGIN.top - MARGIN.bottom);

  const { xScale, yScale, ampMax } = useMemo(() => {
    const xMin = SEEING_BAND_S;
    const xMax = Math.max(xMin * 2, durationSeconds / 2);
    const visibleAmps: number[] = [];
    if (showRa && fftRa?.skip_reason === null && fftRa.amplitude_arcsec.length) {
      visibleAmps.push(...fftRa.amplitude_arcsec);
    }
    if (showDec && fftDec?.skip_reason === null && fftDec.amplitude_arcsec.length) {
      visibleAmps.push(...fftDec.amplitude_arcsec);
    }
    const max = visibleAmps.length > 0 ? Math.max(...visibleAmps) : 1;
    const ampMin = Math.max(max / 10000, 0.001);
    const ampMaxScaled = max * 1.1;
    const x = d3.scaleLog().domain([xMin, xMax]).range([MARGIN.left, MARGIN.left + innerW]);
    const y = d3
      .scaleLog()
      .domain([ampMin, ampMaxScaled])
      .range([MARGIN.top + innerH, MARGIN.top]);
    return { xScale: x, yScale: y, ampMax: ampMaxScaled };
  }, [fftRa, fftDec, durationSeconds, innerW, innerH, showRa, showDec]);

  const traceLine = useMemo(
    () =>
      d3
        .line<[number, number]>()
        .x((d) => xScale(d[0]))
        .y((d) => yScale(d[1]))
        .defined((d) => {
          const [x, y] = d;
          return (
            x >= SEEING_BAND_S &&
            x <= durationSeconds / 2 &&
            y > 0 &&
            Number.isFinite(y)
          );
        }),
    [xScale, yScale, durationSeconds],
  );

  const raPath = useMemo(() => buildPath(fftRa, traceLine), [fftRa, traceLine]);
  const decPath = useMemo(() => buildPath(fftDec, traceLine), [fftDec, traceLine]);

  const visiblePeaks: { trace: "ra" | "dec"; peak: FftPeak }[] = [];
  if (showRa && fftRa && !fftRa.skip_reason) {
    for (const p of fftRa.peaks) visiblePeaks.push({ trace: "ra", peak: p });
  }
  if (showDec && fftDec && !fftDec.skip_reason) {
    for (const p of fftDec.peaks) visiblePeaks.push({ trace: "dec", peak: p });
  }

  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!svgRef.current) return;
    const rect = svgRef.current.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    if (
      mx < MARGIN.left ||
      mx > MARGIN.left + innerW ||
      my < MARGIN.top ||
      my > MARGIN.top + innerH
    ) {
      setHover(null);
      return;
    }
    // Snap is horizontal-only — user's mental model is "the line is
    // near the peak", not "the cursor is near the dot".
    let best: { dist: number; trace: "ra" | "dec"; peak: FftPeak } | null = null;
    for (const { trace, peak } of visiblePeaks) {
      const dist = Math.abs(xScale(peak.period_s) - mx);
      if (dist <= SNAP_RADIUS_PX && (best === null || dist < best.dist)) {
        best = { dist, trace, peak };
      }
    }
    if (best) {
      const period = best.peak.period_s;
      setHover({
        snapped: true,
        cursorX: xScale(period),
        period,
        raAmp: showRa ? lookupAmpAt(fftRa, period) : null,
        decAmp: showDec ? lookupAmpAt(fftDec, period) : null,
        matchedPeak: { trace: best.trace, peak: best.peak },
      });
    } else {
      const period = xScale.invert(mx);
      setHover({
        snapped: false,
        cursorX: mx,
        period,
        raAmp: showRa ? lookupAmpAt(fftRa, period) : null,
        decAmp: showDec ? lookupAmpAt(fftDec, period) : null,
        matchedPeak: null,
      });
    }
  };

  const axisColor = isDark ? "rgba(255,255,255,0.6)" : "rgba(0,0,0,0.6)";
  const gridColor = isDark ? "rgba(255,255,255,0.08)" : "rgba(0,0,0,0.08)";
  const seeingBandFill = isDark ? "rgba(255,255,255,0.04)" : "rgba(0,0,0,0.04)";
  const labelColor = isDark ? "rgba(255,255,255,0.85)" : "rgba(0,0,0,0.85)";

  const xTicks = xScale.ticks(6);
  const yTicks = yScale.ticks(5);

  // Show the "spectrum unavailable" overlay only when every currently-
  // visible trace was skipped. In practice both traces share the same
  // input guards so they tend to skip together, but the constant-data
  // guard is per-trace — toggling RA off when only RA was skipped
  // should reveal the still-valid Dec trace.
  const skippedReason = (() => {
    const visible: (string | null)[] = [];
    if (showRa) visible.push(fftRa?.skip_reason ?? null);
    if (showDec) visible.push(fftDec?.skip_reason ?? null);
    if (visible.length === 0 || visible.some((r) => r === null)) return null;
    return visible[0];
  })();

  const wormPx = wormMarker ? xScale(wormMarker.period_s) : null;
  const wormInDomain =
    wormPx !== null && wormPx >= MARGIN.left && wormPx <= MARGIN.left + innerW;

  return (
    <Stack spacing={1}>
      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
        <LegendChip
          label="RA"
          color={COLOR_RA}
          active={showRa}
          onToggle={() => setShowRa((v) => !v)}
        />
        <LegendChip
          label="Dec"
          color={COLOR_DEC}
          active={showDec}
          onToggle={() => setShowDec((v) => !v)}
        />
        {wormMarker && (
          <Chip
            size="small"
            label={wormMarker.label}
            sx={{
              fontSize: 11,
              height: 22,
              bgcolor: wormMarker.source === "mount" ? "primary.main" : "action.selected",
              color: wormMarker.source === "mount" ? "primary.contrastText" : "text.secondary",
            }}
          />
        )}
      </Stack>

      <Box ref={wrapperRef} sx={{ position: "relative", width: "100%" }}>
        {skippedReason ? (
          <Box
            sx={{
              height,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "text.secondary",
              border: 1,
              borderColor: "divider",
              borderRadius: 1,
              fontStyle: "italic",
              fontSize: 13,
            }}
          >
            Spectrum unavailable: {humanSkipReason(skippedReason)}
          </Box>
        ) : (
          <svg
            ref={svgRef}
            width={width}
            height={height}
            onMouseMove={handleMouseMove}
            onMouseLeave={() => setHover(null)}
            style={{ display: "block" }}
          >
            <defs>
              <clipPath id="fft-panel-clip">
                <rect
                  x={MARGIN.left}
                  y={MARGIN.top}
                  width={innerW}
                  height={innerH}
                />
              </clipPath>
            </defs>

            <rect
              x={MARGIN.left}
              y={MARGIN.top}
              width={Math.max(0, xScale(SEEING_BAND_S) - MARGIN.left)}
              height={innerH}
              fill={seeingBandFill}
            />

            {xTicks.map((t) => (
              <line
                key={`gx-${t}`}
                x1={xScale(t)}
                x2={xScale(t)}
                y1={MARGIN.top}
                y2={MARGIN.top + innerH}
                stroke={gridColor}
              />
            ))}
            {yTicks.map((t) => (
              <line
                key={`gy-${t}`}
                x1={MARGIN.left}
                x2={MARGIN.left + innerW}
                y1={yScale(t)}
                y2={yScale(t)}
                stroke={gridColor}
              />
            ))}

            {wormInDomain && wormPx !== null && (
              <line
                x1={wormPx}
                x2={wormPx}
                y1={MARGIN.top}
                y2={MARGIN.top + innerH}
                stroke={wormMarker?.source === "mount" ? "currentColor" : axisColor}
                strokeDasharray="4 3"
                opacity={wormMarker?.source === "mount" ? 0.6 : 0.4}
              />
            )}

            <g clipPath="url(#fft-panel-clip)">
              {showRa && raPath && (
                <path d={raPath} fill="none" stroke={COLOR_RA} strokeWidth={1.4} opacity={0.85} />
              )}
              {showDec && decPath && (
                <path d={decPath} fill="none" stroke={COLOR_DEC} strokeWidth={1.4} opacity={0.85} />
              )}

              {visiblePeaks.map(({ trace, peak }, i) => (
                <circle
                  key={`peak-${trace}-${i}`}
                  cx={xScale(peak.period_s)}
                  cy={yScale(peak.amplitude_arcsec)}
                  r={3.5}
                  fill={trace === "ra" ? COLOR_RA : COLOR_DEC}
                  stroke="white"
                  strokeWidth={0.5}
                  strokeOpacity={0.5}
                  opacity={0.9}
                />
              ))}
            </g>

            <line
              x1={MARGIN.left}
              x2={MARGIN.left + innerW}
              y1={MARGIN.top + innerH}
              y2={MARGIN.top + innerH}
              stroke={axisColor}
            />
            {xTicks.map((t) => (
              <g key={`xt-${t}`} transform={`translate(${xScale(t)}, ${MARGIN.top + innerH})`}>
                <line y2={4} stroke={axisColor} />
                <text
                  transform="translate(-2, 14) rotate(-30)"
                  fill={labelColor}
                  fontSize={10}
                  textAnchor="end"
                >
                  {formatPeriod(t)}
                </text>
              </g>
            ))}
            <text
              x={MARGIN.left + innerW / 2}
              y={MARGIN.top + innerH + 48}
              fill={labelColor}
              fontSize={11}
              textAnchor="middle"
            >
              Period (s) — log scale
            </text>

            <line
              x1={MARGIN.left}
              x2={MARGIN.left}
              y1={MARGIN.top}
              y2={MARGIN.top + innerH}
              stroke={axisColor}
            />
            {yTicks.map((t) => (
              <g key={`yt-${t}`} transform={`translate(${MARGIN.left}, ${yScale(t)})`}>
                <line x2={-4} stroke={axisColor} />
                <text
                  x={-9}
                  y={3}
                  fill={labelColor}
                  fontSize={10}
                  textAnchor="end"
                >
                  {formatAmplitude(t, ampMax)}
                </text>
              </g>
            ))}
            <text
              transform={`translate(${MARGIN.left - 56}, ${MARGIN.top + innerH / 2}) rotate(-90)`}
              fill={labelColor}
              fontSize={11}
              textAnchor="middle"
            >
              Amplitude (″) — log scale
            </text>

            {hover && (() => {
              const px = hover.cursorX;
              const tooltipW = 168;
              const lineCount = hover.snapped
                ? 5
                : 1 +
                  (hover.raAmp !== null ? 1 : 0) +
                  (hover.decAmp !== null ? 1 : 0);
              // 18 px per line (11 px font × 1.35) + 24 px padding.
              const tooltipH = lineCount * 18 + 24;
              // Anchor at a fixed vertical position regardless of snap
              // state so the tooltip doesn't jump on snap.
              const tooltipYUnclamped = MARGIN.top + innerH * 0.35 - tooltipH / 2;
              const tooltipY = Math.max(
                MARGIN.top + 4,
                Math.min(tooltipYUnclamped, MARGIN.top + innerH - tooltipH - 4),
              );
              const left =
                px + tooltipW + 12 > MARGIN.left + innerW
                  ? px - tooltipW - 12
                  : px + 12;
              return (
                <g pointerEvents="none">
                  <line
                    x1={px}
                    x2={px}
                    y1={MARGIN.top}
                    y2={MARGIN.top + innerH}
                    stroke={axisColor}
                    strokeWidth={1}
                    strokeOpacity={hover.snapped ? 0.7 : 0.35}
                    strokeDasharray={hover.snapped ? undefined : "3 3"}
                  />
                  <foreignObject
                    x={left}
                    y={tooltipY}
                    width={tooltipW}
                    height={tooltipH}
                  >
                    <Box
                      sx={{
                        bgcolor: "background.paper",
                        border: 1,
                        borderColor: "divider",
                        borderRadius: 1,
                        p: 0.75,
                        fontSize: 11,
                        lineHeight: 1.35,
                        // Force Typography to inherit so the per-line
                        // height math above stays accurate.
                        "& .MuiTypography-root": {
                          fontSize: "inherit",
                          lineHeight: "inherit",
                        },
                      }}
                    >
                      {hover.snapped && hover.matchedPeak ? (
                        <>
                          <Typography
                            variant="caption"
                            sx={{
                              fontWeight: 600,
                              display: "block",
                              color: hover.matchedPeak.trace === "ra" ? COLOR_RA : COLOR_DEC,
                            }}
                          >
                            {hover.matchedPeak.trace === "ra" ? "RA peak" : "Dec peak"}
                          </Typography>
                          <Typography variant="caption" sx={{ display: "block" }}>
                            Period: {formatPeriodVerbose(hover.period)}
                          </Typography>
                          <Typography variant="caption" sx={{ display: "block" }}>
                            Amplitude: {hover.matchedPeak.peak.amplitude_arcsec.toFixed(2)}″
                          </Typography>
                          <Typography variant="caption" sx={{ display: "block" }}>
                            Peak-to-peak: {(hover.matchedPeak.peak.amplitude_arcsec * 2).toFixed(2)}″
                          </Typography>
                          <Typography variant="caption" sx={{ display: "block" }}>
                            RMS: {(hover.matchedPeak.peak.amplitude_arcsec / Math.SQRT2).toFixed(2)}″
                          </Typography>
                        </>
                      ) : (
                        <>
                          <Typography variant="caption" sx={{ fontWeight: 600, display: "block" }}>
                            Period: {formatPeriodVerbose(hover.period)}
                          </Typography>
                          {hover.raAmp !== null && (
                            <Typography
                              variant="caption"
                              sx={{ display: "block", color: COLOR_RA }}
                            >
                              RA: {hover.raAmp.toFixed(3)}″
                            </Typography>
                          )}
                          {hover.decAmp !== null && (
                            <Typography
                              variant="caption"
                              sx={{ display: "block", color: COLOR_DEC }}
                            >
                              Dec: {hover.decAmp.toFixed(3)}″
                            </Typography>
                          )}
                        </>
                      )}
                    </Box>
                  </foreignObject>
                </g>
              );
            })()}
          </svg>
        )}
      </Box>
    </Stack>
  );
}

function buildPath(
  fft: FftResult | null,
  line: d3.Line<[number, number]>,
): string | null {
  if (!fft || fft.skip_reason || !fft.amplitude_arcsec.length) return null;
  const points: [number, number][] = fft.period_s.map((p, i) => [
    p,
    fft.amplitude_arcsec[i],
  ]);
  points.sort((a, b) => a[0] - b[0]);
  return line(points);
}

function LegendChip({
  label,
  color,
  active,
  onToggle,
}: {
  label: string;
  color: string;
  active: boolean;
  onToggle: () => void;
}) {
  return (
    <Chip
      size="small"
      onClick={onToggle}
      label={
        <Stack direction="row" spacing={0.75} alignItems="center">
          <Box
            sx={{
              width: 12,
              height: 2,
              bgcolor: color,
              opacity: active ? 1 : 0.3,
              borderRadius: 0.5,
            }}
          />
          <span>{label}</span>
        </Stack>
      }
      variant="outlined"
      sx={{
        fontSize: 11,
        height: 22,
        opacity: active ? 1 : 0.6,
        cursor: "pointer",
      }}
    />
  );
}

function formatPeriod(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(0)}s`;
  if (seconds < 3600) {
    const m = Math.floor(seconds / 60);
    const s = Math.round(seconds - m * 60);
    return s === 0 ? `${m}m` : `${m}m${s}s`;
  }
  const h = Math.floor(seconds / 3600);
  const m = Math.round((seconds - h * 3600) / 60);
  return m === 0 ? `${h}h` : `${h}h${m}m`;
}

function formatPeriodVerbose(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(1)} s`;
  if (seconds < 3600) {
    const m = Math.floor(seconds / 60);
    const s = Math.round(seconds - m * 60);
    return s === 0 ? `${m}m (${seconds.toFixed(0)} s)` : `${m}m ${s}s`;
  }
  const h = Math.floor(seconds / 3600);
  const m = Math.round((seconds - h * 3600) / 60);
  return m === 0 ? `${h}h (${seconds.toFixed(0)} s)` : `${h}h ${m}m`;
}

function formatAmplitude(value: number, axisMax: number): string {
  if (axisMax >= 1000 || value >= 1000) return value.toExponential(0);
  if (value >= 10) return value.toFixed(0);
  if (value >= 1) return value.toFixed(1);
  if (value >= 0.01) return value.toFixed(2);
  return value.toExponential(0);
}

function lookupAmpAt(fft: FftResult | null, period: number): number | null {
  if (!fft || fft.skip_reason || !fft.amplitude_arcsec.length) return null;
  const target = Math.log(period);
  let bestIdx = 0;
  let bestDist = Infinity;
  for (let i = 0; i < fft.period_s.length; i++) {
    const p = fft.period_s[i];
    if (!(p > 0)) continue;
    const d = Math.abs(Math.log(p) - target);
    if (d < bestDist) {
      bestDist = d;
      bestIdx = i;
    }
  }
  return fft.amplitude_arcsec[bestIdx];
}

function humanSkipReason(reason: string): string {
  switch (reason) {
    case "too_short":
      return "section too short for FFT (minimum 12 frames)";
    case "non_uniform_cadence":
      return "sample cadence varies more than 20% — frequency analysis disabled";
    case "constant_data":
      return "no variation in this section's data";
    default:
      return reason;
  }
}
