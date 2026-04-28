/**
 * "Best time of year" chart for the planner detail panel.
 *
 * Dual curves: raw hours (blue solid) and quality-weighted hours
 * (orange dashed). Moon phase backdrop shows the ~29.5-day
 * illumination cycle as a grey band. Hover crosshair shows both
 * values.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import * as d3 from "d3";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { useTheme } from "@mui/material/styles";
import type { AnnualHoursResponse } from "@/api/planner";
import { RIG_BLUE, RIG_ORANGE } from "@/lib/rigColors";

interface Props {
  track: AnnualHoursResponse;
  height?: number;
}

interface HoverInfo {
  xPx: number;
  yPxRaw: number;
  yPxWeighted: number;
  dateLabel: string;
  rawHours: number;
  weightedHours: number;
  illuminationPct: number | null;
  minSeparationDeg: number | null;
  maxAltitudeDeg: number | null;
  snappedToToday: boolean;
}

const TODAY_SNAP_PX = 6;

export default function BestTimeOfYearChart({ track, height = 200 }: Props) {
  const theme = useTheme();
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const [width, setWidth] = useState(600);
  const [hover, setHover] = useState<HoverInfo | null>(null);

  useEffect(() => {
    const el = wrapperRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width ?? 600;
      setWidth(Math.max(400, Math.floor(w)));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const layout = useMemo(() => {
    const MARGIN = { top: 10, right: 44, bottom: 26, left: 44 };
    const dates = track.points.map((p) => new Date(`${p.date}T12:00:00Z`));
    const tmin = dates[0] ?? new Date();
    const tmax = dates[dates.length - 1] ?? new Date();

    const maxHours = Math.max(
      ...track.points.map((p) => p.hours),
      ...track.filtered_points.map((p) => p.hours),
      0,
    );
    const yMax = Math.max(12, Math.ceil(maxHours + 0.5));

    const x = d3
      .scaleTime()
      .domain([tmin, tmax])
      .range([MARGIN.left, width - MARGIN.right]);

    const y = d3
      .scaleLinear()
      .domain([0, yMax])
      .range([height - MARGIN.bottom, MARGIN.top]);

    const line = d3
      .line<number>()
      .defined((d) => d > 0.01)
      .x((_, i) => x(dates[i]))
      .y((d) => y(Math.max(0, Math.min(yMax, d))))
      .curve(d3.curveMonotoneX);

    const lineContinuous = d3
      .line<number>()
      .x((_, i) => x(dates[i]))
      .y((d) => y(Math.max(0, Math.min(yMax, d))))
      .curve(d3.curveMonotoneX);

    const yRight = d3
      .scaleLinear()
      .domain([-10, 90])
      .range([height - MARGIN.bottom, MARGIN.top]);

    const moonAltLine = d3
      .line<number | null>()
      .defined((d) => d != null)
      .x((_, i) => x(dates[i]))
      .y((d) => yRight(d!))
      .curve(d3.curveMonotoneX);

    return { MARGIN, dates, x, y, yRight, line, lineContinuous, moonAltLine, yMax };
  }, [track, width, height]);

  function onMouseMove(e: React.MouseEvent<SVGSVGElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    if (mx < layout.MARGIN.left || mx > width - layout.MARGIN.right) {
      setHover(null);
      return;
    }

    let snapXPx: number | null = null;
    let snapIdx: number | null = null;
    if (todayXPx != null && Math.abs(mx - todayXPx) <= TODAY_SNAP_PX) {
      snapXPx = todayXPx;
      snapIdx = d3
        .bisector((d: Date) => d)
        .center(layout.dates, new Date());
    }

    const t = layout.x.invert(mx);
    const idx =
      snapIdx ?? d3.bisector((d: Date) => d).left(layout.dates, t);
    const clamped = Math.max(0, Math.min(layout.dates.length - 1, idx));
    const rawP = track.points[clamped];
    const weightedP = track.filtered_points[clamped];
    setHover({
      xPx: snapXPx ?? layout.x(layout.dates[clamped]),
      yPxRaw: layout.y(Math.max(0, Math.min(layout.yMax, rawP.hours))),
      yPxWeighted: layout.y(Math.max(0, Math.min(layout.yMax, weightedP?.hours ?? rawP.hours))),
      dateLabel: layout.dates[clamped].toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
      }),
      rawHours: rawP.hours,
      weightedHours: weightedP?.hours ?? rawP.hours,
      illuminationPct: track.moon_data[clamped]?.illumination_pct ?? null,
      minSeparationDeg: track.moon_data[clamped]?.min_separation_deg ?? null,
      maxAltitudeDeg: track.moon_data[clamped]?.max_altitude_deg ?? null,
      snappedToToday: snapXPx != null,
    });
  }

  const monthTicks = useMemo(
    () => {
      const tmin = layout.dates[0];
      const tmax = layout.dates[layout.dates.length - 1];
      if (!tmin || !tmax) return [];
      const ticks = d3.timeMonths(tmin, tmax);
      const firstMonthBoundary = d3.timeMonth.floor(tmin);
      if (
        ticks.length === 0 ||
        ticks[0].getTime() !== firstMonthBoundary.getTime()
      ) {
        return [tmin, ...ticks];
      }
      return ticks;
    },
    [layout.dates],
  );

  const todayXPx = useMemo(() => {
    if (layout.dates.length === 0) return null;
    const now = Date.now();
    const tmin = layout.dates[0].getTime();
    const tmax = layout.dates[layout.dates.length - 1].getTime();
    if (now < tmin || now > tmax) return null;
    return layout.x(new Date(now));
  }, [layout]);

  const yTicks = useMemo(() => {
    const step = layout.yMax > 16 ? 4 : layout.yMax > 8 ? 2 : 1;
    const ticks: number[] = [];
    for (let v = 0; v <= layout.yMax; v += step) ticks.push(v);
    return ticks;
  }, [layout.yMax]);

  const isDark = theme.palette.mode === "dark";
  const hasWeighted = track.filtered_points.length > 0 &&
    track.filtered_points.some((p, i) => Math.abs(p.hours - track.points[i]?.hours) > 0.01);

  return (
    <Box ref={wrapperRef} sx={{ position: "relative", width: "100%" }}>
      <svg
        width={width}
        height={height}
        onMouseMove={onMouseMove}
        onMouseLeave={() => setHover(null)}
        style={{ display: "block" }}
      >
        {/* Y-axis title */}
        <text
          x={-((height - layout.MARGIN.top - layout.MARGIN.bottom) / 2 + layout.MARGIN.top)}
          y={12}
          textAnchor="middle"
          transform="rotate(-90)"
          fontSize={11}
          fill={theme.palette.text.secondary}
        >
          Hours
        </text>

        {/* Y-axis grid + labels */}
        {yTicks.map((v) => (
          <g key={v}>
            <line
              x1={layout.MARGIN.left}
              x2={width - layout.MARGIN.right}
              y1={layout.y(v)}
              y2={layout.y(v)}
              stroke={theme.palette.divider}
              strokeDasharray="2,3"
            />
            <text
              x={layout.MARGIN.left - 8}
              y={layout.y(v) + 4}
              textAnchor="end"
              fontSize={11}
              fill={theme.palette.text.secondary}
            >
              {v}h
            </text>
          </g>
        ))}

        {/* Moon phase backdrop */}
        {track.moon_data.length > 0 && (
          <g>
            {track.moon_data.map((m, i) => {
              if (i >= layout.dates.length) return null;
              const xPos = layout.x(layout.dates[i]);
              const nextX = i + 1 < layout.dates.length
                ? layout.x(layout.dates[i + 1])
                : xPos + 1;
              const opacity = isDark
                ? 0.02 + (m.illumination_pct / 100) * 0.06
                : 0.01 + (m.illumination_pct / 100) * 0.04;
              return (
                <rect
                  key={i}
                  x={xPos}
                  y={layout.MARGIN.top}
                  width={Math.max(0.5, nextX - xPos)}
                  height={height - layout.MARGIN.top - layout.MARGIN.bottom}
                  fill={isDark ? "#ffffff" : "#000000"}
                  opacity={opacity}
                />
              );
            })}
          </g>
        )}

        {/* Month ticks + labels */}
        {monthTicks.map((t, i) => (
          <g key={i}>
            <line
              x1={layout.x(t)}
              x2={layout.x(t)}
              y1={height - layout.MARGIN.bottom}
              y2={height - layout.MARGIN.bottom + 4}
              stroke={theme.palette.divider}
            />
            <text
              x={layout.x(t)}
              y={height - layout.MARGIN.bottom + 17}
              textAnchor="middle"
              fontSize={10}
              fill={theme.palette.text.secondary}
            >
              {t.toLocaleDateString(undefined, { month: "short" })}
            </text>
          </g>
        ))}

        {/* Today marker */}
        {todayXPx != null && (
          <g>
            <line
              x1={todayXPx}
              x2={todayXPx}
              y1={layout.MARGIN.top}
              y2={height - layout.MARGIN.bottom}
              stroke={theme.palette.text.secondary}
              strokeWidth={1}
              strokeDasharray="3,3"
              opacity={0.7}
            />
            <text
              x={todayXPx}
              y={layout.MARGIN.top - 2}
              textAnchor="middle"
              fontSize={10}
              fill={theme.palette.text.secondary}
            >
              today
            </text>
          </g>
        )}

        {/* Raw hours curve — drawn first (behind filtered), thinner when filter active */}
        <path
          d={layout.line(track.points.map((p) => p.hours)) ?? undefined}
          fill="none"
          stroke={RIG_BLUE}
          strokeWidth={hasWeighted ? 1.5 : 2}
        />

        {/* Moon-filtered hours curve — continuous (no gaps at zero), drawn on top */}
        {hasWeighted && (
          <path
            d={layout.lineContinuous(track.filtered_points.map((p) => p.hours)) ?? undefined}
            fill="none"
            stroke={RIG_ORANGE}
            strokeWidth={2}
          />
        )}

        {/* Moon max altitude curve — subtle dashed, right y-axis */}
        <path
          d={layout.moonAltLine(track.moon_data.map((m) => m.max_altitude_deg)) ?? undefined}
          fill="none"
          stroke={theme.palette.text.disabled}
          strokeWidth={1}
          strokeDasharray="4,3"
          opacity={0.6}
        />

        {/* Right y-axis labels (moon altitude) */}
        {[0, 30, 60, 90].map((v) => (
          <text
            key={`rax-${v}`}
            x={width - layout.MARGIN.right + 8}
            y={layout.yRight(v) + 4}
            textAnchor="start"
            fontSize={10}
            fill={theme.palette.text.disabled}
          >
            {v}°
          </text>
        ))}
        <text
          x={-((height - layout.MARGIN.top - layout.MARGIN.bottom) / 2 + layout.MARGIN.top)}
          y={width - 6}
          textAnchor="middle"
          transform="rotate(-90)"
          fontSize={10}
          fill={theme.palette.text.disabled}
        >
          Moon alt
        </text>

        {/* Legend */}
        {hasWeighted && (
          <g transform={`translate(${width - layout.MARGIN.right - 130}, ${layout.MARGIN.top + 4})`}>
            <line x1={0} y1={0} x2={16} y2={0} stroke={RIG_BLUE} strokeWidth={1.5} />
            <text x={20} y={4} fontSize={9} fill={theme.palette.text.secondary}>Raw hours</text>
            <line x1={0} y1={14} x2={16} y2={14} stroke={RIG_ORANGE} strokeWidth={2} />
            <text x={20} y={18} fontSize={9} fill={theme.palette.text.secondary}>Effective hours</text>
          </g>
        )}

        {/* Hover crosshair */}
        {hover && (
          <>
            <line
              x1={hover.xPx}
              x2={hover.xPx}
              y1={layout.MARGIN.top}
              y2={height - layout.MARGIN.bottom}
              stroke={theme.palette.text.secondary}
              strokeWidth={1}
              strokeDasharray="2,2"
            />
            <circle
              cx={hover.xPx}
              cy={hover.yPxRaw}
              r={3.5}
              fill={RIG_BLUE}
              stroke={theme.palette.background.paper}
              strokeWidth={1.5}
            />
            {hasWeighted && (
              <circle
                cx={hover.xPx}
                cy={hover.yPxWeighted}
                r={3.5}
                fill={RIG_ORANGE}
                stroke={theme.palette.background.paper}
                strokeWidth={1.5}
              />
            )}
          </>
        )}
      </svg>

      {hover && (
        <Box
          sx={{
            position: "absolute",
            ...(hover.yPxRaw < height / 2
              ? { bottom: layout.MARGIN.bottom + 6 }
              : { top: 4 }),
            left: Math.min(hover.xPx + 10, width - 180),
            bgcolor: "background.paper",
            border: 1,
            borderColor: "divider",
            borderRadius: 1,
            p: 1,
            pointerEvents: "none",
            fontSize: 12,
            lineHeight: 1.4,
            minWidth: 140,
            boxShadow: 2,
          }}
        >
          <Typography variant="caption" fontWeight={600}>
            {hover.dateLabel}
            {hover.snappedToToday && (
              <Box
                component="span"
                sx={{ ml: 0.75, color: "text.secondary", fontWeight: 400 }}
              >
                (today)
              </Box>
            )}
          </Typography>
          <Box sx={{ color: RIG_BLUE }}>{hover.rawHours.toFixed(1)} h raw</Box>
          {hasWeighted && (
            <Box sx={{ color: RIG_ORANGE }}>{hover.weightedHours.toFixed(1)} h effective</Box>
          )}
          {(hover.illuminationPct != null || hover.minSeparationDeg != null) && (
            <Box sx={{ color: "text.secondary", fontSize: 11 }}>
              Moon: {hover.illuminationPct != null ? `${hover.illuminationPct.toFixed(0)}%` : "—"}
              {hover.minSeparationDeg != null ? ` · ${hover.minSeparationDeg.toFixed(0)}° sep` : ""}
              {hover.maxAltitudeDeg != null ? ` · ${hover.maxAltitudeDeg.toFixed(0)}° alt` : ""}
            </Box>
          )}
        </Box>
      )}
    </Box>
  );
}
