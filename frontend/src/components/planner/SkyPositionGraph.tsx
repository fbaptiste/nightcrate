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
import { RIG_BLUE, RIG_ORANGE, RIG_TEAL } from "@/lib/rigColors";

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
// "Now" indicator colour — distinct from object/moon so the vertical
// line and its triangular anchor read as "this is happening now" at
// a glance. Teal is already in the colorblind-safe rig palette.
const COLOR_NOW = RIG_TEAL;

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
  moonSep: number;
  aboveHorizon: boolean;
  /** ``null`` when hover isn't magnetically snapped to a landmark;
   *  otherwise a lowercase short label ("meridian", "astro dark",
   *  "nautical dark", "civil dark") for the tooltip annotation. */
  snapLabel: string | null;
}

// Magnetic-snap radius around the meridian + twilight boundary lines,
// in CSS pixels. Wide enough to be easy to land on without a precise
// mouse, narrow enough that it feels intentional rather than sticky.
const SNAP_PX = 6;

// Twilight + meridian + now markers live in a stacked label area above
// the chart grid. ``tier 0`` is the topmost label row (farthest from
// the chart); the corresponding vertical line is the longest. Higher
// tier numbers sit closer to the chart with shorter lines.
//
// Tier 0: Sunset / sunrise          (longest line, farthest label)
// Tier 1: Civil dark boundaries
// Tier 2: Nautical dark boundaries
// Tier 3: Astro dark boundaries
// Tier 4: Meridian transit          (own tier — not shared with
//                                    sunset/sunrise because a meridian
//                                    near sunset would overlap text)
// Tier 5: Now                       (closest to chart, shortest line)
const TWILIGHT_TIER_HEIGHT = 14;
const TWILIGHT_MAX_TIER = 5;
const MERIDIAN_TIER = 4;
const NOW_TIER = 5;
// Gap between the lowest tier's label baseline and the chart grid.
// Kept tight so the "now" line's label reads as pinned to the chart
// top instead of floating above it. Any more breathing room separates
// the eye from the freshest data.
const TWILIGHT_LABEL_BAR_GAP = 2;
const TWILIGHT_LABELS_TOTAL_HEIGHT =
  (TWILIGHT_MAX_TIER + 1) * TWILIGHT_TIER_HEIGHT + TWILIGHT_LABEL_BAR_GAP;

interface TwilightMarker {
  key: string;
  label: string; // short label for tooltip + legend
  utc: string | null;
  side: "left" | "right";
  tier: number; // 0 (astro, topmost) .. 2 (civil, closest to chart)
}

export default function SkyPositionGraph({
  track,
  tz,
  // Default bumped 260 → 324 → 338 → 352 → 346 over successive tier
  // additions + a final compaction of the label-strip-to-chart gap.
  // The 86 px label strip above the chart grid reserves six tiers:
  // astro / nautical / civil dark + sunset / sunrise, then meridian
  // on its own row so a meridian-near-sunset doesn't collide with
  // the sunset label, then now closest to the chart. Chart data area
  // stays its historic 222 px tall.
  height = 346,
}: Props) {
  const theme = useTheme();
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const [width, setWidth] = useState(600);
  const [hover, setHover] = useState<HoverInfo | null>(null);
  // Bare counter used only to trigger a re-render when the minute
  // rolls over — lets the "now" marker advance on its own instead of
  // getting frozen at whatever wall-clock time the panel was first
  // opened at. The actual time displayed still comes from
  // ``new Date()`` inside the render.
  const [, setMinuteTick] = useState(0);

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

  useEffect(() => {
    // Wake up at the next minute boundary, then tick every 60s so the
    // minute stays flush with real time (a fixed 60s setInterval would
    // drift relative to the wall clock). HH:MM precision is enough —
    // no need for per-second updates, which would cause needless SVG
    // churn on every tooltip movement.
    let intervalId: ReturnType<typeof setInterval> | undefined;
    const msUntilNextMinute = 60_000 - (Date.now() % 60_000);
    const timeoutId = setTimeout(() => {
      setMinuteTick((t) => t + 1);
      intervalId = setInterval(() => setMinuteTick((t) => t + 1), 60_000);
    }, msUntilNextMinute);
    return () => {
      clearTimeout(timeoutId);
      if (intervalId !== undefined) clearInterval(intervalId);
    };
  }, []);

  const tw = twilightFill(theme.palette.mode);
  const blockedFill = blockedSkyFill(theme.palette.mode);

  const layout = useMemo(() => {
    const MARGIN = {
      top: 10 + TWILIGHT_LABELS_TOTAL_HEIGHT,
      right: 44,
      bottom: 28,
      left: 44,
    };
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

  // Twilight markers — the six boundaries that separate the twilight
  // bands already shaded behind the chart. Tier 0 (astro) is drawn
  // with the longest line + topmost label; tier 2 (civil) is closest
  // to the chart. Side ("left" / "right") only governs label anchor
  // position relative to the line.
  const twilightMarkers = useMemo<TwilightMarker[]>(() => {
    const tw = track.twilight;
    return [
      { key: "sunset", label: "Sunset", utc: tw.sunset_utc, side: "left", tier: 0 },
      { key: "civil_end", label: "Civil dark", utc: tw.civil_end_utc, side: "left", tier: 1 },
      { key: "nautical_end", label: "Nautical dark", utc: tw.nautical_end_utc, side: "left", tier: 2 },
      { key: "astro_start", label: "Astro dark", utc: tw.astro_start_utc, side: "left", tier: 3 },
      { key: "astro_end", label: "Astro dark", utc: tw.astro_end_utc, side: "right", tier: 3 },
      { key: "nautical_start", label: "Nautical dark", utc: tw.nautical_start_utc, side: "right", tier: 2 },
      { key: "civil_start", label: "Civil dark", utc: tw.civil_start_utc, side: "right", tier: 1 },
      { key: "sunrise", label: "Sunrise", utc: tw.sunrise_utc, side: "right", tier: 0 },
    ];
  }, [track.twilight]);

  function onMouseMove(e: React.MouseEvent<SVGSVGElement>) {
    const svg = e.currentTarget;
    const rect = svg.getBoundingClientRect();
    const mx = e.clientX - rect.left;

    // Magnetic snap — meridian + each twilight boundary. Pick the
    // landmark closest to the cursor within SNAP_PX; gives the user
    // a "positive stop" at each darkness-band edge instead of having
    // to land on it by pixel-perfect mouse movement.
    let snapTime: Date | null = null;
    let snapX = mx;
    let snapLabel: string | null = null;
    let bestDist = SNAP_PX + 0.5;

    function tryCandidate(iso: string | null, label: string) {
      if (!iso) return;
      const t = new Date(iso);
      const cx = layout.x(t);
      if (cx < layout.MARGIN.left || cx > width - layout.MARGIN.right) return;
      const d = Math.abs(mx - cx);
      if (d < bestDist) {
        snapTime = t;
        snapX = cx;
        snapLabel = label;
        bestDist = d;
      }
    }

    tryCandidate(track.transit_time_utc, "meridian");
    // Snap to the "now" line when the cursor is near it — completes
    // the set of landmarks the user can land on precisely.
    const now = new Date();
    const tmin = layout.times[0];
    const tmax = layout.times[layout.times.length - 1];
    if (tmin && tmax && now >= tmin && now <= tmax) {
      tryCandidate(now.toISOString(), "now");
    }
    for (const m of twilightMarkers) {
      tryCandidate(m.utc, m.label.toLowerCase());
    }

    const t = snapTime ?? layout.x.invert(mx);
    const idx = d3.bisector((d: Date) => d).left(layout.times, t);
    const clamped = Math.max(0, Math.min(layout.times.length - 1, idx));
    // When snapped to the meridian, prefer the analytical transit
    // altitude (sub-minute precise) over the bisected 5-min sample.
    // For twilight snaps we don't have a corresponding analytical
    // altitude, so fall back to the nearest sample — error is <5 min.
    const objAlt =
      snapLabel === "meridian"
        ? track.peak_altitude_deg
        : track.object_altitude_deg[clamped];
    const horizon = track.horizon_altitude_at_object_az[clamped];
    const localTime = (snapTime ?? layout.times[clamped]).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
      timeZone: tz,
    });
    setHover({
      xPx: snapTime ? snapX : layout.x(layout.times[clamped]),
      timeLocal: localTime,
      objAlt,
      objAz: track.object_azimuth_deg[clamped],
      moonAlt: track.moon_altitude_deg[clamped],
      moonSep: track.moon_separation_deg[clamped],
      aboveHorizon: objAlt > horizon,
      snapLabel,
    });
  }

  // Every hour, not every-other-hour. ``d3.timeHour.range`` returns
  // every hour boundary inside ``[tmin, tmax)`` — one tick per
  // clock-aligned hour across the chart's visible window.
  const [tmin, tmax] = layout.x.domain() as [Date, Date];
  const ticks = d3.timeHour.range(tmin, tmax);

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

        {/* Y-axis title — rotated so it sits flush against the tick labels. */}
        <text
          x={-((height - layout.MARGIN.top - layout.MARGIN.bottom) / 2 + layout.MARGIN.top)}
          y={layout.MARGIN.left - 34}
          textAnchor="middle"
          transform="rotate(-90)"
          fontSize={11}
          fill={theme.palette.text.secondary}
        >
          Altitude (°)
        </text>

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
              {t.toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit",
                hour12: false,
                timeZone: tz,
              })}
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

        {/* Twilight-boundary markers — tiered dashed verticals with
            labels, mirroring the weather app's Darkness-bar
            convention. Astro (tier 0) is topmost + longest line;
            civil (tier 2) is closest to the chart. */}
        {twilightMarkers.map((m) => {
          if (!m.utc) return null;
          const mx = layout.x(new Date(m.utc));
          if (mx < layout.MARGIN.left || mx > width - layout.MARGIN.right) {
            return null;
          }
          // Line top sits at this tier's row in the label area.
          const labelsBarTop = layout.MARGIN.top - TWILIGHT_LABELS_TOTAL_HEIGHT;
          const lineTop = labelsBarTop + m.tier * TWILIGHT_TIER_HEIGHT;
          // Label baseline: 3 px above the tier's lower edge.
          const labelY = labelsBarTop + (m.tier + 1) * TWILIGHT_TIER_HEIGHT - 3;
          const labelX = m.side === "left" ? mx + 4 : mx - 4;
          const textAnchor = m.side === "left" ? "start" : "end";
          const timeLocal = new Date(m.utc).toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
            hour12: false,
            timeZone: tz,
          });
          return (
            <g key={m.key}>
              <line
                x1={mx}
                x2={mx}
                y1={lineTop}
                y2={height - layout.MARGIN.bottom}
                stroke={theme.palette.text.secondary}
                strokeWidth={1}
                strokeDasharray="2,3"
                opacity={0.5}
              />
              <text
                x={labelX}
                y={labelY}
                textAnchor={textAnchor}
                fontSize={10}
                fontFamily="inherit"
              >
                {m.side === "left" && <tspan fill={theme.palette.text.disabled}>{"◂"} </tspan>}
                <tspan fill={theme.palette.text.secondary}>{m.label} </tspan>
                <tspan fill={theme.palette.text.primary}>{timeLocal}</tspan>
                {m.side === "right" && <tspan fill={theme.palette.text.disabled}> {"▸"}</tspan>}
              </text>
            </g>
          );
        })}

        {/* Meridian crossing — vertical dashed line with label on
            its own tier (one above "now", below sunset/sunrise).
            Earlier shared tier 3 with sunset/sunrise, but a meridian
            close to sunset made the labels overlap. Drawn only when
            transit falls inside the display window. */}
        {track.transit_time_utc &&
          (() => {
            const tx = layout.x(new Date(track.transit_time_utc));
            if (tx < layout.MARGIN.left || tx > width - layout.MARGIN.right) return null;
            const labelsBarTop = layout.MARGIN.top - TWILIGHT_LABELS_TOTAL_HEIGHT;
            const lineTop = labelsBarTop + MERIDIAN_TIER * TWILIGHT_TIER_HEIGHT;
            const labelY =
              labelsBarTop + (MERIDIAN_TIER + 1) * TWILIGHT_TIER_HEIGHT - 3;
            const timeLocal = new Date(track.transit_time_utc).toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
              hour12: false,
              timeZone: tz,
            });
            return (
              <g>
                <line
                  x1={tx}
                  x2={tx}
                  y1={lineTop}
                  y2={height - layout.MARGIN.bottom}
                  stroke={COLOR_OBJECT}
                  strokeWidth={1}
                  strokeDasharray="3,3"
                  opacity={0.65}
                />
                <text
                  x={tx}
                  y={labelY}
                  textAnchor="middle"
                  fontSize={10}
                  fontFamily="inherit"
                >
                  <tspan fill={COLOR_OBJECT}>meridian </tspan>
                  <tspan fill={theme.palette.text.primary}>{timeLocal}</tspan>
                </text>
              </g>
            );
          })()}

        {/* "Now" indicator — vertical line + filled-triangle "stop" at
            the top + time label on tier 4 (closest to the chart). Drawn
            only when the current wall-clock time falls inside the
            chart's time window. The triangle acts as a positive visual
            anchor so the line's top is unambiguous even at low
            opacities. The line uses a teal colour distinct from object
            (blue) and moon (orange) so it reads as "this is right now"
            at a glance. Wrapped in an IIFE so the intermediate ``now``
            variable doesn't leak into the outer scope. */}
        {(() => {
          const now = new Date();
          const tmin = layout.times[0];
          const tmax = layout.times[layout.times.length - 1];
          if (!tmin || !tmax || now < tmin || now > tmax) return null;
          const nx = layout.x(now);
          if (nx < layout.MARGIN.left || nx > width - layout.MARGIN.right) {
            return null;
          }
          const labelsBarTop = layout.MARGIN.top - TWILIGHT_LABELS_TOTAL_HEIGHT;
          const labelY =
            labelsBarTop + (NOW_TIER + 1) * TWILIGHT_TIER_HEIGHT - 3;
          const nowLocal = now.toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
            hour12: false,
            timeZone: tz,
          });
          // Line runs only inside the chart data area — from the top
          // grid edge (90° line) down to the bottom axis. Triangle
          // sits flush at the top of the chart with its flat base on
          // the 90° line and its apex pointing down into the chart,
          // so the "positive stop" reads as an arrowhead capping the
          // top of the line. Triangle overlaps the line's top
          // pixels; drawn after the line so the filled triangle
          // covers cleanly.
          const triSize = 5;
          const chartTop = layout.MARGIN.top;
          return (
            <g>
              <line
                x1={nx}
                x2={nx}
                y1={chartTop}
                y2={height - layout.MARGIN.bottom}
                stroke={COLOR_NOW}
                strokeWidth={1.25}
              />
              <polygon
                points={`${nx - triSize},${chartTop} ${nx + triSize},${chartTop} ${nx},${chartTop + triSize * 1.3}`}
                fill={COLOR_NOW}
              />
              <text
                x={nx}
                y={labelY}
                textAnchor="middle"
                fontSize={10}
                fontWeight={600}
                fontFamily="inherit"
                fill={COLOR_NOW}
              >
                now {nowLocal}
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
            {hover.snapLabel && (
              <Box
                component="span"
                sx={{ ml: 0.75, color: "text.secondary", fontWeight: 400 }}
              >
                ({hover.snapLabel})
              </Box>
            )}
          </Typography>
          <div>
            Object: {hover.objAlt.toFixed(1)}° alt, {hover.objAz.toFixed(0)}° az
          </div>
          <div>
            Moon: {hover.moonAlt.toFixed(1)}° alt, {hover.moonSep.toFixed(0)}° sep, {track.moon_phase_pct.toFixed(0)}% illum
          </div>
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
        sx={{ mt: 1, pr: `${layout.MARGIN.right}px` }}
        alignItems="center"
        justifyContent="flex-end"
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
            Horizon
          </Typography>
        </Stack>
      </Stack>
    </Box>
  );
}
