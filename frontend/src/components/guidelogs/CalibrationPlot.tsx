/**
 * PHD2 calibration plot — five-phase stepped path in dx/dy pixel space.
 *
 * Each phase (West, East, Backlash, North, South) draws its own polyline
 * so the user can distinguish the forward/return pairs and the backlash
 * clear. Derived angle + rate + parity for the West and North axes render
 * as a small table beside the plot.
 *
 * v0.22.0 keeps this intentionally simple — origin reticle + grid overlay
 * land in Pass B.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import * as d3 from "d3";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useTheme } from "@mui/material/styles";
import type { CalibrationPhase } from "@/api/guideLogs";
import { RIG_BLUE, RIG_BLUE_LIGHT, RIG_ORANGE, RIG_ORANGE_LIGHT, RIG_TEAL } from "@/lib/rigColors";

interface Props {
  phases: CalibrationPhase[];
  height?: number;
}

/** Per-phase color map. Exported so the Data-tab Chip rendering in
 *  ``SectionDataTab`` stays visually consistent with the plot legend. */
export const PHASE_COLORS: Record<string, string> = {
  West: RIG_BLUE,
  East: RIG_BLUE_LIGHT,
  Backlash: RIG_TEAL,
  North: RIG_ORANGE,
  South: RIG_ORANGE_LIGHT,
};

const MARGIN = { top: 16, right: 16, bottom: 36, left: 52 };

export default function CalibrationPlot({ phases, height = 320 }: Props) {
  const theme = useTheme();
  const isDark = theme.palette.mode === "dark";
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const [width, setWidth] = useState(520);

  useEffect(() => {
    if (!wrapperRef.current) return;
    const obs = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width ?? 520;
      if (w > 0) setWidth(w);
    });
    obs.observe(wrapperRef.current);
    return () => obs.disconnect();
  }, []);

  const { xScale, yScale, paths } = useMemo(() => {
    const allPoints = phases.flatMap((p) => p.samples);
    const dxs = allPoints.map((s) => s.dx_px);
    const dys = allPoints.map((s) => s.dy_px);
    const dxAbs = Math.max(1, d3.max(dxs.map((v) => Math.abs(v))) ?? 1);
    const dyAbs = Math.max(1, d3.max(dys.map((v) => Math.abs(v))) ?? 1);
    // Square plot — use the larger extent on both axes so the geometry is
    // rendered undistorted. Calibration angles are the whole point here.
    const maxAbs = Math.max(dxAbs, dyAbs) * 1.1;

    const innerW = Math.max(100, width - MARGIN.left - MARGIN.right);
    const innerH = height - MARGIN.top - MARGIN.bottom;
    const side = Math.min(innerW, innerH);
    const padX = (innerW - side) / 2;

    const x = d3
      .scaleLinear()
      .domain([-maxAbs, maxAbs])
      .range([MARGIN.left + padX, MARGIN.left + padX + side]);
    // Y flipped so +dy goes up (visual convention).
    const y = d3
      .scaleLinear()
      .domain([-maxAbs, maxAbs])
      .range([MARGIN.top + side, MARGIN.top]);

    const line = d3
      .line<{ dx_px: number; dy_px: number }>()
      .x((s) => x(s.dx_px))
      .y((s) => y(s.dy_px));

    const pathData = phases.map((p) => ({
      direction: p.direction,
      d: p.samples.length > 1 ? line(p.samples) : null,
      points: p.samples.map((s) => ({ cx: x(s.dx_px), cy: y(s.dy_px) })),
    }));

    return { xScale: x, yScale: y, paths: pathData };
  }, [phases, width, height]);

  const gridColor = isDark ? "rgba(255,255,255,0.08)" : "rgba(0,0,0,0.08)";
  const axisColor = isDark ? "rgba(255,255,255,0.6)" : "rgba(0,0,0,0.6)";
  const textColor = isDark ? "rgba(255,255,255,0.87)" : "rgba(0,0,0,0.87)";

  const xTicks = xScale.ticks(5);
  const yTicks = yScale.ticks(5);

  const westPhase = phases.find((p) => p.direction === "West");
  const northPhase = phases.find((p) => p.direction === "North");

  return (
    <Stack direction={{ xs: "column", md: "row" }} spacing={2} sx={{ width: "100%" }}>
      <Box ref={wrapperRef} sx={{ flex: 1, minWidth: 240 }}>
        <svg width={width} height={height} style={{ display: "block" }}>
          {/* Grid */}
          {xTicks.map((t) => (
            <line
              key={`gx-${t}`}
              x1={xScale(t)}
              x2={xScale(t)}
              y1={MARGIN.top}
              y2={height - MARGIN.bottom}
              stroke={gridColor}
            />
          ))}
          {yTicks.map((t) => (
            <line
              key={`gy-${t}`}
              x1={MARGIN.left}
              x2={width - MARGIN.right}
              y1={yScale(t)}
              y2={yScale(t)}
              stroke={gridColor}
            />
          ))}
          {/* Zero axes */}
          <line
            x1={xScale(0)}
            x2={xScale(0)}
            y1={MARGIN.top}
            y2={height - MARGIN.bottom}
            stroke={axisColor}
          />
          <line
            x1={MARGIN.left}
            x2={width - MARGIN.right}
            y1={yScale(0)}
            y2={yScale(0)}
            stroke={axisColor}
          />
          {/* Phase paths */}
          {paths.map((p) => (
            <g key={p.direction}>
              {p.d && (
                <path
                  d={p.d}
                  fill="none"
                  stroke={PHASE_COLORS[p.direction]}
                  strokeWidth={1.5}
                  opacity={0.9}
                />
              )}
              {p.points.map((pt, i) => (
                <circle
                  key={`${p.direction}-${i}`}
                  cx={pt.cx}
                  cy={pt.cy}
                  r={2.5}
                  fill={PHASE_COLORS[p.direction]}
                />
              ))}
            </g>
          ))}

          {/* X ticks */}
          {xTicks.map((t) => (
            <text
              key={`xt-${t}`}
              x={xScale(t)}
              y={height - MARGIN.bottom + 14}
              fill={textColor}
              fontSize={10}
              textAnchor="middle"
            >
              {t}
            </text>
          ))}
          {/* Y ticks */}
          {yTicks.map((t) => (
            <text
              key={`yt-${t}`}
              x={MARGIN.left - 6}
              y={yScale(t)}
              fill={textColor}
              fontSize={10}
              textAnchor="end"
              dominantBaseline="central"
            >
              {t}
            </text>
          ))}
          {/* Axis labels */}
          <text
            x={(MARGIN.left + width - MARGIN.right) / 2}
            y={height - 4}
            fill={textColor}
            fontSize={10}
            textAnchor="middle"
          >
            dx (px)
          </text>
          <text
            x={MARGIN.left - 36}
            y={(MARGIN.top + height - MARGIN.bottom) / 2}
            fill={textColor}
            fontSize={10}
            textAnchor="middle"
            transform={`rotate(-90 ${MARGIN.left - 36} ${(MARGIN.top + height - MARGIN.bottom) / 2})`}
          >
            dy (px)
          </text>
        </svg>
      </Box>
      <Box sx={{ minWidth: 220, maxWidth: 280 }}>
        <Typography variant="subtitle2" sx={{ mb: 1 }}>
          Calibration geometry
        </Typography>
        <Stack spacing={1.5}>
          {(["West", "East", "Backlash", "North", "South"] as const).map((dir) => {
            const phase = phases.find((p) => p.direction === dir);
            const color = PHASE_COLORS[dir];
            const hasMeta = phase?.angle_deg !== undefined && phase?.angle_deg !== null;
            return (
              <Box key={dir}>
                <Stack direction="row" spacing={1} alignItems="center">
                  <Box sx={{ width: 10, height: 10, bgcolor: color, borderRadius: 0.5 }} />
                  <Typography variant="body2" sx={{ fontWeight: 500, color }}>
                    {dir}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    · {phase?.samples.length ?? 0} steps
                  </Typography>
                </Stack>
                {hasMeta && (
                  <Typography variant="caption" sx={{ display: "block", pl: 2.25 }}>
                    angle {phase!.angle_deg?.toFixed(1)}°, rate{" "}
                    {phase!.rate_px_per_sec?.toFixed(3)} px/s
                    {phase!.parity ? `, parity ${phase!.parity}` : ""}
                  </Typography>
                )}
              </Box>
            );
          })}
        </Stack>
        {westPhase?.angle_deg !== undefined &&
          westPhase?.angle_deg !== null &&
          northPhase?.angle_deg !== undefined &&
          northPhase?.angle_deg !== null && (
            <Typography variant="caption" sx={{ display: "block", mt: 2, color: "text.secondary" }}>
              Axis separation:{" "}
              {Math.abs((westPhase.angle_deg ?? 0) - (northPhase.angle_deg ?? 0)).toFixed(1)}°
              (90° = perfectly orthogonal)
            </Typography>
          )}
      </Box>
    </Stack>
  );
}
