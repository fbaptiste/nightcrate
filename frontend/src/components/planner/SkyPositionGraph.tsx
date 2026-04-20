/**
 * Sky-position graph for the planner detail panel.
 *
 * D3 SVG with twilight bands, object altitude, moon altitude, and the
 * location's horizon reference (flat or custom). Visual language matches
 * the weather tool's hourly timeline — twilight gradient, colorblind
 * blue for the object, dashed orange for the moon.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import * as d3 from "d3";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useTheme } from "@mui/material/styles";
import type { SkyTrackResponse } from "@/api/planner";
import { RIG_BLUE, RIG_ORANGE } from "@/lib/rigColors";

interface Props {
  track: SkyTrackResponse;
  tz: string;
  height?: number;
}

// Object + moon colours reuse the canonical rig palette — keeps the
// planner visually consistent with the rest of the app and stays on
// the colorblind-safe blue/orange/teal trio.
const COLOR_OBJECT = RIG_BLUE;
const COLOR_MOON = RIG_ORANGE;

function blockedSkyFill(mode: "light" | "dark") {
  // Filled area below the horizon (sky that the horizon profile blocks).
  // Lightly tinted so it reads as "blocked" without dominating the chart.
  return mode === "dark" ? "rgba(180, 180, 180, 0.14)" : "rgba(60, 60, 60, 0.10)";
}

// Twilight band colors — deepest at astronomical dark, lightest approaching
// civil dusk/dawn. Chosen to read well on both light and dark themes.
function twilightFill(mode: "light" | "dark") {
  if (mode === "dark") {
    return {
      daylight: "transparent",
      civil: "rgba(120, 140, 180, 0.18)",
      nautical: "rgba(60, 80, 130, 0.30)",
      astronomical: "rgba(20, 30, 60, 0.55)",
    };
  }
  return {
    daylight: "transparent",
    civil: "rgba(255, 220, 160, 0.35)",
    nautical: "rgba(120, 140, 200, 0.35)",
    astronomical: "rgba(40, 55, 100, 0.35)",
  };
}

interface HoverInfo {
  xPx: number;
  timeLocal: string;
  objAlt: number;
  objAz: number;
  moonAlt: number;
  aboveHorizon: boolean;
  snappedToMeridian: boolean;
}

// Magnetic-snap radius around the meridian line, in CSS pixels. Wide
// enough to be easy to land on without a precise mouse, narrow enough
// that it feels intentional rather than sticky.
const MERIDIAN_SNAP_PX = 6;

export default function SkyPositionGraph({ track, tz, height = 260 }: Props) {
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

  const tw = twilightFill(theme.palette.mode);
  const blockedFill = blockedSkyFill(theme.palette.mode);

  const layout = useMemo(() => {
    const MARGIN = { top: 10, right: 20, bottom: 28, left: 44 };
    const times = track.times_utc.map((t) => new Date(t));
    const tmin = times[0] ?? new Date();
    const tmax = times[times.length - 1] ?? new Date();

    const x = d3
      .scaleTime()
      .domain([tmin, tmax])
      .range([MARGIN.left, width - MARGIN.right]);

    const y = d3
      .scaleLinear()
      .domain([0, 90])
      .range([height - MARGIN.bottom, MARGIN.top]);

    // Object + moon lines skip samples below the horizon floor — below-0°
    // samples just don't draw rather than getting pinned along the baseline.
    const objLine = d3
      .line<number>()
      .defined((d) => d >= 0)
      .x((_, i) => x(times[i]))
      .y((d) => y(Math.min(90, d)))
      .curve(d3.curveMonotoneX);

    const moonLine = d3
      .line<number>()
      .defined((d) => d >= 0)
      .x((_, i) => x(times[i]))
      .y((d) => y(Math.min(90, d)))
      .curve(d3.curveMonotoneX);

    // Blocked-sky area: from y=0 up to the horizon altitude at each sample.
    // Drawn in a neutral tint with no stroke so a location's custom
    // horizon reads as shaded obstruction, not a line.
    const blockedArea = d3
      .area<number>()
      .x((_, i) => x(times[i]))
      .y0(() => y(0))
      .y1((d) => y(Math.max(0, Math.min(90, d))))
      .curve(d3.curveMonotoneX);

    // Object-altitude fill above horizon — visual cue for "visible time".
    const visibleArea = d3
      .area<number>()
      .x((_, i) => x(times[i]))
      .y0((_, i) => y(track.horizon_altitude_at_object_az[i]))
      .y1((_, i) => y(Math.max(0, Math.min(90, track.object_altitude_deg[i]))))
      .defined(
        (_, i) =>
          track.object_altitude_deg[i] > track.horizon_altitude_at_object_az[i],
      )
      .curve(d3.curveMonotoneX);

    return { MARGIN, times, x, y, objLine, moonLine, blockedArea, visibleArea };
  }, [track, width, height]);

  function bandRect(startIso: string | null, endIso: string | null, fill: string) {
    if (!startIso || !endIso) return null;
    const sx = layout.x(new Date(startIso));
    const ex = layout.x(new Date(endIso));
    if (ex <= sx) return null;
    return (
      <rect
        x={sx}
        y={layout.MARGIN.top}
        width={ex - sx}
        height={height - layout.MARGIN.top - layout.MARGIN.bottom}
        fill={fill}
      />
    );
  }

  function onMouseMove(e: React.MouseEvent<SVGSVGElement>) {
    const svg = e.currentTarget;
    const rect = svg.getBoundingClientRect();
    const mx = e.clientX - rect.left;

    // Magnetic snap: when the cursor is close to the meridian line,
    // lock onto the analytical transit instant exactly. Matters for
    // two reasons — (1) readout shows the precise transit time /
    // altitude rather than a 5-minute sampled neighbour, and (2)
    // gives the user a "positive stop" that feels deliberate.
    let snapTime: Date | null = null;
    let snapX = mx;
    if (track.transit_time_utc) {
      const meridianT = new Date(track.transit_time_utc);
      const meridianX = layout.x(meridianT);
      if (
        meridianX >= layout.MARGIN.left &&
        meridianX <= width - layout.MARGIN.right &&
        Math.abs(mx - meridianX) <= MERIDIAN_SNAP_PX
      ) {
        snapTime = meridianT;
        snapX = meridianX;
      }
    }

    const t = snapTime ?? layout.x.invert(mx);
    const idx = d3.bisector((d: Date) => d).left(layout.times, t);
    const clamped = Math.max(0, Math.min(layout.times.length - 1, idx));
    // When snapped, use the sky-track's analytical peak altitude
    // (equal to the altitude at transit since peak=transit when
    // transit lies inside the charted window) rather than a
    // 5-minute-sampled neighbour. Azimuth + moon stay sampled — the
    // chart doesn't expose sub-minute analytical values for those.
    const objAlt = snapTime ? track.peak_altitude_deg : track.object_altitude_deg[clamped];
    const horizon = track.horizon_altitude_at_object_az[clamped];
    const localTime = (snapTime ?? layout.times[clamped]).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      timeZone: tz,
    });
    setHover({
      xPx: snapTime ? snapX : layout.x(layout.times[clamped]),
      timeLocal: localTime,
      objAlt,
      objAz: track.object_azimuth_deg[clamped],
      moonAlt: track.moon_altitude_deg[clamped],
      aboveHorizon: objAlt > horizon,
      snappedToMeridian: snapTime != null,
    });
  }

  const ticks = layout.x.ticks(6);

  return (
    <Box ref={wrapperRef} sx={{ position: "relative", width: "100%" }}>
      <svg
        width={width}
        height={height}
        onMouseMove={onMouseMove}
        onMouseLeave={() => setHover(null)}
        style={{ display: "block" }}
      >
        {/* Twilight bands */}
        {bandRect(track.twilight.sunset_utc, track.twilight.civil_end_utc, tw.civil)}
        {bandRect(track.twilight.civil_end_utc, track.twilight.nautical_end_utc, tw.nautical)}
        {bandRect(track.twilight.nautical_end_utc, track.twilight.astro_start_utc, tw.nautical)}
        {bandRect(track.twilight.astro_start_utc, track.twilight.astro_end_utc, tw.astronomical)}
        {bandRect(track.twilight.astro_end_utc, track.twilight.nautical_start_utc, tw.nautical)}
        {bandRect(track.twilight.nautical_start_utc, track.twilight.civil_start_utc, tw.nautical)}
        {bandRect(track.twilight.civil_start_utc, track.twilight.sunrise_utc, tw.civil)}

        {/* Y-axis grid + labels */}
        {[0, 30, 60, 90].map((alt) => (
          <g key={alt}>
            <line
              x1={layout.MARGIN.left}
              x2={width - layout.MARGIN.right}
              y1={layout.y(alt)}
              y2={layout.y(alt)}
              stroke={theme.palette.divider}
              strokeDasharray="2,3"
            />
            <text
              x={layout.MARGIN.left - 8}
              y={layout.y(alt) + 4}
              textAnchor="end"
              fontSize={11}
              fill={theme.palette.text.secondary}
            >
              {alt}°
            </text>
          </g>
        ))}

        {/* X-axis ticks */}
        {ticks.map((t, i) => (
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
              y={height - layout.MARGIN.bottom + 18}
              textAnchor="middle"
              fontSize={11}
              fill={theme.palette.text.secondary}
            >
              {t.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", timeZone: tz })}
            </text>
          </g>
        ))}

        {/* Blocked sky (below horizon) — shaded region, no outline. */}
        <path
          d={layout.blockedArea(track.horizon_altitude_at_object_az) ?? undefined}
          fill={blockedFill}
          stroke="none"
        />

        {/* Shaded visible area */}
        <path
          d={layout.visibleArea(track.object_altitude_deg) ?? undefined}
          fill={COLOR_OBJECT}
          fillOpacity={0.15}
        />

        {/* Moon altitude */}
        <path
          d={layout.moonLine(track.moon_altitude_deg) ?? undefined}
          fill="none"
          stroke={COLOR_MOON}
          strokeWidth={1.5}
          strokeDasharray="6,4"
        />

        {/* Object altitude */}
        <path
          d={layout.objLine(track.object_altitude_deg) ?? undefined}
          fill="none"
          stroke={COLOR_OBJECT}
          strokeWidth={2}
        />

        {/* Peak-altitude dot */}
        {(() => {
          const peakT = new Date(track.peak_time_utc);
          const cx = layout.x(peakT);
          const cy = layout.y(Math.max(0, Math.min(90, track.peak_altitude_deg)));
          return (
            <g>
              <circle
                cx={cx}
                cy={cy}
                r={4}
                fill={COLOR_OBJECT}
                stroke={theme.palette.background.paper}
                strokeWidth={1.5}
              />
            </g>
          );
        })()}

        {/* Meridian crossing — vertical dashed line with label. Drawn only
            when transit falls inside the display window. */}
        {track.transit_time_utc &&
          (() => {
            const tx = layout.x(new Date(track.transit_time_utc));
            if (tx < layout.MARGIN.left || tx > width - layout.MARGIN.right) return null;
            return (
              <g>
                <line
                  x1={tx}
                  x2={tx}
                  y1={layout.MARGIN.top}
                  y2={height - layout.MARGIN.bottom}
                  stroke={theme.palette.text.secondary}
                  strokeWidth={1}
                  strokeDasharray="3,3"
                  opacity={0.7}
                />
                <text
                  x={tx}
                  y={layout.MARGIN.top - 2}
                  textAnchor="middle"
                  fontSize={10}
                  fill={theme.palette.text.secondary}
                >
                  meridian
                </text>
              </g>
            );
          })()}

        {/* Hover marker */}
        {hover && (
          <line
            x1={hover.xPx}
            x2={hover.xPx}
            y1={layout.MARGIN.top}
            y2={height - layout.MARGIN.bottom}
            stroke={theme.palette.text.secondary}
            strokeWidth={1}
            strokeDasharray="2,2"
          />
        )}
      </svg>

      {hover && (
        <Box
          sx={{
            position: "absolute",
            top: 4,
            left: Math.min(hover.xPx + 10, width - 220),
            bgcolor: "background.paper",
            border: 1,
            borderColor: "divider",
            borderRadius: 1,
            p: 1,
            pointerEvents: "none",
            fontSize: 12,
            lineHeight: 1.4,
            minWidth: 180,
            boxShadow: 2,
          }}
        >
          <Typography variant="caption" fontWeight={600}>
            {hover.timeLocal}
            {hover.snappedToMeridian && (
              <Box
                component="span"
                sx={{ ml: 0.75, color: "text.secondary", fontWeight: 400 }}
              >
                (meridian)
              </Box>
            )}
          </Typography>
          <div>
            Object: {hover.objAlt.toFixed(1)}° alt, {hover.objAz.toFixed(0)}° az
          </div>
          <div>Moon: {hover.moonAlt.toFixed(1)}° alt</div>
          <div style={{ color: hover.aboveHorizon ? COLOR_OBJECT : undefined }}>
            {hover.aboveHorizon ? "Visible" : "Below horizon"}
          </div>
        </Box>
      )}

      {/* Legend */}
      <Stack
        direction="row"
        gap={2}
        flexWrap="wrap"
        sx={{ mt: 1, px: 1 }}
        alignItems="center"
      >
        <Stack direction="row" gap={0.75} alignItems="center">
          <Box
            sx={{
              width: 18,
              height: 2,
              bgcolor: COLOR_OBJECT,
              borderRadius: 0.5,
            }}
          />
          <Typography variant="caption" color="text.secondary">
            Object
          </Typography>
        </Stack>
        <Stack direction="row" gap={0.75} alignItems="center">
          <Box
            sx={{
              width: 18,
              height: 2,
              background: `repeating-linear-gradient(90deg, ${COLOR_MOON} 0 4px, transparent 4px 8px)`,
            }}
          />
          <Typography variant="caption" color="text.secondary">
            Moon
          </Typography>
        </Stack>
        <Stack direction="row" gap={0.75} alignItems="center">
          <Box sx={{ width: 18, height: 10, bgcolor: blockedFill, borderRadius: 0.5 }} />
          <Typography variant="caption" color="text.secondary">
            Below horizon
          </Typography>
        </Stack>
      </Stack>
    </Box>
  );
}
