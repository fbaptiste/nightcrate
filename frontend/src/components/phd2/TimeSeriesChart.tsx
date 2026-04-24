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
import {
  forwardRef,
  useEffect,
  useId,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from "react";
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
import { RIG_BLUE, RIG_ORANGE, RIG_TEAL } from "@/lib/rigColors";

interface Props {
  samples: GuidingSample[];
  /** Section's INFO events — only ``dither`` events are rendered on
   *  the chart. Pass-through from the parsed section. */
  events?: LogEvent[];
  /** Section start timestamp (naive ISO local) — used to render
   *  X-axis tick labels + cursor tooltip as wall-clock. */
  startIso?: string;
  /** Pixel → arcsec conversion factor from the section header. When
   *  supplied the user can toggle the left y-axis between px and ″;
   *  when ``null``/absent the arcsec toggle is disabled. */
  arcsecScale?: number | null;
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
  /** User-drawn selection window (section-relative seconds). Rendered
   *  as a translucent orange band on the main panel; the StatsPanel
   *  on the parent page recomputes metrics over the samples inside. */
  selection?: [number, number] | null;
  /** User-drawn exclusion window. Rendered as a hatched grey band;
   *  samples inside are dropped from the Selection/Viewport summary. */
  exclusion?: [number, number] | null;
  /** Fired when the user Shift-drags to set / adjust / clear the
   *  selection band. ``null`` indicates clear. */
  onSelectionChange?: (range: [number, number] | null) => void;
  /** Fired when the user Shift+Alt-drags to set / adjust / clear the
   *  exclusion band. ``null`` indicates clear. */
  onExclusionChange?: (range: [number, number] | null) => void;
}

const COLOR_RA = RIG_BLUE;
const COLOR_DEC = RIG_ORANGE;

// ``top`` reserves space above the main panel for two vertically-
// separated rows: the existing dither-triangle strip (0–13 px) and the
// three 14 px event-label rows below it (14–56 px), plus a 3 px gap.
// The 60 total gives the event-marker system room to stack up to three
// rows of labels without overlapping the plotted data.
// ``right`` widened from 56 → 72 so the rotated "Pulses (ms)" axis
// label doesn't butt into the tick numbers (4-digit pulse values
// extend further from the axis than single-digit pixel values on
// the left, which is why the crowding was asymmetric).
const MARGIN = { top: 60, right: 72, bottom: 40, left: 56 };
// Event-label strip geometry. Row 0 is the topmost (farthest from
// chart, longest vertical line); row MAX_ROWS-1 is closest to chart.
const EVENT_LABELS_START_Y = 14; // just below the dither triangle row
const EVENT_ROW_HEIGHT = 14;
const EVENT_MAX_ROWS = 3;
const EVENT_LABEL_PAD = 4;

// Left-column absolute-positioning constants. The left column sits
// beside the SVG inside the chart wrapper; each control's top is
// computed from the in-SVG Y of its corresponding panel plus these
// offsets.
const TOOLBAR_HEIGHT_PX = 40;
// Guide unit toggle sits ``UNIT_TOGGLE_OFFSET`` px ABOVE the Guide axis
// Select. The toggle itself is ~44 px tall (caption + ToggleButtonGroup).
// The extra headroom beyond 56 accounts for MUI's floating "Guide axis
// (px)" label that pokes ~10 px above the outlined border — without the
// padding, the label sits right on top of the toggle and the optical
// gap shrinks to ~2 px even though the math said 12.
const UNIT_TOGGLE_OFFSET = 68;
const GUIDE_PULSE_GAP_HALF = 6; // half the vertical gap between Guide + Pulse selects
const GUIDE_PULSE_HALF_H = 40 + GUIDE_PULSE_GAP_HALF; // one Select height + half-gap
const MAIN_H_RATIO = 0.7;
const SNR_H_RATIO = 0.14;
const MASS_H_RATIO = 0.16;
// Gap below the main panel is slightly wider than the SNR↔Mass gap
// so the transition from the primary guide trace down to the small
// diagnostic panels reads as a clear section break.
const PANEL_GAP_MAIN = 21;
const PANEL_GAP_SNR = 18;

// PHD2 occasionally emits sentinel values in place of missing telemetry
// (star lost, detection failure). Any SNR above 1 000 or mass above
// 10 M ADU is treated as sentinel: filtered out of the panel domain
// and the plotted trace so one bogus point doesn't squash the axis.
const MAX_REASONABLE_SNR = 1000;
const MAX_REASONABLE_MASS = 10_000_000;

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

/** Imperative handle exposed via ``ref``. Used by the EventList
 *  click-to-jump flow on ``pages/Phd2AnalyzerPage.tsx`` so the chart
 *  can pan / zoom to a specific section-time without the parent
 *  having to drive d3 directly. */
export interface TimeSeriesChartHandle {
  /** Centre the view on ``time_seconds`` (section-relative). If the
   *  chart is un-zoomed, applies a default ``SCROLL_TO_ZOOM_SECONDS``
   *  window around the target; otherwise preserves the current zoom
   *  level and just pans. */
  scrollToTime(timeSeconds: number): void;
}

/** Default window width (seconds) applied when scrollToTime is called
 *  on an un-zoomed chart — small enough that the event is visually
 *  distinct, wide enough to keep surrounding context. */
const SCROLL_TO_ZOOM_SECONDS = 60;

function TimeSeriesChartInner(
  {
    samples,
    events = [],
    startIso,
    arcsecScale,
    height = 440,
    onViewportChange,
    settleIntervals = [],
    showSettleShading = true,
    selection = null,
    exclusion = null,
    onSelectionChange,
    onExclusionChange,
  }: Props,
  ref: React.Ref<TimeSeriesChartHandle>,
) {
  const theme = useTheme();
  const isDark = theme.palette.mode === "dark";
  // useId() guarantees unique clipPath ids across multiple instances
  // of the chart (e.g. if a future UI paints two sections side-by-side).
  const uid = useId().replace(/:/g, "");
  const clipMain = `phd2-clip-main-${uid}`;
  const clipSnr = `phd2-clip-snr-${uid}`;
  const clipMass = `phd2-clip-mass-${uid}`;
  const excludePatternId = `phd2-exclude-hatch-${uid}`;
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
    events: true,
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
  const [snrScaleMode, setSnrScaleMode] = useState<"auto" | "fixed">("auto");
  const [massScaleMode, setMassScaleMode] = useState<"auto" | "fixed">("auto");
  // Guide-axis display unit. ``arcsec`` requires a known pixel scale
  // from the section header; when absent, the toggle stays disabled
  // and the chart silently stays in pixels.
  const [guideUnit, setGuideUnit] = useState<"px" | "arcsec">("px");
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
  const mainH = innerH * MAIN_H_RATIO - PANEL_GAP_MAIN;
  const snrH = innerH * SNR_H_RATIO - PANEL_GAP_SNR;
  const massH = innerH * MASS_H_RATIO;
  const mainY0 = MARGIN.top;
  const snrY0 = mainY0 + mainH + PANEL_GAP_MAIN;
  const massY0 = snrY0 + snrH + PANEL_GAP_SNR;

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
    // Auto fit only honours the AXES the user has left visible via the
    // legend — hiding RA or Dec should narrow the auto range instead
    // of holding it open for a series the user can't see.
    const distVals = visibleSamples.flatMap((s) => {
      const out: number[] = [];
      if (visibility.ra && s.ra_raw_px !== null) out.push(s.ra_raw_px);
      if (visibility.dec && s.dec_raw_px !== null) out.push(s.dec_raw_px);
      return out;
    });
    // 0.1 px floor on the auto extent — keeps the axis from collapsing
    // on a sub-pixel-noise-only section without holding it open at
    // ±1 px when the real peaks are smaller. Users who need an even
    // tighter window have the fixed ±0.2 / ±0.3 / ±0.4 / ±0.5 dropdown
    // options.
    const autoMaxAbs = distVals.length
      ? Math.max(0.1, d3.max(distVals.map((v) => Math.abs(v))) ?? 0.1)
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
    const visibleDurations = visibleSamples.flatMap((s) => {
      const out: number[] = [];
      if (visibility.raPulse && (s.ra_duration_ms ?? 0) > 0) {
        out.push(s.ra_duration_ms as number);
      }
      if (visibility.decPulse && (s.dec_duration_ms ?? 0) > 0) {
        out.push(s.dec_duration_ms as number);
      }
      return out;
    });
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
    const snrs = snrSamples
      .map((s) => s.snr)
      .filter(
        (v): v is number => v !== null && v >= 0 && v <= MAX_REASONABLE_SNR,
      );
    const [snrLo, snrHi] = snrDomainWithPadding(snrs, 2);
    const masses = massSamples
      .map((s) => s.star_mass)
      .filter(
        (v): v is number => v !== null && v >= 0 && v <= MAX_REASONABLE_MASS,
      );
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
    visibility.ra,
    visibility.dec,
    visibility.raPulse,
    visibility.decPulse,
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
      // Shift-drag is reserved for the selection / exclusion gestures
      // (Shift → select, Shift+Alt → exclude), so d3.zoom ignores those
      // events and lets our own mousedown handler take over.
      .filter((e) => {
        const me = e as MouseEvent;
        if (me.type === "mousedown" && me.shiftKey) return false;
        return !e.ctrlKey && !e.button;
      })
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

  /** Reset React zoom state + d3's internal transform to identity so
   *  subsequent pan/zoom starts from the un-zoomed baseline. Shared by
   *  the section-switch effect and the toolbar Reset button. */
  const resetZoom = () => {
    setZoomX(null);
    if (svgRef.current && zoomBehaviorRef.current) {
      zoomBehaviorRef.current.transform(
        d3.select(svgRef.current),
        d3.zoomIdentity,
      );
    }
  };

  // Reset zoom + pan when the caller swaps in a new samples array
  // (e.g. the user picks a different section in the left nav). Both
  // the React ``zoomX`` state AND d3's internal transform need to go
  // back to identity so the chart mounts "fresh" for the new data.
  useEffect(() => {
    resetZoom();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [samples]);

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
        .defined(
          (s) =>
            s.snr !== null && s.snr >= 0 && s.snr <= MAX_REASONABLE_SNR,
        )
        .x((s) => xScale(s.time_seconds))
        .y((s) => ySnrScale(s.snr ?? 0)),
    [xScale, ySnrScale],
  );
  const massLine = useMemo(
    () =>
      d3
        .line<GuidingSample>()
        .defined(
          (s) =>
            s.star_mass !== null &&
            s.star_mass >= 0 &&
            s.star_mass <= MAX_REASONABLE_MASS,
        )
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
    type PulseBar = {
      x: number;
      y: number;
      h: number;
      clippedAbove: boolean;
      clippedBelow: boolean;
      cx: number;
    };
    const ra: PulseBar[] = [];
    const dec: PulseBar[] = [];
    /** Build a bar for one axis + direction. ``positiveDir`` is the
     *  direction letter that prints above zero (W for RA, N for Dec). */
    const pushBar = (
      bucket: PulseBar[],
      cx: number,
      dur: number,
      dir: string | null,
      positiveDir: string,
    ): void => {
      if (dur <= 0 || !dir) return;
      const sign = dir === positiveDir ? 1 : -1;
      const rawH = Math.abs(yPulseScale(sign * dur) - y0);
      const h = Math.min(panelHalf, Math.max(minH, rawH));
      bucket.push({
        x: cx - barW / 2,
        y: sign > 0 ? y0 - h : y0,
        h,
        clippedAbove: sign > 0 && rawH > panelHalf,
        clippedBelow: sign < 0 && rawH > panelHalf,
        cx,
      });
    };
    for (const s of samples) {
      const cx = xScale(s.time_seconds);
      pushBar(ra, cx, s.ra_duration_ms ?? 0, s.ra_direction, "W");
      pushBar(dec, cx, s.dec_duration_ms ?? 0, s.dec_direction, "N");
    }
    return { ra, dec, barW };
  }, [samples, xScale, yPulseScale, innerW, zoomX, mainH]);

  // Row-packed event markers. Each non-dither event gets a vertical
  // dashed line anchored at its time; a short text label sits at the
  // top in one of ``EVENT_MAX_ROWS`` stacked rows so labels don't
  // overlap. Greedy packing by time order — events that can't fit in
  // any row drop the label but still draw the line so the time is
  // still visually marked. Recomputed each render from ``xScale`` so
  // pan / zoom re-packs the layout automatically.
  const eventMarkers = useMemo(() => {
    const placements: Array<{
      ev: LogEvent;
      x: number;
      row: number | null;
    }> = [];
    const rowRights = new Array<number>(EVENT_MAX_ROWS).fill(-Infinity);
    const sorted = events
      .filter(
        (e): e is LogEvent & { time_seconds: number } =>
          e.kind !== "dither" && e.time_seconds != null,
      )
      .sort((a, b) => a.time_seconds - b.time_seconds);
    for (const ev of sorted) {
      const x = xScale(ev.time_seconds);
      // Cull markers whose x falls outside the visible panel — a few
      // px of slack on each side keeps edge markers from popping in
      // and out mid-pan.
      if (x < MARGIN.left - 8 || x > MARGIN.left + innerW + 8) continue;
      const spec = EVENT_LABEL_SPECS[ev.kind];
      const labelText = spec?.text ?? ev.kind;
      const anchor = spec?.anchor ?? "middle";
      // Label footprint depends on its text-anchor: middle centers on
      // x, end extends leftward to x, start extends rightward from x.
      const { left, right } = labelBounds(x, labelText, anchor);
      let placed: number | null = null;
      for (let r = 0; r < EVENT_MAX_ROWS; r++) {
        if (rowRights[r] < left) {
          rowRights[r] = right;
          placed = r;
          break;
        }
      }
      placements.push({ ev, x, row: placed });
    }
    return placements;
  }, [events, xScale, innerW]);

  const gridColor = isDark ? "rgba(255,255,255,0.08)" : "rgba(0,0,0,0.08)";
  const axisColor = isDark ? "rgba(255,255,255,0.6)" : "rgba(0,0,0,0.6)";
  const textColor = isDark ? "rgba(255,255,255,0.87)" : "rgba(0,0,0,0.87)";
  // Muted palette grey for event labels — deliberately subtle so the
  // labels read as chart ornamentation, not primary signal.
  const mutedColor = isDark ? "rgba(255,255,255,0.55)" : "rgba(0,0,0,0.55)";

  // Resolve the effective guide-axis display unit. Silently fall back
  // to pixels when the pixel scale wasn't declared in the section
  // header — the toggle UI greys out for the same reason.
  const canUseArcsec = arcsecScale != null && arcsecScale > 0;
  const effectiveGuideUnit: "px" | "arcsec" =
    guideUnit === "arcsec" && canUseArcsec ? "arcsec" : "px";
  const guideAxisUnitLabel = effectiveGuideUnit === "arcsec" ? "″" : "px";
  /** Format a pixel value for the guide axis in the currently selected
   *  unit. Arcsec uses two decimals (typical values are 0–10); px keeps
   *  one decimal. */
  const formatGuidePx = (px: number): string => {
    if (effectiveGuideUnit === "arcsec" && canUseArcsec) {
      return (px * (arcsecScale as number)).toFixed(2);
    }
    return px.toFixed(1);
  };

  // d3's ``ticks(5)`` emits "nice" values that typically stop short of
  // the domain endpoints (e.g. [-5, 5] when the domain is [-9.9, 9.9]).
  // Augment with the actual domain extremes so the user can read the
  // clipping bounds at a glance and isn't surprised when a spike
  // reaches further than the last labelled tick.
  const distTicks = withDomainExtremes(yDistScale);
  const pulseTicks = withDomainExtremes(yPulseScale);
  const snrTicks = withDomainExtremes(ySnrScale, 2);
  const massTicks = withDomainExtremes(yMassScale, 2);

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
      // Legend toggles: dither has its own toggle, every other event
      // kind collectively lives under the "Events" toggle.
      if (ev.kind === "dither" && !visibility.dither) continue;
      if (ev.kind !== "dither" && !visibility.events) continue;
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

  const handleReset = resetZoom;

  // Imperative handle — exposed so the EventList on the parent page
  // can pan / zoom the chart to a clicked event without drilling d3
  // through props. Preserves current zoom when already zoomed;
  // applies a default ~60 s window otherwise.
  useImperativeHandle(
    ref,
    () => ({
      scrollToTime: (timeSeconds: number) => {
        const svg = svgRef.current;
        const behavior = zoomBehaviorRef.current;
        if (!svg || !behavior) return;
        if (samples.length < 2) return;
        const [t0, t1] = [
          samples[0].time_seconds,
          samples[samples.length - 1].time_seconds,
        ];
        const fullSpan = Math.max(1e-6, t1 - t0);
        const base = d3
          .scaleLinear()
          .domain([t0, t1])
          .range([MARGIN.left, MARGIN.left + innerW]);
        // Pick a zoom level: keep current k when already zoomed, else
        // derive one from the default scroll window.
        const currentK =
          zoomX !== null
            ? fullSpan / Math.max(1e-6, zoomX[1] - zoomX[0])
            : Math.max(1, fullSpan / SCROLL_TO_ZOOM_SECONDS);
        const transform = d3.zoomIdentity.scale(currentK);
        // Apply scale first so translateTo interprets the target in
        // the correct coord frame, then recenter on the target time.
        d3.select(svg).call(behavior.transform, transform);
        behavior.translateTo(d3.select(svg), base(timeSeconds), 0);
      },
    }),
    // Rebuild the handle when any of these change so the closed-over
    // values stay current. ``zoomX`` inclusion means a subsequent
    // click preserves the new zoom level from the first click.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [samples, innerW, zoomX],
  );

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

  // ── Selection / exclusion drag gestures ────────────────────────────
  //
  // Shift+drag → select a time range; the Selection Summary panel
  // recomputes metrics over the samples inside. Shift+Alt+drag →
  // exclude a range from the Selection / Viewport Summary.
  //
  // A very short drag (< 0.25 s in domain space) treats the gesture
  // as a "click to clear" and resets the corresponding band. d3.zoom's
  // filter above already bypasses shift-keyed mousedowns so this
  // handler owns the gesture start.
  const selectionDragRef = useRef<{
    mode: "select" | "exclude";
    anchorTime: number;
  } | null>(null);

  const handleSelectionMouseDown = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!e.shiftKey) return;
    // Only honour the gesture when at least one of the change callbacks
    // is wired — avoids capturing events on charts rendered without
    // the selection wiring.
    const mode: "select" | "exclude" = e.altKey ? "exclude" : "select";
    if (mode === "select" && !onSelectionChange) return;
    if (mode === "exclude" && !onExclusionChange) return;

    const svg = e.currentTarget;
    const rect = svg.getBoundingClientRect();
    const mx0 = e.clientX - rect.left;
    if (mx0 < MARGIN.left || mx0 > MARGIN.left + innerW) return;
    const anchorTime = clamp(
      xScale.invert(mx0),
      tmin,
      tmax,
    );
    selectionDragRef.current = { mode, anchorTime };
    // Prevent the event from bubbling into d3.zoom's drag start and
    // suppress the browser's default text-selection behaviour.
    e.preventDefault();
    e.stopPropagation();

    const onMove = (ev: MouseEvent) => {
      const drag = selectionDragRef.current;
      if (!drag || !svgRef.current) return;
      const r = svgRef.current.getBoundingClientRect();
      const mx = ev.clientX - r.left;
      const t = clamp(xScale.invert(mx), tmin, tmax);
      const lo = Math.min(drag.anchorTime, t);
      const hi = Math.max(drag.anchorTime, t);
      if (drag.mode === "select") {
        onSelectionChange?.([lo, hi]);
      } else {
        onExclusionChange?.([lo, hi]);
      }
    };
    const onUp = (ev: MouseEvent) => {
      const drag = selectionDragRef.current;
      if (!drag || !svgRef.current) {
        selectionDragRef.current = null;
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup", onUp);
        return;
      }
      const r = svgRef.current.getBoundingClientRect();
      const mx = ev.clientX - r.left;
      const t = clamp(xScale.invert(mx), tmin, tmax);
      const lo = Math.min(drag.anchorTime, t);
      const hi = Math.max(drag.anchorTime, t);
      // Tiny drag (< 0.25 s) → treat as click-to-clear.
      if (hi - lo < 0.25) {
        if (drag.mode === "select") onSelectionChange?.(null);
        else onExclusionChange?.(null);
      } else {
        if (drag.mode === "select") onSelectionChange?.([lo, hi]);
        else onExclusionChange?.([lo, hi]);
      }
      selectionDragRef.current = null;
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
  // Reserved band between the legend row and the chart's SVG top.
  // Bumped from 4 → 54 (+50) so the tooltip, which anchors at the
  // top of this reservation and extends DOWNWARD, has room to paint
  // without covering chart data. The tooltip is ~100 px tall; with a
  // 54 px reservation its bottom lands ~46 px below the chart's SVG
  // top — inside the SVG's decorative margin (dither + event labels)
  // but above the main panel's data area.
  const TOOLTIP_H = 54;
  const tooltipLeft = hover
    ? Math.max(
        MARGIN.left,
        Math.min(MARGIN.left + innerW - TOOLTIP_W, hover.xPx - TOOLTIP_W / 2),
      )
    : 0;

  return (
    <Stack direction="row" alignItems="flex-start" spacing={1} sx={{ width: "100%" }}>
      {/* Axis-range column on the left. Each control is absolutely
          positioned so it aligns with the vertical CENTER of its
          corresponding panel inside the SVG:
          - Guide + Pulse dropdowns straddle the main panel's centre.
          - Guide unit toggle (px / ″) sits just above them.
          - SNR scale toggle lines up with the SNR sub-panel centre.
          - Mass scale toggle lines up with the Mass sub-panel centre.
          TOOLBAR_HEIGHT_PX + TOOLTIP_H give the SVG-top offset inside
          the wrapper; adding the in-SVG Y yields each control's
          wrapper-relative top. */}
      <Box
        sx={{
          flexShrink: 0,
          width: 132,
          position: "relative",
          // Match the total wrapper height (toolbar + tooltip + SVG +
          // scrollbar padding) so absolute children can address any
          // point from 0 down to the scrollbar.
          minHeight: `${TOOLBAR_HEIGHT_PX + TOOLTIP_H + height + 24}px`,
        }}
      >
        {/* Guide unit toggle (px / ″) — placed just above the Guide +
            Pulse dropdown pair so it reads as belonging to the guide
            axis specifically. Disabled when the section header didn't
            declare a pixel scale. */}
        <Box
          sx={{
            position: "absolute",
            top: `${TOOLBAR_HEIGHT_PX + TOOLTIP_H + MARGIN.top + mainH / 2 - GUIDE_PULSE_HALF_H - UNIT_TOGGLE_OFFSET}px`,
            left: 0,
            width: "100%",
          }}
        >
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ display: "block", mb: 0.25, fontSize: 11 }}
          >
            Guide unit
          </Typography>
          <ToggleButtonGroup
            size="small"
            exclusive
            fullWidth
            value={effectiveGuideUnit}
            disabled={!canUseArcsec && guideUnit === "px"}
            onChange={(_, v) => {
              if (v) setGuideUnit(v as "px" | "arcsec");
            }}
            sx={{
              "& .MuiToggleButton-root": {
                fontSize: 11,
                py: 0.25,
                textTransform: "none",
              },
            }}
          >
            <ToggleButton value="px">px</ToggleButton>
            <ToggleButton value="arcsec" disabled={!canUseArcsec}>
              ″
            </ToggleButton>
          </ToggleButtonGroup>
        </Box>
        <FormControl
          size="small"
          sx={{
            position: "absolute",
            top: `${TOOLBAR_HEIGHT_PX + TOOLTIP_H + MARGIN.top + mainH / 2 - GUIDE_PULSE_HALF_H}px`,
            left: 0,
            width: "100%",
          }}
        >
          <InputLabel id="phd2-guide-axis-label">Guide axis ({guideAxisUnitLabel})</InputLabel>
          <Select
            labelId="phd2-guide-axis-label"
            label={`Guide axis (${guideAxisUnitLabel})`}
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
        <FormControl
          size="small"
          sx={{
            position: "absolute",
            top: `${TOOLBAR_HEIGHT_PX + TOOLTIP_H + MARGIN.top + mainH / 2 + GUIDE_PULSE_GAP_HALF}px`,
            left: 0,
            width: "100%",
          }}
        >
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
        {/* ``top`` places the anchor line exactly at the sub-panel's
            vertical centre; ``transform: translateY(-50%)`` shifts the
            toggle up by half its own rendered height so the centre of
            the caption + ToggleButtonGroup pair lands on that line —
            robust against MUI rendering-height surprises. */}
        <Box
          sx={{
            position: "absolute",
            top: `${TOOLBAR_HEIGHT_PX + TOOLTIP_H + snrY0 + snrH / 2}px`,
            left: 0,
            width: "100%",
            transform: "translateY(-50%)",
          }}
        >
          <SubPanelScaleToggle
            label="SNR scale"
            value={snrScaleMode}
            onChange={setSnrScaleMode}
          />
        </Box>
        <Box
          sx={{
            position: "absolute",
            top: `${TOOLBAR_HEIGHT_PX + TOOLTIP_H + massY0 + massH / 2}px`,
            left: 0,
            width: "100%",
            transform: "translateY(-50%)",
          }}
        >
          <SubPanelScaleToggle
            label="Mass scale"
            value={massScaleMode}
            onChange={setMassScaleMode}
          />
        </Box>
      </Box>

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
        {events.some((e) => e.kind !== "dither" && e.time_seconds != null) && (
          <LegendToggle
            label="Events"
            color={mutedColor}
            shape="line"
            active={visibility.events}
            onToggle={() => setVisibility((v) => ({ ...v, events: !v.events }))}
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
          Scroll to zoom · drag to pan · shift-drag to select · shift+alt-drag to exclude
        </Typography>
        {selection && onSelectionChange && (
          <Button
            size="small"
            onClick={() => onSelectionChange(null)}
          >
            Clear selection
          </Button>
        )}
        {exclusion && onExclusionChange && (
          <Button
            size="small"
            onClick={() => onExclusionChange(null)}
          >
            Clear exclusion
          </Button>
        )}
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
              // Anchor top at the wrapper's origin (the toolbar's top
              // edge). The reservation Box sits below the toolbar, so
              // ``-TOOLBAR_HEIGHT_PX`` moves the tooltip UP to that
              // point and it extends downward from there — covering
              // the toolbar + the SVG's top-margin ornaments, but
              // never above the chart wrapper (which avoids getting
              // clipped by the outer Tabs container).
              top: `-${TOOLBAR_HEIGHT_PX}px`,
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
              zIndex: 2,
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
            {/* Events block intentionally omitted — event info is now
                fully conveyed by the vertical-line markers + top-row
                labels on the chart, so duplicating here would be
                redundant noise. Hover-snap still drives the crosshair
                colour change for visual continuity. */}
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
        onMouseDown={handleSelectionMouseDown}
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
          {/* Diagonal-hatch pattern for the exclusion band — visually
              distinct from the solid-grey settle shading. */}
          <pattern
            id={excludePatternId}
            patternUnits="userSpaceOnUse"
            width={6}
            height={6}
            patternTransform="rotate(45)"
          >
            <rect
              width={6}
              height={6}
              fill={isDark ? "rgba(255,255,255,0.04)" : "rgba(0,0,0,0.04)"}
            />
            <line
              x1={0}
              y1={0}
              x2={0}
              y2={6}
              stroke={isDark ? "rgba(255,255,255,0.18)" : "rgba(0,0,0,0.18)"}
              strokeWidth={1.5}
            />
          </pattern>
        </defs>

        {/* Uniform background tint on all three panels so they read as
            a family — separates the plotted data area from the outer
            chart wrapper at a glance. */}
        {(
          [
            ["main-bg", mainY0, mainH],
            ["snr-bg", snrY0, snrH],
            ["mass-bg", massY0, massH],
          ] as const
        ).map(([key, y0, h]) => (
          <rect
            key={key}
            x={MARGIN.left}
            y={y0}
            width={innerW}
            height={h}
            fill={isDark ? "rgba(255,255,255,0.04)" : "rgba(0,0,0,0.04)"}
          />
        ))}

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
        {/* Main panel top + bottom reference rules in soft grid colour.
            No vertical enclosure — matches the SNR / Mass subpanels'
            unbounded look so the three panels read as a family. */}
        <line
          x1={MARGIN.left}
          x2={MARGIN.left + innerW}
          y1={mainY0}
          y2={mainY0}
          stroke={gridColor}
          strokeWidth={1}
        />
        <line
          x1={MARGIN.left}
          x2={MARGIN.left + innerW}
          y1={mainY0 + mainH}
          y2={mainY0 + mainH}
          stroke={gridColor}
          strokeWidth={1}
        />

        {/* Settle-window shading — paints FIRST so pulse bars + traces
            render on top. Signals "these samples are excluded from the
            guide-quality stats per PHD2 / PHDLogViewer convention".
            Same translucent grey across all three panels. */}
        {showSettleShading && settleIntervals.length > 0 && (
          <>
            {(
              [
                ["main", clipMain, mainY0, mainH],
                ["snr", clipSnr, snrY0, snrH],
                ["mass", clipMass, massY0, massH],
              ] as const
            ).map(([panel, clipId, y0, h]) => (
              <g key={`settle-${panel}`} clipPath={`url(#${clipId})`}>
                {settleIntervals.map(([t0, t1], i) => (
                  <rect
                    key={`settle-${panel}-${i}`}
                    x={xScale(t0)}
                    y={y0}
                    width={Math.max(1, xScale(t1) - xScale(t0))}
                    height={h}
                    fill={isDark ? "rgba(255,255,255,0.10)" : "rgba(0,0,0,0.08)"}
                  />
                ))}
              </g>
            ))}
          </>
        )}

        {/* User-drawn selection band (orange) + exclusion band (hatched
            grey). Anchored in section-time so they stay put under
            zoom/pan. Stroke at the edges gives a clear boundary for
            click-to-clear discoverability. */}
        {selection && (
          <g clipPath={`url(#${clipMain})`}>
            <rect
              x={xScale(selection[0])}
              y={mainY0}
              width={Math.max(1, xScale(selection[1]) - xScale(selection[0]))}
              height={mainH}
              fill={RIG_TEAL}
              fillOpacity={0.14}
              stroke={RIG_TEAL}
              strokeOpacity={0.7}
              strokeWidth={1}
              strokeDasharray="2 2"
              pointerEvents="none"
            />
          </g>
        )}
        {exclusion && (
          <g clipPath={`url(#${clipMain})`}>
            <rect
              x={xScale(exclusion[0])}
              y={mainY0}
              width={Math.max(1, xScale(exclusion[1]) - xScale(exclusion[0]))}
              height={mainH}
              fill={`url(#${excludePatternId})`}
              stroke={axisColor}
              strokeOpacity={0.5}
              strokeWidth={1}
              strokeDasharray="4 3"
              pointerEvents="none"
            />
          </g>
        )}

        {/* Everything inside the main panel's data area is clipped so
            pulse bars and traces can never paint over the tick labels
            that sit in MARGIN.left / MARGIN.right. */}
        <g clipPath={`url(#${clipMain})`}>
          {/* Pulse bars — drawn BEFORE traces so lines paint on top. */}
          {(
            [
              [visibility.raPulse, pulseBars.ra, COLOR_RA, "rab"] as const,
              [visibility.decPulse, pulseBars.dec, COLOR_DEC, "decb"] as const,
            ]
          ).flatMap(([visible, bars, color, keyPrefix]) =>
            !visible
              ? []
              : bars.map((b, i) => (
                  <rect
                    key={`${keyPrefix}-${i}`}
                    x={b.x}
                    y={b.y}
                    width={pulseBars.barW}
                    height={b.h}
                    fill="none"
                    stroke={color}
                    strokeWidth={1}
                    opacity={0.5}
                  />
                )),
          )}

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
            reads like a continuation marker rather than extra noise.
            Skip carets whose sample sits outside the horizontal plot
            area — bars are cropped via clipPath, but carets live outside
            that group so the horizontal bounds check has to happen in JS. */}
        {(
          [
            [visibility.raPulse, pulseBars.ra, COLOR_RA, "rac"] as const,
            [visibility.decPulse, pulseBars.dec, COLOR_DEC, "decc"] as const,
          ]
        ).flatMap(([visible, bars, color, keyPrefix]) =>
          !visible
            ? []
            : bars.map((b, i) => {
                if (!b.clippedAbove && !b.clippedBelow) return null;
                if (b.cx < MARGIN.left || b.cx > MARGIN.left + innerW) return null;
                return (
                  <ClipCaret
                    key={`${keyPrefix}-${i}`}
                    cx={b.cx}
                    edgeY={b.clippedAbove ? mainY0 : mainY0 + mainH}
                    direction={b.clippedAbove ? "up" : "down"}
                    color={color}
                    barW={pulseBars.barW}
                  />
                );
              }),
        )}

        {/* Event markers — vertical dashed line per non-dither event
            descending from the label strip through every panel, plus a
            short label at the top in the row assigned by the packing
            algorithm. Hover detection stays at the SVG level via
            ``handleMouseMove`` so the main tooltip's Events block
            unifies dither triangle, event marker, and settle-window
            boundary hovers into one surface. */}
        {visibility.events && eventMarkers.map(({ ev, x, row }, i) => {
          const spec = EVENT_LABEL_SPECS[ev.kind];
          const labelText = spec?.text ?? ev.kind;
          // All event labels render in the subtle muted grey — the
          // categorical colours on ``spec`` are retained for future
          // use but the UI reads better with a uniform palette tone
          // so the labels don't compete with the plotted data.
          const labelColor = mutedColor;
          const labelTopY =
            EVENT_LABELS_START_Y + (row ?? 0) * EVENT_ROW_HEIGHT;
          // Line top sits just below the label's baseline row when
          // one was assigned; falls back to the top of the label strip
          // for no-label markers so those still have a visible line.
          const lineTop =
            row === null
              ? EVENT_LABELS_START_Y
              : labelTopY + EVENT_ROW_HEIGHT - 2;
          return (
            <g key={`evt-${ev.kind}-${ev.time_seconds}-${i}`} pointerEvents="none">
              <line
                x1={x}
                x2={x}
                y1={lineTop}
                y2={massY0 + massH}
                stroke={axisColor}
                strokeDasharray="3 3"
                strokeWidth={1}
                opacity={0.5}
              />
              {row !== null && (
                <text
                  x={x}
                  y={labelTopY + EVENT_ROW_HEIGHT - 3}
                  fontSize={10}
                  fontWeight={500}
                  textAnchor={spec?.anchor ?? "middle"}
                  fill={labelColor}
                >
                  {labelText}
                </text>
              )}
            </g>
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
              // Dither triangles sit just above the main panel's top
              // edge — visually "pointing at" the panel. Vertical
              // overlap with the event-label strip only kicks in if a
              // non-settle label lands at exactly the same X, which
              // is rare (settle_begin fires at the same time as
              // dither but its label goes in the top row, nowhere
              // near this band).
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

        {/* Left-axis ticks (distance). Values stay in pixel domain;
            only the displayed label is converted to arcsec when the
            user has switched units. */}
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
            {formatGuidePx(t)}
          </text>
        ))}
        {/* Guide error + Pulses panel titles moved OUT of the SVG to
            the HTML banner above the chart — they were overlapping
            the plotted data at small Y ranges. */}

        {/* Right-axis ticks (pulse duration, ms). Values rounded to
            integers — pulse durations are inherently integer ms, and
            the ``withDomainExtremes`` augmentation can surface floats
            from the auto-fit padding that would otherwise render
            "8269.8000" next to the tidy "2000" of the nice ticks. */}
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
            {Math.round(t)}
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
            {/* Round to one decimal — avoids float-precision garbage
                like "0.000000002" on domain extremes added by
                ``withDomainExtremes`` and trims "16.908" to "16.9". */}
            {formatTenth(t)}
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
            {formatMassTick(t)}
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
            ``rotate(-90)`` makes the text read from bottom to top.
            Main-panel labels use 11px + opaque; sub-panel labels use
            10px + 0.85 opacity to read as secondary signal. */}
        {(
          [
            [14, mainY0 + mainH / 2, `Guide error (${guideAxisUnitLabel})`, 11, 1.0],
            [width - 14, mainY0 + mainH / 2, "Pulses (ms)", 11, 1.0],
            [14, snrY0 + snrH / 2, "SNR", 10, 0.85],
            [14, massY0 + massH / 2, "Mass (ADU)", 10, 0.85],
          ] as const
        ).map(([x, y, label, size, opacity]) => (
          <text
            key={label}
            transform={`translate(${x}, ${y}) rotate(-90)`}
            fill={textColor}
            fillOpacity={opacity}
            fontSize={size}
            fontWeight={600}
            textAnchor="middle"
          >
            {label}
          </text>
        ))}

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

const TimeSeriesChart = forwardRef<TimeSeriesChartHandle, Props>(
  TimeSeriesChartInner,
);
export default TimeSeriesChart;

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
  // The caption floats ABOVE the toggle via ``position: absolute`` so
  // the component's flow-height equals the ToggleButtonGroup alone.
  // The outer positioning layer can then ``translateY(-50%)`` to
  // centre the TOGGLE (not the caption+toggle pair) on the panel's
  // vertical midpoint — the caption drifts above centre, which reads
  // better than a toggle sitting off-centre.
  return (
    <Box sx={{ position: "relative" }}>
      <Typography
        variant="caption"
        color="text.secondary"
        sx={{
          position: "absolute",
          bottom: "100%",
          left: 0,
          right: 0,
          display: "block",
          mb: 0.25,
          fontSize: 11,
        }}
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

/** Short abbreviation + colour category for each non-dither event
 *  kind. Kept concise so the row-packing algorithm in ``eventMarkers``
 *  can stack more events in fewer rows. ``anchor`` controls which
 *  glyph sits on the vertical line: "end" anchors the rightmost
 *  character at the line (text grows leftward), "start" anchors the
 *  leftmost character (text grows rightward), "middle" centers the
 *  label on the line. Dither is intentionally absent — it has its
 *  own triangle marker and parsed Δx/Δy that don't fit a single-
 *  label style. */
const EVENT_LABEL_SPECS: Partial<
  Record<
    string,
    {
      text: string;
      category: "blue" | "orange" | "teal" | "neutral";
      anchor: "start" | "middle" | "end";
    }
  >
> = {
  // Settle begin: arrow on the RIGHT end of the label, pointing into
  // the line at its X. Text reads leftward from the line.
  settle_begin: { text: "Settle ▶", category: "blue", anchor: "end" },
  // Settle end: arrow on the LEFT end, pointing into the line from
  // the right side. Text reads rightward from the line.
  settle_end: { text: "◀ Settle", category: "blue", anchor: "start" },
  lock_position_set: { text: "Lock pos", category: "neutral", anchor: "middle" },
  star_selected: { text: "Star pick", category: "neutral", anchor: "middle" },
  alert: { text: "Alert", category: "orange", anchor: "middle" },
  guiding_enabled: { text: "Guide ▶", category: "teal", anchor: "end" },
  guiding_disabled: { text: "◀ Guide", category: "teal", anchor: "start" },
  server_pause: { text: "Pause", category: "neutral", anchor: "middle" },
  server_resume: { text: "Resume", category: "neutral", anchor: "middle" },
  info: { text: "Info", category: "neutral", anchor: "middle" },
};

/** Round to the nearest 0.1 and strip trailing zeros. Keeps SNR tick
 *  labels tidy when d3 emits float-precision residuals like
 *  ``1.9999999997e-9`` for near-zero ticks. */
function formatTenth(t: number): string {
  const rounded = Math.round(t * 10) / 10;
  return rounded.toString();
}

/** Mass ticks need enough precision to stay distinct — the prior
 *  ``${Math.round(t / 1000)}k`` rendered "1k" for every tick in
 *  [500, 1499] when the domain hugged 1 000. Use `toLocaleString`
 *  for integers up to 9 999, then 1-decimal "N.Nk" above that. */
function formatMassTick(t: number): string {
  if (t < 1000) return Math.round(t).toLocaleString();
  if (t < 10_000) return `${(t / 1000).toFixed(1)}k`;
  return `${Math.round(t / 1000)}k`;
}

function clamp(v: number, lo: number, hi: number): number {
  return v < lo ? lo : v > hi ? hi : v;
}

/** Augments d3's ``ticks()`` with the scale's domain endpoints so the
 *  user sees a labelled tick at the panel's clipping extremes, not
 *  just at the nearest nice number inside the domain. Near-duplicates
 *  (endpoint within ~5 % of spacing of an existing tick) are dropped
 *  so labels don't overlap. */
function withDomainExtremes(
  scale: d3.ScaleLinear<number, number>,
  tickCount: number = 5,
): number[] {
  const base = scale.ticks(tickCount);
  const [lo, hi] = scale.domain();
  const span = Math.abs(hi - lo);
  const nearTolerance = span * 0.05;
  const augmented = [...base];
  if (!base.some((t) => Math.abs(t - lo) < nearTolerance)) augmented.push(lo);
  if (!base.some((t) => Math.abs(t - hi) < nearTolerance)) augmented.push(hi);
  return augmented.sort((a, b) => a - b);
}

/** Absolute [left, right] screen-x extent of a label anchored at
 *  ``centerX`` with the given SVG ``text-anchor``. Width is estimated
 *  at ~3.3 px per char for a 10 px sans-serif — close enough for
 *  row-packing; ``EVENT_LABEL_PAD`` adds slack on both sides so
 *  rare under-estimates don't cause overlap. */
function labelBounds(
  centerX: number,
  text: string,
  anchor: "start" | "middle" | "end",
): { left: number; right: number } {
  const width = Math.max(24, text.length * 3.3);
  const pad = EVENT_LABEL_PAD;
  if (anchor === "middle") {
    return { left: centerX - width / 2 - pad, right: centerX + width / 2 + pad };
  }
  if (anchor === "end") {
    return { left: centerX - width - pad, right: centerX + pad };
  }
  return { left: centerX - pad, right: centerX + width + pad };
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
