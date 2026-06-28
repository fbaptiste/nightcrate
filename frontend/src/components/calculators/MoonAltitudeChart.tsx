/**
 * Standalone Moon-altitude-over-the-year chart for the Sky Conditions
 * calculator. Plots the Moon's peak altitude during astronomical darkness each
 * night (left axis, 0–90°), illumination as per-night background shading
 * (brighter = fuller), and solid new-moon (below) / full-moon (above) markers
 * the hover scrubber snaps to. D3 patterns mirror the planner's
 * BestTimeOfYearChart.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import * as d3 from "d3";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { useTheme } from "@mui/material/styles";
import type { MoonYearResponse } from "@/api/planner";
import { RIG_BLUE, RIG_ORANGE, RIG_TEAL } from "@/lib/rigColors";

interface Props {
  data: MoonYearResponse;
  height?: number;
}

interface HoverInfo {
  xPx: number;
  dateLabel: string;
  altitudeDeg: number | null;
  illuminationPct: number;
  phase: "new" | "full" | null;
}

const SNAP_PX = 9; // detent radius around a new/full-moon marker

function parseDate(iso: string): Date {
  return new Date(`${iso}T12:00:00Z`);
}

export default function MoonAltitudeChart({ data, height = 300 }: Props) {
  const theme = useTheme();
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const [width, setWidth] = useState(720);
  const [hover, setHover] = useState<HoverInfo | null>(null);

  useEffect(() => {
    const el = wrapperRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width ?? 720;
      setWidth(Math.max(420, Math.floor(w)));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const layout = useMemo(() => {
    const MARGIN = { top: 26, right: 18, bottom: 40, left: 46 };
    const dates = data.points.map((p) => parseDate(p.date));
    const tmin = dates[0] ?? new Date();
    const tmax = dates[dates.length - 1] ?? new Date();

    const x = d3
      .scaleTime()
      .domain([tmin, tmax])
      .range([MARGIN.left, width - MARGIN.right]);
    const yAlt = d3
      .scaleLinear()
      .domain([0, 90])
      .range([height - MARGIN.bottom, MARGIN.top]);

    const altLine = d3
      .line<number | null>()
      .defined((d) => d != null)
      .x((_, i) => x(dates[i]))
      .y((d) => yAlt(Math.max(0, d!)))
      .curve(d3.curveMonotoneX);

    return { MARGIN, dates, x, yAlt, altLine };
  }, [data, width, height]);

  // Index by ISO date for exact lookup when snapping to a phase marker.
  const idxByDate = useMemo(() => {
    const m = new Map<string, number>();
    data.points.forEach((p, i) => m.set(p.date, i));
    return m;
  }, [data]);

  const markers = useMemo(() => {
    const make = (iso: string, type: "new" | "full") => ({
      iso,
      type,
      xPx: layout.x(parseDate(iso)),
    });
    return [
      ...data.new_moons.map((d) => make(d, "new" as const)),
      ...data.full_moons.map((d) => make(d, "full" as const)),
    ];
  }, [data, layout]);

  const monthTicks = useMemo(() => {
    const tmin = layout.dates[0];
    const tmax = layout.dates[layout.dates.length - 1];
    if (!tmin || !tmax) return [];
    const ticks = d3.timeMonths(tmin, tmax);
    const first = d3.timeMonth.floor(tmin);
    if (ticks.length === 0 || ticks[0].getTime() !== first.getTime()) {
      return [tmin, ...ticks];
    }
    return ticks;
  }, [layout.dates]);

  function handleHover(svg: SVGSVGElement, clientX: number) {
    const rect = svg.getBoundingClientRect();
    const mx = clientX - rect.left;
    if (mx < layout.MARGIN.left || mx > width - layout.MARGIN.right) {
      setHover(null);
      return;
    }

    // Snap to the nearest new/full-moon marker within the detent radius.
    let snap: { iso: string; type: "new" | "full"; xPx: number } | null = null;
    let best = SNAP_PX;
    for (const mk of markers) {
      const dpx = Math.abs(mx - mk.xPx);
      if (dpx <= best) {
        best = dpx;
        snap = mk;
      }
    }

    let idx: number;
    let xPx: number;
    if (snap) {
      idx = idxByDate.get(snap.iso) ?? 0;
      xPx = snap.xPx;
    } else {
      const t = layout.x.invert(mx);
      idx = d3.bisector((d: Date) => d).center(layout.dates, t);
      idx = Math.max(0, Math.min(layout.dates.length - 1, idx));
      xPx = layout.x(layout.dates[idx]);
    }

    const p = data.points[idx];
    setHover({
      xPx,
      dateLabel: layout.dates[idx].toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
      }),
      altitudeDeg: p.max_altitude_deg,
      illuminationPct: p.illumination_pct,
      phase: snap?.type ?? null,
    });
  }

  const altColor = RIG_BLUE;
  const isDark = theme.palette.mode === "dark";
  // New moons sit below the plot, full moons above it — marker height tracks
  // illumination (low = new/dark, high = full/bright).
  const newMarkerY = height - layout.MARGIN.bottom + 22;
  const fullMarkerY = layout.MARGIN.top - 18;

  return (
    <Box ref={wrapperRef} sx={{ position: "relative", width: "100%" }}>
      <svg
        width={width}
        height={height}
        onMouseMove={(e) => handleHover(e.currentTarget, e.clientX)}
        onMouseLeave={() => setHover(null)}
        onTouchStart={(e) => {
          e.preventDefault();
          handleHover(e.currentTarget, e.touches[0].clientX);
        }}
        onTouchMove={(e) => {
          e.preventDefault();
          handleHover(e.currentTarget, e.touches[0].clientX);
        }}
        onTouchEnd={() => setHover(null)}
        style={{
          display: "block",
          touchAction: "none",
          WebkitTouchCallout: "none",
          WebkitUserSelect: "none",
          userSelect: "none",
        }}
      >
        {/* Moon illumination backdrop — per-night shading, brighter = fuller
            moon (same treatment as the planner's Best-time-of-year chart). */}
        {data.points.map((p, i) => {
          if (i >= layout.dates.length) return null;
          const xPos = layout.x(layout.dates[i]);
          const nextX =
            i + 1 < layout.dates.length ? layout.x(layout.dates[i + 1]) : xPos + 1;
          const opacity = isDark
            ? 0.03 + (p.illumination_pct / 100) * 0.1
            : 0.04 + (p.illumination_pct / 100) * 0.14;
          return (
            <rect
              key={`bg-${i}`}
              x={xPos}
              y={layout.MARGIN.top}
              width={Math.max(0.5, nextX - xPos)}
              height={height - layout.MARGIN.top - layout.MARGIN.bottom}
              fill={isDark ? "#ffffff" : "#000000"}
              opacity={opacity}
            />
          );
        })}

        {/* Left axis (altitude) grid + labels */}
        {[0, 30, 60, 90].map((v) => (
          <g key={`alt-${v}`}>
            <line
              x1={layout.MARGIN.left}
              x2={width - layout.MARGIN.right}
              y1={layout.yAlt(v)}
              y2={layout.yAlt(v)}
              stroke={theme.palette.divider}
              strokeDasharray="2,3"
            />
            <text
              x={layout.MARGIN.left - 8}
              y={layout.yAlt(v) + 4}
              textAnchor="end"
              fontSize={11}
              fill={altColor}
            >
              {v}&deg;
            </text>
          </g>
        ))}

        {/* Left axis title */}
        <text
          x={-((height - layout.MARGIN.top - layout.MARGIN.bottom) / 2 + layout.MARGIN.top)}
          y={12}
          textAnchor="middle"
          transform="rotate(-90)"
          fontSize={11}
          fill={altColor}
        >
          Moon altitude
        </text>

        {/* New-moon guide lines (dark-sky windows) */}
        {markers
          .filter((m) => m.type === "new")
          .map((m) => (
            <line
              key={`nl-${m.iso}`}
              x1={m.xPx}
              x2={m.xPx}
              y1={layout.MARGIN.top}
              y2={height - layout.MARGIN.bottom}
              stroke={RIG_TEAL}
              strokeWidth={1}
              opacity={0.22}
            />
          ))}

        {/* Month ticks + labels */}
        {monthTicks.map((t, i) => (
          <g key={`m-${i}`}>
            <line
              x1={layout.x(t)}
              x2={layout.x(t)}
              y1={height - layout.MARGIN.bottom}
              y2={height - layout.MARGIN.bottom + 4}
              stroke={theme.palette.divider}
            />
            <text
              x={layout.x(t)}
              y={height - layout.MARGIN.bottom + 16}
              textAnchor="middle"
              fontSize={10}
              fill={theme.palette.text.secondary}
            >
              {t.toLocaleDateString(undefined, { month: "short" })}
            </text>
          </g>
        ))}

        {/* Moon altitude line (primary, left axis) */}
        <path
          d={layout.altLine(data.points.map((p) => p.max_altitude_deg)) ?? undefined}
          fill="none"
          stroke={altColor}
          strokeWidth={2}
        />

        {/* New moon markers — solid teal, below the plot */}
        {/* Full moon markers — solid orange, above the plot */}
        {markers.map((m) => (
          <circle
            key={`mk-${m.iso}`}
            cx={m.xPx}
            cy={m.type === "new" ? newMarkerY : fullMarkerY}
            r={4}
            fill={m.type === "new" ? RIG_TEAL : RIG_ORANGE}
          />
        ))}

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
            {hover.altitudeDeg != null && (
              <circle
                cx={hover.xPx}
                cy={layout.yAlt(Math.max(0, hover.altitudeDeg))}
                r={3.5}
                fill={altColor}
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
            top: 4,
            left: Math.min(hover.xPx + 10, width - 190),
            bgcolor: "background.paper",
            border: 1,
            borderColor: "divider",
            borderRadius: 1,
            p: 1,
            pointerEvents: "none",
            fontSize: 12,
            lineHeight: 1.5,
            minWidth: 150,
            boxShadow: 2,
          }}
        >
          <Typography variant="caption" fontWeight={600}>
            {hover.dateLabel}
            {hover.phase && (
              <Box
                component="span"
                sx={{
                  ml: 0.75,
                  fontWeight: 700,
                  color: hover.phase === "new" ? RIG_TEAL : RIG_ORANGE,
                }}
              >
                {hover.phase === "new" ? "New moon" : "Full moon"}
              </Box>
            )}
          </Typography>
          <Box sx={{ color: altColor }}>
            {hover.altitudeDeg == null || hover.altitudeDeg < 0
              ? "Below horizon while dark"
              : `${hover.altitudeDeg.toFixed(0)}° peak altitude`}
          </Box>
          <Box sx={{ color: "text.secondary", fontSize: 11 }}>
            {hover.illuminationPct.toFixed(0)}% illuminated
          </Box>
        </Box>
      )}

      {/* Legend */}
      <Box
        sx={{
          display: "flex",
          flexWrap: "wrap",
          gap: 2,
          mt: 1,
          fontSize: 12,
          color: "text.secondary",
          alignItems: "center",
        }}
      >
        <LegendDot color={altColor} label="Moon altitude" />
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
          <Box
            sx={{
              width: 28,
              height: 12,
              borderRadius: 0.5,
              border: 1,
              borderColor: "divider",
              background: isDark
                ? "linear-gradient(to right, rgba(255,255,255,0.04), rgba(255,255,255,0.5))"
                : "linear-gradient(to right, rgba(0,0,0,0.03), rgba(0,0,0,0.4))",
            }}
          />
          <span>Illumination (shading)</span>
        </Box>
        <LegendDot color={RIG_TEAL} label="New moon" filled />
        <LegendDot color={RIG_ORANGE} label="Full moon" filled />
      </Box>
    </Box>
  );
}

function LegendDot({
  color,
  label,
  filled,
}: {
  color: string;
  label: string;
  filled?: boolean;
}) {
  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
      {filled ? (
        <Box
          sx={{ width: 10, height: 10, borderRadius: "50%", bgcolor: color }}
        />
      ) : (
        <Box sx={{ width: 18, height: 0, borderTop: `2px solid ${color}` }} />
      )}
      <span>{label}</span>
    </Box>
  );
}
