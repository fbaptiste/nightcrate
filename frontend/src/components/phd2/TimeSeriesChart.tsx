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
import { useEffect, useId, useMemo, useRef, useState } from "react";
import * as d3 from "d3";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Stack from "@mui/material/Stack";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
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
  /** Fires whenever the visible X domain changes (pan/zoom/reset).
   *  ``null`` == full section visible. Used by the Viewport Summary
   *  panel on the page so metrics can recompute over just the
   *  in-view samples. */
  onViewportChange?: (domain: [number, number] | null) => void;
  /** Closed-interval settle windows to shade on the chart. Passed from
   *  the page so the shading stays in lockstep with the metrics filter. */
  settleIntervals?: Array<[number, number]>;
  /** When false, suppress shading even if ``settleIntervals`` is
   *  non-empty. Driven by the page-level "Include settle" toggle — when
   *  the user has opted to include settle frames in stats, greying them
   *  out would be inconsistent. Default ``true``. */
  showSettleShading?: boolean;
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
  /** Every event (dither or otherwise) whose X is within
   *  ``EVENT_SNAP_PX`` of the cursor. When non-empty the crosshair
   *  paints solid blue and the tooltip renders an Events section. */
  nearbyEvents: LogEvent[];
}

/** Pixel radius within which the cursor snaps to any event marker
 *  (dither triangle or non-dither dot). */
const EVENT_SNAP_PX = 8;

export default function TimeSeriesChart({
  samples,
  events = [],
  startIso,
  height = 440,
  onViewportChange,
  settleIntervals = [],
  showSettleShading = true,
}: Props) {
  const theme = useTheme();
  const isDark = theme.palette.mode === "dark";
  // useId() guarantees unique clipPath ids across multiple instances
  // of the chart (e.g. if a future UI paints two sections side-by-side).
  const uid = useId().replace(/:/g, "");
  const clipMain = `phd2-clip-main-${uid}`;
  const clipSnr = `phd2-clip-snr-${uid}`;
  const clipMass = `phd2-clip-mass-${uid}`;
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);
  // Reference to the active d3.zoom behavior attached to the SVG. The
  // scrollbar drag and the Reset-zoom button both program the SAME
  // behavior instance so d3's internal transform stays coherent with
  // subsequent wheel / drag interactions.
  const zoomBehaviorRef = useRef<d3.ZoomBehavior<SVGSVGElement, unknown> | null>(null);
  const [width, setWidth] = useState(640);
  const [zoomX, setZoomX] = useState<[number, number] | null>(null);
  const [hover, setHover] = useState<HoverInfo | null>(null);
  // Per-series visibility, toggled by clicking a legend chip. All
  // series default to shown; individual series can be hidden without
  // affecting the axes so zoom/pan state stays coherent.
  const [visibility, setVisibility] = useState({
    ra: true,
    dec: true,
    raPulse: true,
    decPulse: true,
    dither: true,
  });
  // User-adjustable Y ranges for the two main-panel axes. "auto" =
  // auto-fit the domain to the visible data; a positive-number string
  // clamps to ±value. The sentinel is a non-empty string so MUI
  // ``Select`` with a floating label renders "Auto" as the selected
  // value instead of flashing the empty-value label overlay.
  const [guideAxisMax, setGuideAxisMax] = useState<string>("auto");
  const [pulseAxisMax, setPulseAxisMax] = useState<string>("auto");
  // Sub-panel y-axis scale mode. "fixed" = derive domain from the full
  // section (current default behaviour: scale stable while zooming).
  // "auto" = derive domain from the visible samples only, matching the
  // guide-axis Auto behaviour — the axis tightens when panning into a
  // calmer stretch.
  const [snrScaleMode, setSnrScaleMode] = useState<"auto" | "fixed">("fixed");
  const [massScaleMode, setMassScaleMode] = useState<"auto" | "fixed">("fixed");
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

  // Data domain extrema (used for the scrollbar + zoom base scale).
  const [tmin, tmax] = useMemo(() => {
    if (samples.length === 0) return [0, 1];
    return [samples[0].time_seconds, samples[samples.length - 1].time_seconds];
  }, [samples]);

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

    // Auto / manual left-axis range. Auto re-fits per-zoom using only
    // the visible samples so panning into a quieter region zooms in
    // on small deflections. Manual (user-picked ±N px) clamps to that
    // fixed range; data outside the range clips at the panel edges.
    const visibleSamples = zoomX
      ? samples.filter(
          (s) => s.time_seconds >= zoomX[0] && s.time_seconds <= zoomX[1],
        )
      : samples;
    const distVals = visibleSamples.flatMap((s) =>
      [s.ra_raw_px, s.dec_raw_px].filter((v): v is number => v !== null),
    );
    const autoMaxAbs = distVals.length
      ? Math.max(1.0, d3.max(distVals.map((v) => Math.abs(v))) ?? 1.0)
      : 1.0;
    const parsedGuideMax = parseFloat(guideAxisMax);
    const maxAbs =
      Number.isFinite(parsedGuideMax) && parsedGuideMax > 0
        ? parsedGuideMax
        : autoMaxAbs * 1.1;

    // Pulse axis range — scoped to visible samples so panning / zooming
    // always reflects the in-view data. Auto uses the visible max + 10 %
    // headroom (mirroring the guide-axis auto behaviour) with a 50 ms
    // floor so a quiet all-zero region still renders a usable scale.
    const visibleDurations = visibleSamples.flatMap((s) =>
      [s.ra_duration_ms ?? 0, s.dec_duration_ms ?? 0].filter((v) => v > 0),
    );
    const visibleDurMax = visibleDurations.length
      ? (d3.max(visibleDurations) ?? 0)
      : 0;
    const autoDurMax = Math.max(50, visibleDurMax * 1.1);
    const parsedPulseMax = parseFloat(pulseAxisMax);
    const durMax =
      Number.isFinite(parsedPulseMax) && parsedPulseMax > 0
        ? parsedPulseMax
        : autoDurMax;

    // SNR + mass are tight-fit around the observed extent so subtle
    // variation is actually readable. Earlier behaviour (``[0, max*1.1]``)
    // squashed the trace to a flat line when the minimum was well above
    // zero (typical — SNR stays in the 15–40 band for a healthy star).
    // Scale mode picks the sample source: "fixed" uses the full section
    // (axis stable across pan/zoom), "auto" uses only visible samples
    // (axis tightens when panning to a quieter stretch).
    const snrSamples = snrScaleMode === "auto" ? visibleSamples : samples;
    const massSamples = massScaleMode === "auto" ? visibleSamples : samples;
    const snrs = snrSamples.map((s) => s.snr).filter((v): v is number => v !== null);
    const [snrLo, snrHi] = snrDomainWithPadding(snrs, 2);
    const masses = massSamples
      .map((s) => s.star_mass)
      .filter((v): v is number => v !== null);
    const [massLo, massHi] = snrDomainWithPadding(masses, 100);

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
        .domain([snrLo, snrHi])
        .range([snrY0 + snrH, snrY0]),
      yMassScale: d3
        .scaleLinear()
        .domain([massLo, massHi])
        .range([massY0 + massH, massY0]),
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    samples,
    width,
    height,
    zoomX,
    guideAxisMax,
    pulseAxisMax,
    snrScaleMode,
    massScaleMode,
    innerW,
    mainH,
    snrH,
    massH,
  ]);

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
    zoomBehaviorRef.current = zoom;
    return () => {
      d3.select(svg).on(".zoom", null);
      zoomBehaviorRef.current = null;
    };
  }, [samples, width, height, innerW]);

  // Notify the page whenever the visible X domain changes — drives
  // the Viewport Summary panel's metrics recompute.
  useEffect(() => {
    onViewportChange?.(zoomX);
  }, [zoomX, onViewportChange]);

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
    if (samples.length < 2) return { ra: [], dec: [], barW: 3 };
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
    // ``clippedAbove`` / ``clippedBelow`` flag bars whose raw height
    // exceeded the panel half-extent — a subtle triangle caret at the
    // panel edge signals the clip so big outliers aren't silently lost.
    const ra: Array<{
      x: number;
      y: number;
      h: number;
      clippedAbove: boolean;
      clippedBelow: boolean;
      cx: number;
    }> = [];
    const dec: Array<{
      x: number;
      y: number;
      h: number;
      clippedAbove: boolean;
      clippedBelow: boolean;
      cx: number;
    }> = [];
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
          clippedAbove: sign > 0 && rawH > panelHalf,
          clippedBelow: sign < 0 && rawH > panelHalf,
          cx,
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
          clippedAbove: sign > 0 && rawH > panelHalf,
          clippedBelow: sign < 0 && rawH > panelHalf,
          cx,
        });
      }
    }
    return { ra, dec, barW };
  }, [samples, xScale, yPulseScale, innerW, zoomX, mainH]);

  // Group non-dither events by time_seconds so a single dot represents
  // every event at a given instant. Dither keeps its own triangle
  // marker — rendering both would overlap at the same x. Events with
  // no time anchor are dropped (they precede the first sample).
  const eventDotGroups = useMemo((): Array<[number, LogEvent[]]> => {
    const groups = new Map<number, LogEvent[]>();
    for (const e of events) {
      if (e.kind === "dither") continue;
      if (e.time_seconds == null) continue;
      const existing = groups.get(e.time_seconds);
      if (existing) existing.push(e);
      else groups.set(e.time_seconds, [e]);
    }
    return Array.from(groups.entries()).sort((a, b) => a[0] - b[0]);
  }, [events]);

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

    // Collect every event within EVENT_SNAP_PX of the cursor — dither
    // triangles and non-dither dots flow into a single tooltip block.
    // The nearest event's X doubles as a soft snap so the crosshair
    // locks onto the event row.
    const nearbyEvents: LogEvent[] = [];
    let snapTime: number | null = null;
    let bestDist = EVENT_SNAP_PX + 0.5;
    for (const ev of events) {
      if (ev.time_seconds == null) continue;
      // Dither legend toggle hides both the triangle AND its tooltip
      // entry; other event kinds can't be hidden today.
      if (ev.kind === "dither" && !visibility.dither) continue;
      const ex = xScale(ev.time_seconds);
      if (ex < MARGIN.left || ex > MARGIN.left + innerW) continue;
      const d = Math.abs(mx - ex);
      if (d <= EVENT_SNAP_PX) {
        nearbyEvents.push(ev);
        if (d < bestDist) {
          bestDist = d;
          snapTime = ev.time_seconds;
        }
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
      nearbyEvents,
    });
  }

  function handleReset() {
    setZoomX(null);
    if (svgRef.current && zoomBehaviorRef.current) {
      zoomBehaviorRef.current.transform(
        d3.select(svgRef.current),
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

  // Guide axis (left y, px) options: auto + a tight sub-pixel tier
  // (0.2 / 0.3 / 0.4 / 0.5) for jitter inspection, then integer ranges
  // from ±1 to ±10 px for broader deflection views.
  const guideAxisOptions: Array<{ value: string; label: string }> = [
    { value: "auto", label: "Auto" },
    { value: "0.2", label: "±0.2 px" },
    { value: "0.3", label: "±0.3 px" },
    { value: "0.4", label: "±0.4 px" },
    { value: "0.5", label: "±0.5 px" },
    ...Array.from({ length: 10 }, (_, i) => ({
      value: String(i + 1),
      label: `±${i + 1} px`,
    })),
  ];

  // Pulse axis (right y, ms) options. Based on the sample ASIAIR log:
  // p75 ≈ 115 ms, p95 ≈ 200 ms, p99 ≈ 500 ms, outliers up to ~8 s on
  // settle recovery. PHD2's default MaxRADuration / MaxDecDuration is
  // 1000 ms — the most common clamp. Range choices cover the tight
  // (jitter inspection) through extreme (settle spikes) cases.
  const pulseAxisOptions: Array<{ value: string; label: string }> = [
    { value: "auto", label: "Auto" },
    { value: "100", label: "±100 ms" },
    { value: "200", label: "±200 ms" },
    { value: "300", label: "±300 ms" },
    { value: "500", label: "±500 ms" },
    { value: "1000", label: "±1000 ms" },
    { value: "2000", label: "±2000 ms" },
    { value: "5000", label: "±5000 ms" },
  ];

  // Scrollbar thumb — represents visible X range within the full data
  // range. Left + width are computed from zoomX vs (tmin, tmax).
  const zoomLeft = zoomX ? zoomX[0] : tmin;
  const zoomRight = zoomX ? zoomX[1] : tmax;
  const spanFull = Math.max(1e-6, tmax - tmin);
  const thumbLeftFrac = (zoomLeft - tmin) / spanFull;
  const thumbWidthFrac = (zoomRight - zoomLeft) / spanFull;
  const isZoomed = zoomX !== null;

  // Mouse-drag handler for the scrollbar thumb — uses d3.zoom's
  // translateTo to recenter on the new x, which keeps d3's internal
  // transform state in sync with our React zoomX state.
  const scrollbarDragRef = useRef<{
    startMouseX: number;
    startLeft: number;
    trackWidth: number;
  } | null>(null);

  const onScrollbarMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!svgRef.current || !zoomBehaviorRef.current || !isZoomed) return;
    const trackEl = (e.currentTarget.parentElement as HTMLElement) ?? null;
    if (!trackEl) return;
    scrollbarDragRef.current = {
      startMouseX: e.clientX,
      startLeft: thumbLeftFrac,
      trackWidth: trackEl.clientWidth,
    };
    e.preventDefault();
    const onMove = (ev: MouseEvent) => {
      const drag = scrollbarDragRef.current;
      const svg = svgRef.current;
      const behavior = zoomBehaviorRef.current;
      if (!drag || !svg || !behavior) return;
      const deltaFrac = (ev.clientX - drag.startMouseX) / Math.max(1, drag.trackWidth);
      const newLeftFrac = Math.max(
        0,
        Math.min(1 - thumbWidthFrac, drag.startLeft + deltaFrac),
      );
      // translateTo takes coordinates in the BASE (untransformed) pixel
      // space of the zoom's extent — which is pixel-space here — so
      // convert the new center time back to its base pixel x.
      const newCenterFrac = newLeftFrac + thumbWidthFrac / 2;
      const newCenterPx = MARGIN.left + newCenterFrac * innerW;
      behavior.translateTo(d3.select(svg), newCenterPx, 0);
    };
    const onUp = () => {
      scrollbarDragRef.current = null;
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
    };
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  };

  // Horizontal position of the tooltip within its reservation area.
  // Centered on the cursor; clamped so the tooltip stays inside the
  // chart's horizontal span.
  const TOOLTIP_W = 250;
  // Reservation height must fit the worst-case tooltip (frame row +
  // 3-row RA/Dec grid + SNR/mass row + optional Dither row). Sized for
  // the dither-snap case so the tooltip never overflows downward onto
  // the SVG and covers the dither triangle at the top margin.
  const TOOLTIP_H = 140;
  const tooltipLeft = hover
    ? Math.max(
        MARGIN.left,
        Math.min(MARGIN.left + innerW - TOOLTIP_W, hover.xPx - TOOLTIP_W / 2),
      )
    : 0;

  return (
    <Stack direction="row" alignItems="flex-start" spacing={1} sx={{ width: "100%" }}>
      {/* Axis-range column on the left, aligned with the top of the
          chart (past the toolbar + tooltip area + panel-label row).
          Two stacked Selects — guide axis (left y, px) + pulse axis
          (right y, ms). Both default to Auto, which fits the domain
          to the visible samples. */}
      <Stack
        direction="column"
        spacing={2}
        sx={{ flexShrink: 0, width: 132, pt: `${TOOLTIP_H + 60}px` }}
      >
        <FormControl size="small" fullWidth>
          <InputLabel id="phd2-guide-axis-label">Guide axis (px)</InputLabel>
          <Select
            labelId="phd2-guide-axis-label"
            label="Guide axis (px)"
            value={guideAxisMax}
            onChange={(e) => setGuideAxisMax(e.target.value)}
            sx={{ fontSize: 12 }}
          >
            {guideAxisOptions.map((o) => (
              <MenuItem key={o.value} value={o.value}>
                {o.label}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        <FormControl size="small" fullWidth>
          <InputLabel id="phd2-pulse-axis-label">Pulse axis (ms)</InputLabel>
          <Select
            labelId="phd2-pulse-axis-label"
            label="Pulse axis (ms)"
            value={pulseAxisMax}
            onChange={(e) => setPulseAxisMax(e.target.value)}
            sx={{ fontSize: 12 }}
          >
            {pulseAxisOptions.map((o) => (
              <MenuItem key={o.value} value={o.value}>
                {o.label}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        <SubPanelScaleToggle
          label="SNR scale"
          value={snrScaleMode}
          onChange={setSnrScaleMode}
        />
        <SubPanelScaleToggle
          label="Mass scale"
          value={massScaleMode}
          onChange={setMassScaleMode}
        />
      </Stack>

      <Box ref={wrapperRef} sx={{ flex: 1, minWidth: 0, position: "relative" }}>
        {/* Toolbar — legend toggles + hint + reset */}
        <Stack direction="row" spacing={1} alignItems="center" sx={{ pb: 0.5 }} flexWrap="wrap" useFlexGap>
        <LegendToggle
          label="RA"
          color={COLOR_RA}
          shape="line"
          active={visibility.ra}
          onToggle={() => setVisibility((v) => ({ ...v, ra: !v.ra }))}
        />
        <LegendToggle
          label="Dec"
          color={COLOR_DEC}
          shape="line"
          active={visibility.dec}
          onToggle={() => setVisibility((v) => ({ ...v, dec: !v.dec }))}
        />
        <LegendToggle
          label="RA pulse"
          color={COLOR_RA}
          shape="bar"
          active={visibility.raPulse}
          onToggle={() => setVisibility((v) => ({ ...v, raPulse: !v.raPulse }))}
        />
        <LegendToggle
          label="Dec pulse"
          color={COLOR_DEC}
          shape="bar"
          active={visibility.decPulse}
          onToggle={() => setVisibility((v) => ({ ...v, decPulse: !v.decPulse }))}
        />
        {events.some((e) => e.kind === "dither") && (
          <LegendToggle
            label="Dither"
            color={COLOR_RA}
            shape="triangle"
            active={visibility.dither}
            onToggle={() => setVisibility((v) => ({ ...v, dither: !v.dither }))}
          />
        )}
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ fontStyle: "italic", ml: 0.5 }}
        >
          (click to toggle)
        </Typography>
        <Box sx={{ flex: 1 }} />
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ fontStyle: "italic" }}
        >
          Scroll to zoom · drag to pan
        </Typography>
        <Button
          size="small"
          startIcon={<RestartAltIcon />}
          onClick={handleReset}
          disabled={zoomX === null}
        >
          Reset X zoom
        </Button>
      </Stack>

      {/* Tooltip reservation area — always present so the chart layout
          doesn't jump when the hover tooltip appears / disappears. */}
      <Box sx={{ position: "relative", height: TOOLTIP_H }}>
        {hover && (
          <Box
            sx={{
              position: "absolute",
              top: 0,
              left: tooltipLeft,
              width: TOOLTIP_W,
              p: 1,
              bgcolor: "background.paper",
              border: "1px solid",
              borderColor: "divider",
              borderRadius: 1,
              fontSize: 12,
              pointerEvents: "none",
              boxShadow: 1,
            }}
          >
            <Typography variant="caption" sx={{ display: "block", fontWeight: 600 }}>
              Frame {hover.frame ?? ""} ·{" "}
              {startIso ? `${formatWallClock(startIso, hover.time)} · ` : ""}
              {hover.time.toFixed(2)} s
            </Typography>
            {/* RA / Dec grid — error + pulse rows, blank cells for null. */}
            <Box
              sx={{
                display: "grid",
                gridTemplateColumns: "auto 1fr 1fr auto",
                columnGap: 1,
                rowGap: 0.25,
                alignItems: "center",
                fontSize: 12,
                mt: 0.25,
              }}
            >
              <span />
              <Box sx={{ color: COLOR_RA, fontWeight: 600, textAlign: "right" }}>RA</Box>
              <Box sx={{ color: COLOR_DEC, fontWeight: 600, textAlign: "right" }}>Dec</Box>
              <span />

              <Box sx={{ opacity: 0.7 }}>error:</Box>
              <Box sx={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                {formatPxOrBlank(hover.raRaw)}
              </Box>
              <Box sx={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                {formatPxOrBlank(hover.decRaw)}
              </Box>
              <Box sx={{ opacity: 0.7 }}>px</Box>

              <Box sx={{ opacity: 0.7 }}>pulse:</Box>
              <Box sx={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                {formatPulseOrBlank(hover.raDuration, hover.raDirection)}
              </Box>
              <Box sx={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                {formatPulseOrBlank(hover.decDuration, hover.decDirection)}
              </Box>
              <Box sx={{ opacity: 0.7 }}>ms</Box>
            </Box>
            <Typography variant="caption" sx={{ display: "block", mt: 0.25 }}>
              SNR: {hover.snr != null ? hover.snr.toFixed(1) : ""} · mass:{" "}
              {hover.starMass != null ? hover.starMass : ""}
            </Typography>
            {hover.nearbyEvents.length > 0 && (
              <Box
                sx={{
                  mt: 0.5,
                  pt: 0.5,
                  borderTop: 1,
                  borderColor: "divider",
                }}
              >
                {/* Dither always pinned to the top; other events keep
                    their original order. */}
                {[...hover.nearbyEvents]
                  .sort((a, b) => {
                    const aIsDither = a.kind === "dither" ? 0 : 1;
                    const bIsDither = b.kind === "dither" ? 0 : 1;
                    return aIsDither - bIsDither;
                  })
                  .map((ev, i) => (
                    <Typography
                      key={`${ev.kind}-${i}`}
                      variant="caption"
                      sx={{
                        display: "block",
                        color: ev.kind === "dither" ? COLOR_RA : "text.primary",
                        fontWeight: ev.kind === "dither" ? 600 : 500,
                      }}
                    >
                      {formatEventSummary(ev)}
                    </Typography>
                  ))}
              </Box>
            )}
          </Box>
        )}
      </Box>

      {/* Panel titles are rendered INSIDE the SVG as rotated axis
          labels — see the text blocks positioned via
          ``rotate(-90)`` alongside each y-axis, below. */}

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
        {/* Per-panel clip rects — every series + bar renders inside its
            panel only, so traces can never paint over the left / right
            axis tick labels or bleed into the SNR / mass panels. */}
        <defs>
          <clipPath id={clipMain}>
            <rect x={MARGIN.left} y={mainY0} width={innerW} height={mainH} />
          </clipPath>
          <clipPath id={clipSnr}>
            <rect x={MARGIN.left} y={snrY0} width={innerW} height={snrH} />
          </clipPath>
          <clipPath id={clipMass}>
            <rect x={MARGIN.left} y={massY0} width={innerW} height={massH} />
          </clipPath>
        </defs>

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

        {/* Settle-window shading — paints FIRST so pulse bars + traces
            render on top. Signals "these samples are excluded from the
            guide-quality stats per PHD2 / PHDLogViewer convention".
            Same translucent grey across all three panels. */}
        {showSettleShading && settleIntervals.length > 0 && (
          <>
            <g clipPath={`url(#${clipMain})`}>
              {settleIntervals.map(([t0, t1], i) => (
                <rect
                  key={`settle-main-${i}`}
                  x={xScale(t0)}
                  y={mainY0}
                  width={Math.max(1, xScale(t1) - xScale(t0))}
                  height={mainH}
                  fill={isDark ? "rgba(255,255,255,0.10)" : "rgba(0,0,0,0.08)"}
                />
              ))}
            </g>
            <g clipPath={`url(#${clipSnr})`}>
              {settleIntervals.map(([t0, t1], i) => (
                <rect
                  key={`settle-snr-${i}`}
                  x={xScale(t0)}
                  y={snrY0}
                  width={Math.max(1, xScale(t1) - xScale(t0))}
                  height={snrH}
                  fill={isDark ? "rgba(255,255,255,0.10)" : "rgba(0,0,0,0.08)"}
                />
              ))}
            </g>
            <g clipPath={`url(#${clipMass})`}>
              {settleIntervals.map(([t0, t1], i) => (
                <rect
                  key={`settle-mass-${i}`}
                  x={xScale(t0)}
                  y={massY0}
                  width={Math.max(1, xScale(t1) - xScale(t0))}
                  height={massH}
                  fill={isDark ? "rgba(255,255,255,0.10)" : "rgba(0,0,0,0.08)"}
                />
              ))}
            </g>
          </>
        )}

        {/* Everything inside the main panel's data area is clipped so
            pulse bars and traces can never paint over the tick labels
            that sit in MARGIN.left / MARGIN.right. */}
        <g clipPath={`url(#${clipMain})`}>
          {/* Pulse bars — drawn BEFORE traces so lines paint on top. */}
          {visibility.raPulse &&
            pulseBars.ra.map((b, i) => (
              <rect
                key={`rab-${i}`}
                x={b.x}
                y={b.y}
                width={pulseBars.barW}
                height={b.h}
                fill="none"
                stroke={COLOR_RA}
                strokeWidth={1}
                opacity={0.5}
              />
            ))}
          {visibility.decPulse &&
            pulseBars.dec.map((b, i) => (
              <rect
                key={`decb-${i}`}
                x={b.x}
                y={b.y}
                width={pulseBars.barW}
                height={b.h}
                fill="none"
                stroke={COLOR_DEC}
                strokeWidth={1}
                opacity={0.5}
              />
            ))}

          {/* Main traces */}
          {visibility.ra && (
            <path
              d={raLine(samples) ?? undefined}
              fill="none"
              stroke={COLOR_RA}
              strokeWidth={1.3}
            />
          )}
          {visibility.dec && (
            <path
              d={decLine(samples) ?? undefined}
              fill="none"
              stroke={COLOR_DEC}
              strokeWidth={1.3}
            />
          )}
        </g>

        {/* Clipped-pulse carets — rendered OUTSIDE the clip group so
            the indicator is visible right at the panel edge. A tiny
            outward-pointing triangle at the top (positive pulse clipped)
            or bottom (negative pulse clipped), sized to the bar so it
            reads like a continuation marker rather than extra noise. */}
        {visibility.raPulse &&
          pulseBars.ra.map((b, i) => {
            if (!b.clippedAbove && !b.clippedBelow) return null;
            // Skip carets whose sample sits outside the horizontal
            // plot area — bars are cropped to the panel via clipPath,
            // but carets are drawn outside the clip group so the
            // horizontal bounds check has to happen in JS.
            if (b.cx < MARGIN.left || b.cx > MARGIN.left + innerW) return null;
            return (
              <ClipCaret
                key={`rac-${i}`}
                cx={b.cx}
                edgeY={b.clippedAbove ? mainY0 : mainY0 + mainH}
                direction={b.clippedAbove ? "up" : "down"}
                color={COLOR_RA}
                barW={pulseBars.barW}
              />
            );
          })}
        {visibility.decPulse &&
          pulseBars.dec.map((b, i) => {
            if (!b.clippedAbove && !b.clippedBelow) return null;
            if (b.cx < MARGIN.left || b.cx > MARGIN.left + innerW) return null;
            return (
              <ClipCaret
                key={`decc-${i}`}
                cx={b.cx}
                edgeY={b.clippedAbove ? mainY0 : mainY0 + mainH}
                direction={b.clippedAbove ? "up" : "down"}
                color={COLOR_DEC}
                barW={pulseBars.barW}
              />
            );
          })}

        {/* Event dots — one small circle per non-dither event, grouped
            by time so simultaneous events share a single marker. Sits
            in the top margin just below the dither row. Hover detection
            happens at the SVG level via ``handleMouseMove`` so the dot
            merges into the main tooltip's Events block rather than
            using a per-element SVG <title>. */}
        {eventDotGroups.map(([t]) => {
          const cx = xScale(t);
          if (cx < MARGIN.left - 3 || cx > MARGIN.left + innerW + 3) return null;
          return (
            <circle
              key={`evt-${t}`}
              cx={cx}
              cy={MARGIN.top - 1}
              r={2.2}
              fill={axisColor}
              opacity={0.7}
              pointerEvents="none"
            />
          );
        })}

        {/* Dither markers — downward triangles in the top margin. Hover
            tooltip is handled centrally via handleMouseMove's event
            snap so dither + co-located events merge into one block. */}
        {visibility.dither &&
          events
            .filter((e) => e.kind === "dither" && e.time_seconds != null)
            .map((e) => {
              const cx = xScale(e.time_seconds as number);
              if (cx < MARGIN.left - 4 || cx > MARGIN.left + innerW + 4) return null;
              const topY = MARGIN.top - 9;
              const apexY = MARGIN.top - 1;
              return (
                <path
                  key={`dither-${e.time_seconds}`}
                  d={`M ${cx - 5},${topY} L ${cx + 5},${topY} L ${cx},${apexY} Z`}
                  fill={COLOR_RA}
                  stroke={COLOR_RA}
                  strokeWidth={0.5}
                  pointerEvents="none"
                />
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
        {/* Guide error + Pulses panel titles moved OUT of the SVG to
            the HTML banner above the chart — they were overlapping
            the plotted data at small Y ranges. */}

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
        {/* SNR panel */}
        <line
          x1={MARGIN.left}
          x2={MARGIN.left + innerW}
          y1={snrY0 + snrH}
          y2={snrY0 + snrH}
          stroke={axisColor}
        />
        <g clipPath={`url(#${clipSnr})`}>
          <path
            d={snrLine(samples) ?? undefined}
            fill="none"
            stroke={axisColor}
            strokeWidth={1}
            opacity={0.7}
          />
        </g>
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
        {/* Mass panel */}
        <line
          x1={MARGIN.left}
          x2={MARGIN.left + innerW}
          y1={massY0 + massH}
          y2={massY0 + massH}
          stroke={axisColor}
        />
        <g clipPath={`url(#${clipMass})`}>
          <path
            d={massLine(samples) ?? undefined}
            fill="none"
            stroke={axisColor}
            strokeWidth={1}
            opacity={0.5}
          />
        </g>
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

        {/* Rotated y-axis labels — one per axis, standing upright
            alongside the tick column. Pivot at (x, panelCentre);
            ``rotate(-90)`` makes the text read from bottom to top. */}
        <text
          transform={`translate(14, ${mainY0 + mainH / 2}) rotate(-90)`}
          fill={textColor}
          fontSize={11}
          fontWeight={600}
          textAnchor="middle"
        >
          Guide error (px)
        </text>
        <text
          transform={`translate(${width - 14}, ${mainY0 + mainH / 2}) rotate(-90)`}
          fill={textColor}
          fontSize={11}
          fontWeight={600}
          textAnchor="middle"
        >
          Pulses (ms)
        </text>
        <text
          transform={`translate(14, ${snrY0 + snrH / 2}) rotate(-90)`}
          fill={textColor}
          fillOpacity={0.85}
          fontSize={10}
          fontWeight={600}
          textAnchor="middle"
        >
          SNR
        </text>
        <text
          transform={`translate(14, ${massY0 + massH / 2}) rotate(-90)`}
          fill={textColor}
          fillOpacity={0.85}
          fontSize={10}
          fontWeight={600}
          textAnchor="middle"
        >
          Mass (ADU)
        </text>

        {/* Crosshair — paints solid blue when snapped to any event. */}
        {hover && (() => {
          const snapped = hover.nearbyEvents.length > 0;
          return (
            <g pointerEvents="none">
              <line
                x1={hover.xPx}
                x2={hover.xPx}
                y1={MARGIN.top}
                y2={massY0 + massH}
                stroke={snapped ? COLOR_RA : axisColor}
                strokeDasharray={snapped ? undefined : "3 3"}
                opacity={snapped ? 0.85 : 0.7}
              />
            </g>
          );
        })()}
      </svg>

      {/* Scrollbar row — thumb width reflects the visible fraction of
          the full data range. Drag to pan; the thumb is only
          interactive when the chart is zoomed in. */}
      <Box
        sx={{
          mt: 0.5,
          mb: 0.5,
          mx: `${MARGIN.left}px`,
          height: 10,
          position: "relative",
          bgcolor: "action.hover",
          borderRadius: 1,
        }}
      >
        {ready && (
          <Box
            onMouseDown={onScrollbarMouseDown}
            sx={{
              position: "absolute",
              top: 1,
              bottom: 1,
              left: `${thumbLeftFrac * 100}%`,
              width: `${thumbWidthFrac * 100}%`,
              bgcolor: isZoomed ? "primary.main" : "action.selected",
              borderRadius: 1,
              cursor: isZoomed ? "grab" : "default",
              opacity: isZoomed ? 0.85 : 0.5,
              minWidth: 12,
              "&:hover": isZoomed ? { opacity: 1 } : {},
              "&:active": isZoomed ? { cursor: "grabbing" } : {},
            }}
          />
        )}
      </Box>
      </Box>
    </Stack>
  );
}

// ── Sub-panel scale toggle ───────────────────────────────────────────────────

/** Compact Auto/Fixed toggle used for the SNR and Mass sub-panels'
 *  y-axis scale mode. Sits in the left axis-controls column alongside
 *  the Guide / Pulse axis dropdowns. */
function SubPanelScaleToggle({
  label,
  value,
  onChange,
}: {
  label: string;
  value: "auto" | "fixed";
  onChange: (v: "auto" | "fixed") => void;
}) {
  return (
    <Box>
      <Typography
        variant="caption"
        color="text.secondary"
        sx={{ display: "block", mb: 0.25, fontSize: 11 }}
      >
        {label}
      </Typography>
      <ToggleButtonGroup
        size="small"
        exclusive
        fullWidth
        value={value}
        onChange={(_, v) => {
          if (v) onChange(v as "auto" | "fixed");
        }}
        sx={{
          "& .MuiToggleButton-root": {
            fontSize: 11,
            py: 0.25,
            textTransform: "none",
          },
        }}
      >
        <ToggleButton value="auto">Auto</ToggleButton>
        <ToggleButton value="fixed">Fixed</ToggleButton>
      </ToggleButtonGroup>
    </Box>
  );
}

// ── Legend toggle ────────────────────────────────────────────────────────────

interface LegendToggleProps {
  label: string;
  color: string;
  shape: "line" | "bar" | "triangle";
  active: boolean;
  onToggle: () => void;
}

/** Clickable legend chip — swatch + label. Clicking toggles the series
 *  on/off. The "off" state greys out the swatch and strikes through the
 *  label so users can see at a glance which series are hidden. */
function LegendToggle({ label, color, shape, active, onToggle }: LegendToggleProps) {
  return (
    <Stack
      direction="row"
      spacing={0.5}
      alignItems="center"
      onClick={onToggle}
      sx={{
        cursor: "pointer",
        userSelect: "none",
        px: 0.75,
        py: 0.25,
        borderRadius: 1,
        opacity: active ? 1 : 0.4,
        "&:hover": { bgcolor: "action.hover" },
      }}
    >
      {shape === "line" && <Box sx={{ width: 14, height: 2, bgcolor: color }} />}
      {shape === "bar" && (
        <Box
          sx={{
            width: 6,
            height: 10,
            border: `1px solid ${color}`,
            opacity: 0.6,
          }}
        />
      )}
      {shape === "triangle" && (
        <svg width={12} height={10} style={{ display: "block" }}>
          <path d="M 1,1 L 11,1 L 6,9 Z" fill={color} />
        </svg>
      )}
      <Typography
        variant="caption"
        sx={{
          color,
          textDecoration: active ? "none" : "line-through",
        }}
      >
        {label}
      </Typography>
    </Stack>
  );
}

/**
 * Small triangle caret drawn at the panel's top (``direction="up"``) or
 * bottom (``direction="down"``) edge to signal that a pulse bar was
 * clipped. Width matches the bar; height is capped so the indicator
 * reads as "there's more data here" rather than adding chart noise.
 */
function ClipCaret({
  cx,
  edgeY,
  direction,
  color,
  barW,
}: {
  cx: number;
  edgeY: number;
  direction: "up" | "down";
  color: string;
  barW: number;
}) {
  const w = Math.max(4, barW);
  const h = Math.min(5, w * 0.8);
  const tip = direction === "up" ? edgeY - h : edgeY + h;
  // Base sits flush with the panel edge so the caret looks like a
  // continuation marker growing outward rather than a detached icon.
  return (
    <path
      d={`M ${cx - w / 2},${edgeY} L ${cx + w / 2},${edgeY} L ${cx},${tip} Z`}
      fill={color}
      opacity={0.85}
    />
  );
}

/**
 * Build a [lo, hi] domain for a subpanel that hugs the actual data extent
 * with ~10 % padding on each side, rather than forcing the axis to start
 * at zero. ``minSpan`` is a floor on the range width so a stone-still
 * series still renders a centred line (not a degenerate zero-height
 * scale). When the data is empty, falls back to [0, minSpan].
 */
function snrDomainWithPadding(values: number[], minSpan: number): [number, number] {
  if (values.length === 0) return [0, minSpan];
  const lo = d3.min(values) ?? 0;
  const hi = d3.max(values) ?? 0;
  const span = Math.max(minSpan, hi - lo);
  const pad = span * 0.1;
  return [lo - pad, lo + span + pad];
}

/** Human-readable version of a ``LogEvent.kind`` string for the
 *  event-dot tooltip. Falls back to the raw enum form in Start Case
 *  if we ever add a new kind without wiring a friendly label. */
const EVENT_KIND_LABELS: Record<string, string> = {
  settle_begin: "Settle start",
  settle_end: "Settle complete",
  lock_position_set: "Lock position",
  dither: "Dither",
  server_pause: "Server paused",
  server_resume: "Server resumed",
  star_selected: "Star selected",
  alert: "Alert",
  guiding_enabled: "Guiding enabled",
  guiding_disabled: "Guiding disabled",
  info: "Info",
};

function formatEventKind(kind: string): string {
  return (
    EVENT_KIND_LABELS[kind] ??
    kind
      .split("_")
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join(" ")
  );
}

/** One-line summary for an event inside the tooltip's Events block.
 *  Dither gets the familiar Δx / Δy formatting; other kinds show the
 *  raw INFO message after the friendly label. */
function formatEventSummary(e: LogEvent): string {
  const label = formatEventKind(e.kind);
  if (e.kind === "dither") {
    const dx = e.parsed_fields.dx ?? "?";
    const dy = e.parsed_fields.dy ?? "?";
    return `${label} · Δx=${dx}, Δy=${dy} px`;
  }
  return `${label} · ${e.raw_message}`;
}

function formatPxOrBlank(v: number | null): string {
  if (v === null || v === undefined) return "";
  return v.toFixed(3);
}

function formatPulseOrBlank(
  ms: number | null,
  dir: "W" | "E" | "N" | "S" | null,
): string {
  if (ms == null || ms <= 0) return "";
  return dir ? `${ms} ${dir}` : String(ms);
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
