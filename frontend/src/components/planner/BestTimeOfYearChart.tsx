/**
 * "Best time of year" chart for the planner detail panel.
 *
 * Curve across the calendar year showing hours per night that the
 * target spends above a chosen altitude threshold (or the location's
 * custom horizon) during astronomical darkness, optionally with
 * moon avoidance (LRGB mode).
 *
 * X-axis: 12 months. Y-axis: hours, auto-scaled from data (0 to
 * max(data, 12) so nights approaching 12 h astro-dark still anchor a
 * sensible scale when the target tops out short). Hover: vertical
 * crosshair + date + hours tooltip.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import * as d3 from "d3";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { useTheme } from "@mui/material/styles";
import type { AnnualHoursResponse } from "@/api/planner";
import { RIG_BLUE } from "@/lib/rigColors";

interface Props {
  track: AnnualHoursResponse;
  height?: number;
}

const COLOR_OBJECT = RIG_BLUE;

interface HoverInfo {
  xPx: number;
  yPx: number;
  dateLabel: string;
  hours: number;
  snappedToToday: boolean;
}

// Magnetic-snap radius around the today line, in CSS pixels. Wide
// enough to be easy to land on, narrow enough that the snap feels
// intentional. Mirrors ``MERIDIAN_SNAP_PX`` on SkyPositionGraph.
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
    const MARGIN = { top: 10, right: 20, bottom: 26, left: 44 };
    // Anchor each point at noon UTC of its evening date so the curve
    // aligns with the month-tick grid on any timezone without half-day
    // drift from "YYYY-MM-DD" being parsed as UTC midnight.
    const dates = track.points.map((p) => new Date(`${p.date}T12:00:00Z`));
    const tmin = dates[0] ?? new Date();
    const tmax = dates[dates.length - 1] ?? new Date();

    const maxHours = Math.max(...track.points.map((p) => p.hours), 0);
    // Anchor the y-scale at 12 h unless the data exceeds it (polar
    // summer twilight can stretch beyond) — users comparing targets
    // benefit from a stable vertical reference.
    const yMax = Math.max(12, Math.ceil(maxHours + 0.5));

    const x = d3
      .scaleTime()
      .domain([tmin, tmax])
      .range([MARGIN.left, width - MARGIN.right]);

    const y = d3
      .scaleLinear()
      .domain([0, yMax])
      .range([height - MARGIN.bottom, MARGIN.top]);

    // Raw data with cosmetic ``curveMonotoneX``. The spline rounds
    // sharp corners slightly but is monotone-preserving, so real
    // horizon spikes stay faithful (no overshoot) and the tooltip
    // at each sampled night agrees with the drawn line. Zero-hour
    // nights break the line via ``defined`` so the curve gaps over
    // unreachable seasons instead of hugging the baseline.
    const line = d3
      .line<number>()
      .defined((d) => d > 0.01)
      .x((_, i) => x(dates[i]))
      .y((d) => y(Math.max(0, Math.min(yMax, d))))
      .curve(d3.curveMonotoneX);

    return { MARGIN, dates, x, y, line, yMax };
  }, [track, width, height]);

  function onMouseMove(e: React.MouseEvent<SVGSVGElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    if (mx < layout.MARGIN.left || mx > width - layout.MARGIN.right) {
      setHover(null);
      return;
    }

    // Magnetic snap: when the cursor is within TODAY_SNAP_PX of the
    // today line, lock onto today exactly. Gives the user a "positive
    // stop" so the today marker feels like a clickable detent rather
    // than a passive visual reference. Mirrors the meridian snap on
    // SkyPositionGraph.
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
    const p = track.points[clamped];
    setHover({
      xPx: snapXPx ?? layout.x(layout.dates[clamped]),
      yPx: layout.y(Math.max(0, Math.min(layout.yMax, p.hours))),
      dateLabel: layout.dates[clamped].toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
      }),
      hours: p.hours,
      snappedToToday: snapXPx != null,
    });
  }

  const monthTicks = useMemo(
    () => d3.timeMonths(layout.dates[0], layout.dates[layout.dates.length - 1]),
    [layout.dates],
  );

  // Today marker — only drawn when the chart's year range actually
  // covers "now". Silently omitted for past or future year views.
  const todayXPx = useMemo(() => {
    if (layout.dates.length === 0) return null;
    const now = Date.now();
    const tmin = layout.dates[0].getTime();
    const tmax = layout.dates[layout.dates.length - 1].getTime();
    if (now < tmin || now > tmax) return null;
    return layout.x(new Date(now));
  }, [layout]);

  // Y-axis tick values — simple integer ladder anchored to yMax.
  const yTicks = useMemo(() => {
    const step = layout.yMax > 16 ? 4 : layout.yMax > 8 ? 2 : 1;
    const ticks: number[] = [];
    for (let v = 0; v <= layout.yMax; v += step) ticks.push(v);
    return ticks;
  }, [layout.yMax]);

  return (
    <Box ref={wrapperRef} sx={{ position: "relative", width: "100%" }}>
      <svg
        width={width}
        height={height}
        onMouseMove={onMouseMove}
        onMouseLeave={() => setHover(null)}
        style={{ display: "block" }}
      >
        {/* Y-axis title — rotated so it sits flush against the tick labels. */}
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

        {/* Today marker — dashed vertical line with "today" label,
            drawn behind the hours curve so the data stays foreground. */}
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

        {/* Hours curve */}
        <path
          d={layout.line(track.points.map((p) => p.hours)) ?? undefined}
          fill="none"
          stroke={COLOR_OBJECT}
          strokeWidth={2}
        />

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
              cy={hover.yPx}
              r={3.5}
              fill={COLOR_OBJECT}
              stroke={theme.palette.background.paper}
              strokeWidth={1.5}
            />
          </>
        )}
      </svg>

      {hover && (
        <Box
          sx={{
            position: "absolute",
            // Flip the tooltip vertically so it sits opposite the
            // hover dot: dot in the top half of the chart → tooltip
            // pinned to the bottom, and vice versa. Keeps the line
            // itself always unobscured. The 32 px bottom offset
            // clears the x-axis tick labels.
            ...(hover.yPx < height / 2
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
          <div>{hover.hours.toFixed(1)} h</div>
        </Box>
      )}
    </Box>
  );
}
