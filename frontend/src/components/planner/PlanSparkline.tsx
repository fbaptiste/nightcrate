/**
 * Compact best-time-of-year sparkline for wishlist plan rows.
 *
 * SVG-only (~160x32 px), no hover/tooltip. Draws the annual hours
 * curve with a today-marker vertical line and highlighted date range
 * zones matching the assignment editor's visual style.
 */
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import * as d3 from "d3";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { useTheme } from "@mui/material/styles";
import { fetchAnnualHours, type AnnualHoursPoint } from "@/api/planner";
import type { DateRangeOut } from "@/api/wishlist";
import { RIG_BLUE, RIG_ORANGE } from "@/lib/rigColors";

interface Props {
  dsoId: number;
  locationId: number;
  horizonId: number;
  moonSepDeg?: number;
  dateRanges?: DateRangeOut[];
  width?: number;
  height?: number;
}

const PADDING = 2;

export default function PlanSparkline({
  dsoId,
  locationId,
  horizonId,
  moonSepDeg = 0,
  dateRanges = [],
  width = 160,
  height = 32,
}: Props) {
  const theme = useTheme();

  const { data, isLoading } = useQuery({
    queryKey: ["annual-hours", dsoId, locationId, horizonId, moonSepDeg],
    queryFn: () =>
      fetchAnnualHours(dsoId, locationId, {
        horizonId,
        moonSepDeg,
      }),
    staleTime: 60 * 60_000,
  });

  const layout = useMemo(() => {
    if (!data?.points || data.points.length === 0) return null;

    const pts: AnnualHoursPoint[] =
      data.filtered_points?.length > 0 ? data.filtered_points : data.points;
    const xScale = d3
      .scaleTime()
      .domain([new Date(pts[0].date), new Date(pts[pts.length - 1].date)])
      .range([PADDING, width - PADDING]);
    const maxH = Math.ceil(d3.max(pts, (d) => d.hours) ?? 1);
    const yScale = d3
      .scaleLinear()
      .domain([0, Math.max(maxH, 1)])
      .range([height - PADDING, PADDING]);

    const line = d3
      .line<AnnualHoursPoint>()
      .x((d) => xScale(new Date(d.date)))
      .y((d) => yScale(d.hours))
      .curve(d3.curveMonotoneX);

    // Anchor "today" to the backend location-tz date, not the raw UTC instant
    // (which lands a day ahead in the evening). null if outside the year.
    const todayX = data.today ? xScale(new Date(data.today)) : null;
    return { xScale, yScale, pathD: line(pts), todayX };
  }, [data, width, height]);

  if (isLoading) {
    return (
      <Box sx={{ width, height, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <Typography variant="caption" color="text.disabled" sx={{ fontSize: "0.6rem" }}>
          ...
        </Typography>
      </Box>
    );
  }

  if (!layout?.pathD) return null;

  const isDark = theme.palette.mode === "dark";
  const todayColor = isDark ? "#ffffff55" : "#00000033";
  const rangeColor = `${RIG_ORANGE}44`;

  return (
    <svg width={width} height={height} style={{ display: "block", flexShrink: 0 }}>
      {/* Date range highlights */}
      {dateRanges.map((dr, i) => {
        if (!dr.start_date || !dr.end_date) return null;
        const x1 = layout.xScale(new Date(dr.start_date));
        const x2 = layout.xScale(new Date(dr.end_date));
        return (
          <rect
            key={i}
            x={x1}
            y={PADDING}
            width={Math.max(1, x2 - x1)}
            height={height - PADDING * 2}
            fill={rangeColor}
          />
        );
      })}
      {/* Today line */}
      {layout.todayX != null && layout.todayX >= PADDING && layout.todayX <= width - PADDING && (
        <line
          x1={layout.todayX}
          y1={PADDING}
          x2={layout.todayX}
          y2={height - PADDING}
          stroke={todayColor}
          strokeWidth={1}
          strokeDasharray="2,2"
        />
      )}
      {/* Hours curve */}
      <path d={layout.pathD} fill="none" stroke={RIG_BLUE} strokeWidth={1.5} />
    </svg>
  );
}
