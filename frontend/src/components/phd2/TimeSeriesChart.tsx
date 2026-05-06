/**
 * PHD2 time-series chart.
 *
 * - One main chart area with *dual y-axes*. Left axis shows the RA/Dec
 *   raw distance (pixels); right axis shows the guide-pulse duration
 *   (milliseconds). Both scales are zero-aligned to the same horizontal
 *   line so a W pulse (positive RA correction) prints above zero along
 *   with any positive star deflection, and an E pulse prints below.
 * - Separate SNR + star-mass sub-panels underneath — useful context
 *   for diagnosing lost-star events.
 * - User-adjustable Y range for every axis: vertical sliders flank
 *   the chart (guide / SNR / Mass on the left; pulse on the right).
 *   Each slider drag locks the axis to the chosen ceiling; a reset
 *   icon below restores auto-fit.
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
import FormControlLabel from "@mui/material/FormControlLabel";
import IconButton from "@mui/material/IconButton";
import Slider from "@mui/material/Slider";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AutorenewIcon from "@mui/icons-material/Autorenew";
import RestartAltIcon from "@mui/icons-material/RestartAlt";
import VisibilityIcon from "@mui/icons-material/Visibility";
import VisibilityOffIcon from "@mui/icons-material/VisibilityOff";

import { useSettingsStore } from "@/stores/settingsStore";
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
  /** User-drawn selection windows — translucent teal bands. Samples
   *  inside the union of selections form the base set for the
   *  Selection / Viewport summary panel; exclusions subtract from
   *  that base. Multiple selections accumulate via shift-drag. */
  selections?: Array<[number, number]>;
  /** User-drawn exclusion windows — hatched-grey bands. Samples
   *  inside any exclusion are dropped from the summary. Multiple
   *  exclusions accumulate via shift+alt-drag. */
  exclusions?: Array<[number, number]>;
  /** Parent's state setter for selections. Chart computes the new
   *  array (append on shift-drag, splice on × click, empty array on
   *  Clear all) and forwards it via this callback. */
  onSelectionsChange?: (next: Array<[number, number]>) => void;
  /** Parent's state setter for exclusions. Same contract as
   *  ``onSelectionsChange``. */
  onExclusionsChange?: (next: Array<[number, number]>) => void;
  /** Page-level "include settle in stats" toggle, threaded into the
   *  chart so the toggle UI sits in the chart toolbar alongside the
   *  X-zoom controls. Drives the Section + Viewport / Selection
   *  summary metrics filter and the chart's settle-region shading
   *  (via ``showSettleShading``); does not modify selection or
   *  exclusion gestures. */
  includeSettle?: boolean;
  onIncludeSettleChange?: (v: boolean) => void;
}

const COLOR_RA = RIG_BLUE;
const COLOR_DEC = RIG_ORANGE;

// ``top`` reserves space above the main panel for two vertically-
// separated rows: the existing dither-triangle strip (0–13 px) and the
// three 14 px event-label rows below it (14–56 px), plus a 3 px gap.
// The 60 total gives the event-marker system room to stack up to three
// rows of labels without overlapping the plotted data.
// ``left`` / ``right`` are tight (44 / 56) so the chart's data area
// extends close to the sliders flanking the SVG. Right is slightly
// wider than left to accommodate 4-digit pulse-axis tick labels.
const MARGIN = { top: 60, right: 56, bottom: 40, left: 44 };
// Event-label strip geometry. Row 0 is the topmost (farthest from
// chart, longest vertical line); row MAX_ROWS-1 is closest to chart.
const EVENT_LABELS_START_Y = 14; // just below the dither triangle row
const EVENT_ROW_HEIGHT = 14;
const EVENT_MAX_ROWS = 3;
const EVENT_LABEL_PAD = 4;

// Panel-height ratios chosen so SNR and Mass render at the SAME
// absolute height (~110 px each at the default chart height) — the
// user expected the two diagnostic panels to read as a matched pair,
// not a stretched / shrunken variant. ``MAIN_H_RATIO`` carries the
// slack so the three ratios sum to 1.0. ``SNR_H_RATIO`` is slightly
// larger than ``MASS_H_RATIO`` because the snr panel formula
// subtracts ``PANEL_GAP_SNR`` to leave room for the gap above the
// mass panel; the visible track works out equal.
const MAIN_H_RATIO = 0.54;
const SNR_H_RATIO = 0.26;
const MASS_H_RATIO = 0.2;
// Generous panel gaps with a theme-aware divider line at the midpoint
// of each gap make the panel splits visually unambiguous — narrower
// gaps had the traces blurring into one tall plot. Each divider also
// doubles as a drag-to-resize handle (see ``handleDividerMouseDown``).
const PANEL_GAP_MAIN = 36;
const PANEL_GAP_SNR = 32;

// Stable empty-record reference for zustand selectors. Returning a
// fresh ``{}`` from a selector on every call triggers an infinite
// render loop (zustand's default Object.is comparator sees a new
// reference every time → re-render → re-select → re-render).
const EMPTY_RECORD: Record<string, number> = Object.freeze({});

// Panel identity. ``main`` is the multi-trace guide-error panel; the
// other three are diagnostic strips with their own y-axis. Hoisted to
// module scope so the (frozen) ``PANEL_LABEL`` lookup doesn't get
// reallocated on every render and consumers can use it for tooltips
// or stub strings without a switch / nested ternary.
type PanelKey = "main" | "snr" | "mass";
const PANEL_LABEL: Record<PanelKey, string> = {
  main: "Guide error",
  snr: "SNR",
  mass: "Mass",
};
const PANEL_MAX_H = 600;

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
    height = 650,
    onViewportChange,
    settleIntervals = [],
    showSettleShading = true,
    selections = [],
    exclusions = [],
    onSelectionsChange,
    onExclusionsChange,
    includeSettle,
    onIncludeSettleChange,
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
  const toolbarRef = useRef<HTMLDivElement | null>(null);
  // Measured height of the toolbar Stacks above the SVG. The slider
  // rails position children using ``topOffset = toolbarHeight +
  // TOOLTIP_H + panelY``; reading the actual rendered height keeps
  // the slider track aligned with the SVG's panel boundaries even as
  // toolbar rows are added / removed conditionally (e.g., the
  // selection-action row only appears when the chart is interactive).
  const [toolbarHeight, setToolbarHeight] = useState(0);
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
  // User-adjustable Y ranges for the two main-panel axes. ``null`` =
  // auto-fit the domain to the visible data on each render (initial
  // load + section change); a positive number locks the axis to ±value
  // so the user's slider position survives subsequent zoom / section
  // changes. First slider drag transitions the state from null → number.
  // A reset button per slider sets it back to null. State stored in
  // pixels for guide and milliseconds for pulse — the slider UI handles
  // arcsec-mode display via valueLabelFormat.
  const [guideAxisMax, setGuideAxisMax] = useState<number | null>(null);
  const [pulseAxisMax, setPulseAxisMax] = useState<number | null>(null);
  // Sub-panel y-axis upper bounds — same null-means-auto-fit pattern
  // as the guide / pulse axes. Slider drag promotes state from null
  // to a number; reset returns to null. Lower bound stays at the
  // auto-fit value (snrDomainWithPadding) regardless — only the
  // ceiling is user-controllable.
  const [snrAxisMax, setSnrAxisMax] = useState<number | null>(null);
  const [massAxisMax, setMassAxisMax] = useState<number | null>(null);
  const updateSettings = useSettingsStore((s) => s.update);
  // Per-panel collapse toggles (eye icon on the left of each non-main
  // panel). When false the panel renders as a thin stub showing only
  // the toggle so the user can always restore it; the chart's overall
  // height shrinks by the panel's full size minus the stub height.
  const [panelExpanded, setPanelExpanded] = useState({
    snr: true,
    mass: true,
  });
  // Persisted panel heights from settings (per-user, drag-to-resize).
  // Each value is an absolute pixel height for the panel; missing keys
  // fall back to the ratio-derived default. Values clamp to [default,
  // 600] so the user can grow but not shrink below the layout's
  // sensible minimum.
  const persistedPanelHeights = useSettingsStore(
    (s) => s.settings?.phd2_panel_heights ?? EMPTY_RECORD,
  );
  // In-flight drag override — applied per-panel during mousemove for
  // smooth feedback without round-tripping every motion event through
  // settings persistence.
  const [dragPanelHeights, setDragPanelHeights] = useState<
    Record<string, number>
  >({});
  const dragRef = useRef<{
    panelKey: PanelKey;
    startMouseY: number;
    startHeight: number;
    minHeight: number;
    currentHeight: number;
  } | null>(null);
  // Guide-axis display unit. ``arcsec`` requires a known pixel scale
  // from the section header; when absent, the toggle stays disabled
  // and the chart silently stays in pixels.
  const [guideUnit, setGuideUnit] = useState<"px" | "arcsec">("px");
  // Live-preview rectangles for in-progress shift-drag / shift+alt-
  // drag. Committed arrays live on the parent; only on mouseup do we
  // fire ``onSelectionsChange`` / ``onExclusionsChange`` with the new
  // appended value.
  const [pendingSelection, setPendingSelection] = useState<
    [number, number] | null
  >(null);
  const [pendingExclusion, setPendingExclusion] = useState<
    [number, number] | null
  >(null);
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

  useEffect(() => {
    if (!toolbarRef.current) return;
    const obs = new ResizeObserver((entries) => {
      const h = entries[0]?.contentRect.height ?? 0;
      setToolbarHeight(h);
    });
    obs.observe(toolbarRef.current);
    return () => obs.disconnect();
  }, []);

  // Data domain extrema (used for the scrollbar + zoom base scale).
  const [tmin, tmax] = useMemo(() => {
    if (samples.length === 0) return [0, 1];
    return [samples[0].time_seconds, samples[samples.length - 1].time_seconds];
  }, [samples]);

  // Panel rectangles. Each non-main panel can be collapsed to a thin
  // ``STUB_H`` strip that shows only the eye-toggle icon (so the user
  // can always restore it). The chart's overall height is the sum of
  // visible panel heights + gaps + margins — collapsing a panel
  // shrinks the total chart.
  const STUB_H = 22;
  const innerW = Math.max(100, width - MARGIN.left - MARGIN.right);
  const innerH = height - MARGIN.top - MARGIN.bottom;
  // Default ratio-derived sizes — these are also the minimum heights
  // for each panel (user can drag to grow, never shrink below).
  const defaultMainH = innerH * MAIN_H_RATIO - PANEL_GAP_MAIN;
  const defaultSnrFullH = innerH * SNR_H_RATIO - PANEL_GAP_SNR;
  const defaultMassFullH = innerH * MASS_H_RATIO;

  // Resolve effective heights = drag override (if mid-drag) || persisted
  // setting || default. Always clamped to [default, PANEL_MAX_H] —
  // shrinking below the ratio-derived layout breaks the chart. Drag
  // override takes precedence so feedback is immediate.
  const resolvePanelHeight = (key: PanelKey, defaultH: number): number => {
    const drag = dragPanelHeights[key];
    const persisted = persistedPanelHeights[key];
    const candidate = drag ?? persisted ?? defaultH;
    return Math.max(defaultH, Math.min(PANEL_MAX_H, candidate));
  };
  const mainH = resolvePanelHeight("main", defaultMainH);
  const snrFullH = resolvePanelHeight("snr", defaultSnrFullH);
  const massFullH = resolvePanelHeight("mass", defaultMassFullH);

  const snrH = panelExpanded.snr ? snrFullH : STUB_H;
  const massH = panelExpanded.mass ? massFullH : STUB_H;
  const mainY0 = MARGIN.top;
  const snrY0 = mainY0 + mainH + PANEL_GAP_MAIN;
  const massY0 = snrY0 + snrH + PANEL_GAP_SNR;
  // Effective SVG height — shrinks as panels collapse, grows as the
  // user drags any panel taller.
  const effectiveSvgHeight = massY0 + massH + MARGIN.bottom;

  // Divider layout — y-coordinates within the SVG plus the panel each
  // divider resizes (the panel ABOVE the divider). The Mass-bottom
  // divider sits just above the SVG bottom edge; dragging it grows
  // the Mass panel. When a panel is collapsed (panelExpanded[key] =
  // false), its divider is suppressed since the height-resize would
  // be invisible.
  type DividerInfo = {
    key: PanelKey;
    y: number;
    currentHeight: number;
    minHeight: number;
  };
  const dividerLayout: DividerInfo[] = [];
  dividerLayout.push({
    key: "main",
    y: mainY0 + mainH + PANEL_GAP_MAIN / 2,
    currentHeight: mainH,
    minHeight: defaultMainH,
  });
  if (panelExpanded.snr) {
    dividerLayout.push({
      key: "snr",
      y: snrY0 + snrH + PANEL_GAP_SNR / 2,
      currentHeight: snrH,
      minHeight: defaultSnrFullH,
    });
  }
  if (panelExpanded.mass) {
    dividerLayout.push({
      key: "mass",
      y: effectiveSvgHeight - 4,
      currentHeight: massH,
      minHeight: defaultMassFullH,
    });
  }

  // Scales.
  const {
    xScale,
    yDistScale,
    yPulseScale,
    ySnrScale,
    yMassScale,
    effectiveGuideMax,
    effectivePulseMax,
    effectiveSnrMax,
    effectiveMassMax,
    snrHiAuto,
    snrMedian,
    massHiAuto,
    massMedian,
  } = useMemo(() => {
    const times = samples.map((s) => s.time_seconds);
    const tmin = times.length ? times[0] : 0;
    const tmax = times.length ? times[times.length - 1] : 1;

    // Auto / manual left-axis range. Auto fits over the FULL section
    // (not the visible window) so the y-axis stays put as the user
    // pans across the X-axis — matching the SNR + Mass sub-panels'
    // behaviour. Manual (user-picked ±N px) clamps to that fixed
    // range; data outside the range clips at the panel edges.
    // Auto fit only honours the AXES the user has left visible via the
    // legend — hiding RA or Dec narrows the auto range instead of
    // holding it open for a series the user can't see.
    const distVals = samples.flatMap((s) => {
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
    const maxAbs =
      guideAxisMax !== null && guideAxisMax > 0
        ? guideAxisMax
        : autoMaxAbs * 1.1;

    // Pulse axis range — fits the FULL section so panning doesn't
    // re-fit. Auto = full-section max + 10 % headroom with a 50 ms
    // floor so a quiet all-zero region still renders a usable scale.
    const pulseDurations = samples.flatMap((s) => {
      const out: number[] = [];
      if (visibility.raPulse && (s.ra_duration_ms ?? 0) > 0) {
        out.push(s.ra_duration_ms as number);
      }
      if (visibility.decPulse && (s.dec_duration_ms ?? 0) > 0) {
        out.push(s.dec_duration_ms as number);
      }
      return out;
    });
    const pulseDurMax = pulseDurations.length
      ? (d3.max(pulseDurations) ?? 0)
      : 0;
    const autoDurMax = Math.max(50, pulseDurMax * 1.1);
    const durMax =
      pulseAxisMax !== null && pulseAxisMax > 0 ? pulseAxisMax : autoDurMax;

    // SNR + mass are tight-fit around the observed extent so subtle
    // variation is actually readable. Earlier behaviour (``[0, max*1.1]``)
    // squashed the trace to a flat line when the minimum was well above
    // zero (typical — SNR stays in the 15–40 band for a healthy star).
    // Sample source is always the visible window so the axis tightens
    // when panning into a quieter stretch — matching the guide / pulse
    // axes' auto-fit behaviour. The user's slider override (when set)
    // replaces the upper bound with their chosen value.
    // SNR + Mass sub-panels: axis MIN is locked at the data's
    // auto-fit lo so the data's lower extreme is always visible.
    // Axis MAX is the slider value (or auto-fit hi when state is
    // null). Dragging UP shrinks the upper bound — the data trace
    // fills more of the panel vertically while the floor stays
    // anchored. The slider's min value is clamped above the
    // median (see slider props below) so the bulk can never get
    // pushed off the top of the panel.
    //
    // Sample source is the FULL section, not the visible window —
    // y-axis zoom stays stable while panning / zooming the X-axis.
    const snrs = samples
      .map((s) => s.snr)
      .filter(
        (v): v is number => v !== null && v >= 0 && v <= MAX_REASONABLE_SNR,
      );
    const [snrLoAuto, snrHiAuto] = snrDomainWithPadding(snrs, 2);
    const snrMedian =
      snrs.length > 0 ? (d3.median(snrs) ?? snrLoAuto) : snrLoAuto;
    const snrLo = snrLoAuto;
    const snrHi =
      snrAxisMax !== null && snrAxisMax > snrMedian ? snrAxisMax : snrHiAuto;
    const masses = samples
      .map((s) => s.star_mass)
      .filter(
        (v): v is number => v !== null && v >= 0 && v <= MAX_REASONABLE_MASS,
      );
    const [massLoAuto, massHiAuto] = snrDomainWithPadding(masses, 100);
    const massMedian =
      masses.length > 0 ? (d3.median(masses) ?? massLoAuto) : massLoAuto;
    const massLo = massLoAuto;
    const massHi =
      massAxisMax !== null && massAxisMax > massMedian
        ? massAxisMax
        : massHiAuto;

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
      // Surfaced so the vertical scale sliders can render their
      // position even when state is null (auto-fit) — the slider's
      // thumb tracks the effective upper bound regardless of which
      // branch produced the value. The ``…HiAuto`` companions drive
      // the sub-panel sliders' dynamic min/max so the auto-fit value
      // sits at the slider's top (most-zoomed-in) and the slider only
      // grants zoom-out range from there. Without that, slider min
      // sat well below the typical SNR / Mass auto value, leaving the
      // thumb perched at the top and the useful range crammed into
      // a few pixels.
      effectiveGuideMax: maxAbs,
      effectivePulseMax: durMax,
      effectiveSnrMax: snrHi,
      effectiveMassMax: massHi,
      snrHiAuto,
      snrMedian,
      massHiAuto,
      massMedian,
    };
    // mainY0 / snrY0 / massY0 are derived from the same inputs the
    // hook already depends on (height, mainH, etc.), so listing them
    // here would re-run the memo on a strictly redundant set of deps.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    samples,
    width,
    height,
    zoomX,
    guideAxisMax,
    pulseAxisMax,
    snrAxisMax,
    massAxisMax,
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
      .filter((e) => {
        const me = e as MouseEvent;
        if (me.type === "mousedown" && me.shiftKey) return false;
        if (me.ctrlKey || me.button) return false;
        const rect = svg.getBoundingClientRect();
        const x = me.clientX - rect.left;
        return x >= MARGIN.left && x <= MARGIN.left + innerW;
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

  function handleHover(svg: SVGSVGElement, clientX: number) {
    if (samples.length === 0) return;
    const rect = svg.getBoundingClientRect();
    const mx = clientX - rect.left;
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
    const sIdx = Math.max(0, Math.min(samples.length - 1, idx));
    const s = samples[sIdx];
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

  // ── Panel-divider drag-to-resize ──────────────────────────────────
  //
  // Each visible divider has an invisible hit area (ns-resize cursor)
  // overlaid above the SVG. Mousedown starts a drag; mousemove updates
  // the in-flight ``dragPanelHeights`` for smooth feedback; mouseup
  // commits the new height to settings. The PANEL ABOVE the divider
  // grows; other panels keep their current heights, so the chart
  // overall grows taller as the user drags down.
  const handleDividerMouseDown = (
    panelKey: PanelKey,
    currentHeight: number,
    minHeight: number,
  ) => (e: React.MouseEvent) => {
    e.preventDefault();
    dragRef.current = {
      panelKey,
      startMouseY: e.clientY,
      startHeight: currentHeight,
      minHeight,
      currentHeight,
    };
    const onMove = (ev: MouseEvent) => {
      const drag = dragRef.current;
      if (!drag) return;
      const dy = ev.clientY - drag.startMouseY;
      const next = Math.max(
        drag.minHeight,
        Math.min(PANEL_MAX_H, drag.startHeight + dy),
      );
      drag.currentHeight = next;
      setDragPanelHeights((prev) => ({ ...prev, [drag.panelKey]: next }));
    };
    const onUp = () => {
      const drag = dragRef.current;
      dragRef.current = null;
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
      if (!drag) return;
      setDragPanelHeights({});
      const next = {
        ...persistedPanelHeights,
        [drag.panelKey]: drag.currentHeight,
      };
      updateSettings({ phd2_panel_heights: next });
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

  // Keep refs to values the drag handlers below need at their latest
  // value — the onMove / onUp closures below capture these refs on
  // mousedown, so without the live sync they'd drift after any re-
  // render (wheel-zoom mid-drag, append-on-drag needing the fresh
  // array, etc.).
  const xScaleRef = useLatestRef(xScale);
  const selectionsRef = useLatestRef(selections);
  const exclusionsRef = useLatestRef(exclusions);

  const handleSelectionMouseDown = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!e.shiftKey) return;
    // Only honour the gesture when at least one of the change callbacks
    // is wired — avoids capturing events on charts rendered without
    // the selection wiring.
    const mode: "select" | "exclude" = e.altKey ? "exclude" : "select";
    if (mode === "select" && !onSelectionsChange) return;
    if (mode === "exclude" && !onExclusionsChange) return;

    const svg = e.currentTarget;
    const rect = svg.getBoundingClientRect();
    const mx0 = e.clientX - rect.left;
    if (mx0 < MARGIN.left || mx0 > MARGIN.left + innerW) return;
    const anchorTime = clamp(
      xScaleRef.current.invert(mx0),
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
      const t = clamp(xScaleRef.current.invert(mx), tmin, tmax);
      const lo = Math.min(drag.anchorTime, t);
      const hi = Math.max(drag.anchorTime, t);
      // Live preview — selection + exclusion both drive a pending
      // rect that renders until mouseup commits (or discards).
      if (drag.mode === "select") {
        setPendingSelection([lo, hi]);
      } else {
        setPendingExclusion([lo, hi]);
      }
    };
    const onUp = (ev: MouseEvent) => {
      const drag = selectionDragRef.current;
      if (!drag || !svgRef.current) {
        selectionDragRef.current = null;
        setPendingSelection(null);
        setPendingExclusion(null);
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup", onUp);
        return;
      }
      const r = svgRef.current.getBoundingClientRect();
      const mx = ev.clientX - r.left;
      const t = clamp(xScaleRef.current.invert(mx), tmin, tmax);
      const lo = Math.min(drag.anchorTime, t);
      const hi = Math.max(drag.anchorTime, t);
      // Tiny drag (< 0.25 s) → no-op. The × button per zone + the
      // "Clear all" toolbar button cover the removal flows; an
      // accidental click shouldn't wipe state.
      if (hi - lo >= 0.25) {
        if (drag.mode === "select") {
          onSelectionsChange?.([...selectionsRef.current, [lo, hi]]);
        } else {
          onExclusionsChange?.([...exclusionsRef.current, [lo, hi]]);
        }
      }
      setPendingSelection(null);
      setPendingExclusion(null);
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
    <Stack direction="row" alignItems="flex-start" spacing={0} sx={{ width: "100%" }}>
      {/* Per-panel collapse toggles — eye icons at the top-left of
          each non-main panel. Sits to the LEFT of the slider rail so
          the slider thumb area is unobstructed; always rendered
          (even when the panel is stubbed) so the user can always
          restore a hidden panel. */}
      <Box
        sx={{
          flexShrink: 0,
          width: 28,
          position: "relative",
          minHeight: `${toolbarHeight + TOOLTIP_H + effectiveSvgHeight}px`,
        }}
      >
        {(
          [
            { key: "snr" as const, y: snrY0 },
            { key: "mass" as const, y: massY0 },
          ] as const
        ).map(({ key, y }) => {
            const expanded = panelExpanded[key];
            const label = PANEL_LABEL[key];
            return (
              <IconButton
                key={`eye-${key}`}
                size="small"
                onClick={() =>
                  setPanelExpanded((prev) => ({ ...prev, [key]: !prev[key] }))
                }
                title={expanded ? `Collapse ${label}` : `Expand ${label}`}
                sx={{
                  position: "absolute",
                  left: 4,
                  top: toolbarHeight + TOOLTIP_H + y - 2,
                  p: 0.25,
                  color: "text.secondary",
                  "&:hover": { color: "text.primary" },
                }}
              >
                {expanded ? (
                  <VisibilityIcon sx={{ fontSize: 16 }} />
                ) : (
                  <VisibilityOffIcon sx={{ fontSize: 16 }} />
                )}
              </IconButton>
            );
          })}
      </Box>
      {/* Left axis-controls column — narrow rail holding the guide-
          axis slider plus the SNR / Mass sliders. The Guide unit
          (px / ″) toggle floats just inside the toolbar row above
          all three sliders. The column is intentionally narrow
          (40 px) so the chart SVG can occupy the rest of the
          horizontal space; ``spacing={0}`` on the outer Stack keeps
          the slider's right edge flush with the SVG's left margin. */}
      <Box
        sx={{
          flexShrink: 0,
          width: 40,
          position: "relative",
          minHeight: `${toolbarHeight + TOOLTIP_H + effectiveSvgHeight}px`,
        }}
      >
        <VerticalScaleSlider
          value={effectiveGuideMax}
          isAuto={guideAxisMax === null}
          min={0.1}
          max={10}
          step={0.01}
          onChange={(v) => setGuideAxisMax(v)}
          onReset={() => setGuideAxisMax(null)}
          formatValue={(px) => `±${formatGuidePx(px)} ${guideAxisUnitLabel}`}
          containerHeight={mainH}
          topOffset={toolbarHeight + TOOLTIP_H + mainY0}
        />
        {/* SNR / Mass sliders: slider value sets the axis upper
            bound; axis lower bound is locked at the data's auto-fit
            lo (so min values are always visible at the chart's
            bottom). Slider max = auto-fit hi (default — reproduces
            the existing tight auto-fit). Slider min is set so the
            bulk (median) can never disappear off the top of the
            panel even at maximum zoom: ``median + 20 % of the
            median-to-autoHi distance`` keeps the median visible at
            ~83 % of the panel height when fully zoomed in. Sliders
            hide entirely when their panel is collapsed — there's
            nothing meaningful to scale. */}
        {panelExpanded.snr && (
          <VerticalScaleSlider
            value={effectiveSnrMax}
            isAuto={snrAxisMax === null}
            min={snrMedian + Math.max(0.5, (snrHiAuto - snrMedian) * 0.2)}
            max={snrHiAuto}
            step={0.01}
            onChange={(v) => setSnrAxisMax(v)}
            onReset={() => setSnrAxisMax(null)}
            formatValue={(v) => `↑ ${v.toFixed(0)}`}
            containerHeight={snrH}
            topOffset={toolbarHeight + TOOLTIP_H + snrY0}
          />
        )}
        {panelExpanded.mass && (
          <VerticalScaleSlider
            value={effectiveMassMax}
            isAuto={massAxisMax === null}
            min={massMedian + Math.max(50, (massHiAuto - massMedian) * 0.2)}
            max={massHiAuto}
            step={0.01}
            onChange={(v) => setMassAxisMax(v)}
            onReset={() => setMassAxisMax(null)}
            formatValue={(v) => `↑ ${formatMassShort(v)}`}
            containerHeight={massH}
            topOffset={toolbarHeight + TOOLTIP_H + massY0}
          />
        )}
      </Box>

      <Box ref={wrapperRef} sx={{ flex: 1, minWidth: 0, position: "relative" }}>
        <Box ref={toolbarRef}>
        {/* Toolbar row 1 — Guide unit toggle + legend chips + hint */}
        <Stack direction="row" spacing={1} alignItems="center" sx={{ pb: 0.5 }} flexWrap="wrap" useFlexGap>
        <Stack
          direction="row"
          alignItems="center"
          spacing={0.75}
          sx={{ mr: 1 }}
        >
          <Tooltip
            title="Switch the guide-error y-axis between pixels and arcseconds. Arcseconds are absolute angular distance on the sky and let you compare across rigs; pixels are direct readouts of what the camera actually saw. The arcsec option is greyed out when the log doesn't include a pixel scale."
            arrow
          >
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ fontSize: 11, cursor: "help" }}
            >
              Guide unit
            </Typography>
          </Tooltip>
          <ToggleButtonGroup
            size="small"
            exclusive
            value={effectiveGuideUnit}
            disabled={!canUseArcsec && guideUnit === "px"}
            onChange={(_, v) => {
              if (v) setGuideUnit(v as "px" | "arcsec");
            }}
            sx={{
              "& .MuiToggleButton-root": {
                fontSize: 11,
                py: 0.125,
                px: 1.5,
                textTransform: "none",
                minWidth: 36,
              },
            }}
          >
            <ToggleButton value="px">px</ToggleButton>
            <ToggleButton value="arcsec" disabled={!canUseArcsec}>
              ″
            </ToggleButton>
          </ToggleButtonGroup>
        </Stack>
        <LegendToggle
          label="RA"
          color={COLOR_RA}
          shape="line"
          active={visibility.ra}
          onToggle={() => setVisibility((v) => ({ ...v, ra: !v.ra }))}
          tooltip="How far the guide star drifted left or right of the lock position before guiding corrected it. Lower is tighter."
        />
        <LegendToggle
          label="Dec"
          color={COLOR_DEC}
          shape="line"
          active={visibility.dec}
          onToggle={() => setVisibility((v) => ({ ...v, dec: !v.dec }))}
          tooltip="How far the guide star drifted up or down. Polar alignment dominates the long-term Dec drift; mechanical flexure shows up here too."
        />
        <LegendToggle
          label="RA pulse"
          color={COLOR_RA}
          shape="bar"
          active={visibility.raPulse}
          onToggle={() => setVisibility((v) => ({ ...v, raPulse: !v.raPulse }))}
          tooltip="How long PHD2 commanded the mount to slew east or west on each frame. Spikes mean the algorithm is working hard to catch up."
        />
        <LegendToggle
          label="Dec pulse"
          color={COLOR_DEC}
          shape="bar"
          active={visibility.decPulse}
          onToggle={() => setVisibility((v) => ({ ...v, decPulse: !v.decPulse }))}
          tooltip="How long PHD2 commanded the mount to slew north or south on each frame."
        />
        {events.some((e) => e.kind === "dither") && (
          <LegendToggle
            label="Dither"
            color={COLOR_RA}
            shape="triangle"
            active={visibility.dither}
            onToggle={() => setVisibility((v) => ({ ...v, dither: !v.dither }))}
            tooltip="Mark events where PHD2 deliberately shifted the lock position by a small random amount between sub-frames — used to spread sensor defects and make stacking more effective."
          />
        )}
        {events.some((e) => e.kind !== "dither" && e.time_seconds != null) && (
          <LegendToggle
            label="Events"
            color={mutedColor}
            shape="line"
            active={visibility.events}
            onToggle={() => setVisibility((v) => ({ ...v, events: !v.events }))}
            tooltip="Show non-dither markers — settle windows, lock-position changes, alerts, guiding pause / resume, etc. Hover or click an event marker for details."
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
          Scroll to zoom · drag to pan · shift-drag: include · shift+alt-drag: exclude
        </Typography>
      </Stack>

      {/* Action-button row — moved off the legend row so the wider
          set of toggle chips never collides with the action buttons
          even on narrow viewports. Reset X zoom sits on the right
          end, separated from the include / exclude / clear cluster
          by ``flex: 1`` so it reads as its own concern. */}
      <Stack
        direction="row"
        spacing={1}
        alignItems="center"
        sx={{ pb: 0.5 }}
        flexWrap="wrap"
        useFlexGap
      >
        <Tooltip title="Restore the full-section X-axis range.">
          <span>
            <Button
              size="small"
              startIcon={<RestartAltIcon />}
              onClick={handleReset}
              disabled={zoomX === null}
            >
              Reset X zoom
            </Button>
          </span>
        </Tooltip>
        <Tooltip title="Remove all selection and exclusion zones.">
          <span>
            <Button
              size="small"
              disabled={selections.length === 0 && exclusions.length === 0}
              onClick={() => {
                onSelectionsChange?.([]);
                onExclusionsChange?.([]);
              }}
            >
              Clear all selections
            </Button>
          </span>
        </Tooltip>
        <Box sx={{ flex: 1 }} />
        {onIncludeSettleChange && (
          <Tooltip title="When on, settle frames count toward stats. Off (default) excludes them.">
            <FormControlLabel
              control={
                <Switch
                  size="small"
                  checked={includeSettle ?? false}
                  onChange={(e) => onIncludeSettleChange(e.target.checked)}
                />
              }
              label={
                <Typography
                  variant="caption"
                  color="text.secondary"
                  sx={{ fontSize: 11 }}
                >
                  Include settle frames in stats
                </Typography>
              }
              sx={{ mr: 0.5, ml: 0 }}
            />
          </Tooltip>
        )}
      </Stack>
      </Box>{/* end toolbarRef */}

      {/* Tooltip reservation area — always present so the chart layout
          doesn't jump when the hover tooltip appears / disappears. */}
      <Box sx={{ position: "relative", height: TOOLTIP_H }}>
        {hover && (
          <Box
            sx={{
              position: "absolute",
              // Anchor top at the wrapper's origin (the toolbar's top
              // edge). The reservation Box sits below the toolbar, so
              // ``-toolbarHeight`` moves the tooltip UP to that
              // point and it extends downward from there — covering
              // the toolbar + the SVG's top-margin ornaments, but
              // never above the chart wrapper (which avoids getting
              // clipped by the outer Tabs container).
              top: `-${toolbarHeight}px`,
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
                {hover.raRaw == null ? "" : formatGuidePx(hover.raRaw)}
              </Box>
              <Box sx={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                {hover.decRaw == null ? "" : formatGuidePx(hover.decRaw)}
              </Box>
              <Box sx={{ opacity: 0.7 }}>{guideAxisUnitLabel}</Box>

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
              SNR: {hover.snr != null ? hover.snr.toFixed(1) : ""} · Mass:{" "}
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
        height={effectiveSvgHeight}
        onMouseMove={(e) => handleHover(e.currentTarget, e.clientX)}
        onMouseLeave={() => setHover(null)}
        onMouseDown={handleSelectionMouseDown}
        onTouchStart={(e) => { if (e.touches.length === 1) handleHover(e.currentTarget, e.touches[0].clientX); }}
        onTouchMove={(e) => { if (e.touches.length === 1) handleHover(e.currentTarget, e.touches[0].clientX); }}
        onTouchEnd={() => setHover(null)}
        style={{
          display: ready ? "block" : "none",
          cursor: zoomX ? "grab" : "crosshair",
          touchAction: "none",
          WebkitTouchCallout: "none",
          WebkitUserSelect: "none",
          userSelect: "none",
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

        {/* Uniform background tint on every panel so they read as a
            family — separates the plotted data area from the outer
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

        {/* Panel-divider lines — drag-to-resize handles. Each one
            sits centred in its gap; stretches nearly the full SVG
            width (with ~12 px padding on each side); coloured at a
            theme-aware divider tone so it reads as a structural
            separator rather than a chart axis. The bottom divider
            (below the Mass panel) lives just above the SVG's bottom
            edge, below the x-axis labels, and grows the Mass panel
            when dragged. The matching HTML hit areas sit above the
            SVG (rendered after </svg>) with cursor: ns-resize. */}
        {dividerLayout.map(({ key, y }) => (
          <line
            key={`panel-divider-${key}`}
            x1={12}
            x2={Math.max(12, width - 12)}
            y1={y}
            y2={y}
            stroke={theme.palette.divider}
            strokeWidth={1.25}
            opacity={0.85}
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
            guide-quality stats" (post-dither settle window). Same
            translucent grey across all three panels. */}
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

        {/* User-drawn selection bands (teal) + exclusion bands
            (hatched grey). Anchored in section-time so they stay put
            under zoom/pan. Each zone's bar is rendered inside the
            main-panel clipPath so it can't paint over the axis tick
            columns; the × close button that follows is rendered
            OUTSIDE the clipPath so it stays clickable even when the
            band is clipped. Committed bands render at lower opacity
            than the live-preview pending band so a drag-in-progress
            reads as the focused element. */}
        <ZoneBands
          keyPrefix="sel"
          clipId={clipMain}
          zones={selections}
          pending={pendingSelection}
          xScale={xScale}
          y={mainY0}
          height={mainH}
          fill={RIG_TEAL}
          committedFillOpacity={0.14}
          pendingFillOpacity={0.2}
          stroke={RIG_TEAL}
          committedStrokeOpacity={0.7}
          pendingStrokeOpacity={0.9}
          strokeDasharray="2 2"
        />
        <ZoneBands
          keyPrefix="excl"
          clipId={clipMain}
          zones={exclusions}
          pending={pendingExclusion}
          xScale={xScale}
          y={mainY0}
          height={mainH}
          fill={`url(#${excludePatternId})`}
          stroke={axisColor}
          committedStrokeOpacity={0.5}
          pendingStrokeOpacity={0.8}
          strokeDasharray="4 3"
        />

        {/* Per-zone × close buttons — rendered OUTSIDE the main clip
            so they remain visible (and clickable) even when the zone
            is partially clipped by zoom. Selection ×s sit at the top
            of the panel; exclusion ×s sit 16 px lower so the two
            don't collide when a selection and exclusion happen to
            share their right edge. */}
        {selections.map(([t0, t1], i) => (
          <ZoneCloseButton
            key={`sel-close-${i}`}
            cx={clamp(xScale(t1) - 9, MARGIN.left + 10, MARGIN.left + innerW - 10)}
            cy={mainY0 + 10}
            stroke={RIG_TEAL}
            bg={isDark ? "rgba(18,18,18,0.85)" : "rgba(255,255,255,0.9)"}
            onRemove={() =>
              onSelectionsChange?.(selections.filter((_, j) => j !== i))
            }
            title={`Remove selection ${i + 1} of ${selections.length} (${t0.toFixed(1)}s → ${t1.toFixed(1)}s)`}
          />
        ))}
        {exclusions.map(([t0, t1], i) => (
          <ZoneCloseButton
            key={`excl-close-${i}`}
            cx={clamp(xScale(t1) - 9, MARGIN.left + 10, MARGIN.left + innerW - 10)}
            cy={mainY0 + 26}
            stroke={axisColor}
            bg={isDark ? "rgba(18,18,18,0.85)" : "rgba(255,255,255,0.9)"}
            onRemove={() =>
              onExclusionsChange?.(exclusions.filter((_, j) => j !== i))
            }
            title={`Remove exclusion ${i + 1} of ${exclusions.length} (${t0.toFixed(1)}s → ${t1.toFixed(1)}s)`}
          />
        ))}

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
            x={MARGIN.left - 9}
            y={yDistScale(t)}
            fill={textColor}
            fontSize={10}
            textAnchor="end"
            dominantBaseline="central"
          >
            {formatGuidePx(t)}
          </text>
        ))}

        {/* Right-axis ticks (pulse duration, ms). Values rounded to
            integers — pulse durations are inherently integer ms, and
            the ``withDomainExtremes`` augmentation can surface floats
            from the auto-fit padding that would otherwise render
            "8269.8000" next to the tidy "2000" of the nice ticks. */}
        {pulseTicks.map((t) => (
          <text
            key={`pt-${t}`}
            x={MARGIN.left + innerW + 9}
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
        {panelExpanded.snr && (
          <>
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
                x={MARGIN.left - 9}
                y={ySnrScale(t)}
                fill={textColor}
                fontSize={9}
                textAnchor="end"
                dominantBaseline="central"
              >
                {/* Round to one decimal — avoids float-precision
                    garbage on domain extremes from ``withDomainExtremes``
                    and trims "16.908" to "16.9". */}
                {formatTenth(t)}
              </text>
            ))}
          </>
        )}
        {/* Mass panel */}
        {panelExpanded.mass && (
          <>
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
                x={MARGIN.left - 9}
                y={yMassScale(t)}
                fill={textColor}
                fontSize={9}
                textAnchor="end"
                dominantBaseline="central"
              >
                {formatMassTick(t)}
              </text>
            ))}
          </>
        )}

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
                y={massY0 + massH + 19}
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
          y={effectiveSvgHeight - 6}
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
            [10, mainY0 + mainH / 2, `Guide error (${guideAxisUnitLabel})`, 11, 1.0],
            [width - 14, mainY0 + mainH / 2, "Pulses (ms)", 11, 1.0],
            ...(panelExpanded.snr
              ? [[10, snrY0 + snrH / 2, "SNR", 10, 0.85] as const]
              : []),
            ...(panelExpanded.mass
              ? [[10, massY0 + massH / 2, "Mass (ADU)", 10, 0.85] as const]
              : []),
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

        {/* Stub labels — when a panel is collapsed, render the panel
            name centred in the stub strip so the user can see what
            they hid without expanding it again. */}
        {(
          [
            { key: "snr" as const, y: snrY0 },
            { key: "mass" as const, y: massY0 },
          ] as const
        )
          .filter(({ key }) => !panelExpanded[key])
          .map(({ key, y }) => (
            <text
              key={`stub-${key}`}
              x={MARGIN.left + 8}
              y={y + STUB_H / 2}
              fill={textColor}
              fillOpacity={0.65}
              fontSize={11}
              dominantBaseline="central"
              fontStyle="italic"
            >
              {PANEL_LABEL[key]}
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

      {/* Panel-divider drag handles — invisible 12 px tall hit areas
          aligned with each visible SVG divider line. Cursor changes
          to ns-resize on hover; click-drag grows the panel above.
          Heights are persisted per-user via the settings store; the
          minimum is the panel's ratio-derived default (Fred's
          requirement: never shrink below the layout default). */}
      {ready &&
        dividerLayout.map(({ key, y, currentHeight, minHeight }) => (
          <Tooltip
            key={`divider-handle-${key}`}
            title={`Drag down to make the ${PANEL_LABEL[key]} panel taller`}
            arrow
            placement="left"
          >
            <Box
              onMouseDown={handleDividerMouseDown(
                key,
                currentHeight,
                minHeight,
              )}
              sx={{
                position: "absolute",
                left: 12,
                right: 12,
                top: toolbarHeight + TOOLTIP_H + y - 6,
                height: 12,
                cursor: "ns-resize",
                zIndex: 5,
                "&:hover": {
                  bgcolor: "action.hover",
                  borderRadius: 0.5,
                },
              }}
            />
          </Tooltip>
        ))}

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
      {/* Right axis-controls column — pulse-axis slider, vertically
          aligned to the main panel only. Same 40 px width as the left
          rail so the chart SVG can claim the horizontal middle. */}
      <Box
        sx={{
          flexShrink: 0,
          width: 40,
          position: "relative",
          minHeight: `${toolbarHeight + TOOLTIP_H + effectiveSvgHeight}px`,
        }}
      >
        <VerticalScaleSlider
          value={effectivePulseMax}
          isAuto={pulseAxisMax === null}
          min={50}
          max={5000}
          step={0.01}
          onChange={(v) => setPulseAxisMax(v)}
          onReset={() => setPulseAxisMax(null)}
          formatValue={(ms) => `±${Math.round(ms)} ms`}
          containerHeight={mainH}
          topOffset={toolbarHeight + TOOLTIP_H + mainY0}
          tooltipSide="left"
        />
      </Box>
    </Stack>
  );
}

const TimeSeriesChart = forwardRef<TimeSeriesChartHandle, Props>(
  TimeSeriesChartInner,
);
export default TimeSeriesChart;

// ── Vertical scale slider ────────────────────────────────────────────────────

/** Vertical scale slider for the guide-axis (left) and pulse-axis
 *  (right) controls. Logarithmic mapping in slider-space so the
 *  span (0.1 → 10 px or 50 → 5000 ms) is well-distributed across
 *  the track instead of compressing the small end into a few pixels.
 *
 *  The slider's ``value`` is the ACTUAL scale (px / ms), not the
 *  log-position — MUI's ``scale`` prop interprets the slider's
 *  internal-position via the inverse log so the displayed value
 *  reads naturally. ``isAuto`` dims the slider to signal that the
 *  position came from the auto-fit logic; the first user drag
 *  promotes state from null → number and the dim treatment lifts.
 *
 *  Reset icon button next to the slider returns state to null
 *  (auto). Always present — the user can always recover auto
 *  behaviour without re-loading the section.
 */
function VerticalScaleSlider({
  value,
  isAuto,
  min,
  max,
  step,
  onChange,
  onReset,
  formatValue,
  containerHeight,
  topOffset,
  tooltipSide = "right",
}: {
  /** Current effective scale value (px or ms). When ``isAuto`` is
   *  true this comes from the auto-fit logic. */
  value: number;
  /** True when state is still null (auto-fit). Slider opacity dims
   *  to signal the user hasn't taken manual control yet. */
  isAuto: boolean;
  /** Domain bounds for the slider. */
  min: number;
  max: number;
  /** Slider step in slider-internal log-position units. */
  step: number;
  /** Called when the user drags. Receives the actual scale value
   *  (already inverse-log mapped). */
  onChange: (v: number) => void;
  /** Resets state to null (returns to auto-fit on the next render). */
  onReset: () => void;
  /** Format the live value for the slider's tooltip — applies the
   *  display unit (px or ″ for guide; ms for pulse). */
  formatValue: (v: number) => string;
  /** Height of the slider track in pixels — driven by the chart's
   *  main panel height so the slider visually flanks just that
   *  panel and not the SNR / Mass sub-panels below. */
  containerHeight: number;
  /** Offset from the column's top to the top of the slider track. */
  topOffset: number;
  /** Where the slider's value label pops out — ``"right"`` (default)
   *  is correct for left-rail sliders so the label tooltip extends
   *  toward the chart and never gets clipped by the left nav's
   *  overflow boundary. ``"left"`` for right-rail sliders does the
   *  same on the opposite side. */
  tooltipSide?: "left" | "right";
}) {
  const logMin = Math.log10(min);
  const logMax = Math.log10(max);
  const clamped = Math.min(max, Math.max(min, value));
  // Negate the log mapping so UP on the slider = SMALLER scale value
  // (= ZOOM IN, tighter axis). MUI's native direction is the opposite;
  // the negation propagates through min/max bounds, onChange, and
  // valueLabelFormat as inverse mappings.
  const sliderPosition = -Math.log10(clamped);
  const sliderMin = -logMax;
  const sliderMax = -logMin;

  // ``RESET_GAP`` is the breathing room between the slider's rail
  // bottom and the reset icon's top edge. ≥ 4 px so the reset never
  // looks like it's hugging the slider; 6 reads cleanly without
  // shoving the icon too far below the panel.
  const RESET_GAP = 6;

  return (
    <>
      <Box
        sx={{
          position: "absolute",
          // The slider Box is sized exactly to the panel. MUI's
          // default vertical padding is overridden via ``py: 0`` on
          // the Slider sx so the rail extends the full Box height —
          // the rail's top / bottom then land exactly on the
          // panel's top / bottom horizontal axis lines. The thumb
          // can stick out by half its diameter at the extremes;
          // that's an intentional visual signal that the slider
          // controls a value AT the axis edge.
          top: topOffset,
          left: 0,
          width: 40,
          height: containerHeight,
          display: "flex",
          justifyContent: "center",
          px: 0.5,
        }}
      >
        <Slider
          orientation="vertical"
          min={sliderMin}
          max={sliderMax}
          step={step}
          value={sliderPosition}
          onChange={(_, v) => onChange(Math.pow(10, -(v as number)))}
          onChangeCommitted={() => {
            // MUI's auto value-label stays visible while the thumb
            // retains focus, which after mouseup feels like a stuck
            // tooltip. Force blur on commit so the label dismisses
            // alongside the drag gesture ending.
            if (document.activeElement instanceof HTMLElement) {
              document.activeElement.blur();
            }
          }}
          valueLabelDisplay="auto"
          valueLabelFormat={(v) => formatValue(Math.pow(10, -v))}
          size="small"
          sx={{
            height: "100%",
            py: 0,
            opacity: isAuto ? 0.55 : 1,
            transition: "opacity 120ms ease",
            "& .MuiSlider-valueLabel": {
              fontSize: 10,
              padding: "2px 4px",
            },
            // Position override is scoped to ``.MuiSlider-valueLabelOpen``
            // so it only fires when the label is meant to be shown.
            // Targeting ``.MuiSlider-valueLabel`` directly would
            // overwrite MUI's default ``transform: scale(0)`` that
            // hides the label off-state, leaving the tooltip visible
            // on first load before any drag.
            ...(tooltipSide === "right" && {
              "& .MuiSlider-valueLabel.MuiSlider-valueLabelOpen": {
                right: "auto",
                left: "100%",
                transform: "translate(8px, -50%) scale(1)",
                transformOrigin: "left center",
              },
            }),
          }}
        />
      </Box>
      <Tooltip title={isAuto ? "Auto-fit (drag to lock)" : "Reset to auto-fit"}>
        <span
          style={{
            position: "absolute",
            top: topOffset + containerHeight + RESET_GAP,
            left: 0,
            width: 40,
            display: "flex",
            justifyContent: "center",
          }}
        >
          <IconButton
            size="small"
            onClick={onReset}
            disabled={isAuto}
            sx={{
              p: 0.25,
              opacity: isAuto ? 0.5 : 1,
            }}
          >
            <AutorenewIcon sx={{ fontSize: 14 }} />
          </IconButton>
        </span>
      </Tooltip>
    </>
  );
}

// ── Legend toggle ────────────────────────────────────────────────────────────

interface LegendToggleProps {
  label: string;
  color: string;
  shape: "line" | "bar" | "triangle";
  active: boolean;
  onToggle: () => void;
  /** Plain-language explanation of what the series represents. Renders
   *  on hover via MUI Tooltip; helps users who aren't fluent in PHD2
   *  jargon understand what each trace measures. */
  tooltip?: string;
}

/** Clickable legend chip — swatch + label. Clicking toggles the series
 *  on/off. The "off" state greys out the swatch and strikes through the
 *  label so users can see at a glance which series are hidden. */
function LegendToggle({
  label,
  color,
  shape,
  active,
  onToggle,
  tooltip,
}: LegendToggleProps) {
  const inner = (
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
  return tooltip ? (
    <Tooltip title={tooltip} arrow disableInteractive>
      {inner}
    </Tooltip>
  ) : (
    inner
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

/** Mirror a reactive value into a ref that the latest render always
 *  writes to. Read ``.current`` inside imperative handlers (e.g. drag
 *  ``mousemove`` / ``mouseup``) that were registered once but need to
 *  see the freshest React value instead of the one closed over at
 *  registration time. */
function useLatestRef<T>(value: T): React.MutableRefObject<T> {
  const ref = useRef(value);
  ref.current = value;
  return ref;
}

/** Renders the committed + pending rectangles for one user-drawn zone
 *  family (selections or exclusions). Styling differs between families
 *  but the geometry, clipPath wrapping, and committed-vs-pending
 *  opacity split are identical; this component owns that shared
 *  shape. Returns ``null`` when there's nothing to render so the
 *  parent SVG doesn't accumulate empty ``<g>`` nodes. */
function ZoneBands({
  keyPrefix,
  clipId,
  zones,
  pending,
  xScale,
  y,
  height,
  fill,
  committedFillOpacity,
  pendingFillOpacity,
  stroke,
  committedStrokeOpacity,
  pendingStrokeOpacity,
  strokeDasharray,
}: {
  keyPrefix: string;
  clipId: string;
  zones: Array<[number, number]>;
  pending: [number, number] | null;
  xScale: d3.ScaleLinear<number, number>;
  y: number;
  height: number;
  fill: string;
  /** Optional: set for the selection family (teal fill, ~15–20 % alpha).
   *  Leave undefined for the exclusion family — the hatched pattern
   *  already encodes its own alpha. */
  committedFillOpacity?: number;
  pendingFillOpacity?: number;
  stroke: string;
  committedStrokeOpacity: number;
  pendingStrokeOpacity: number;
  strokeDasharray: string;
}) {
  if (zones.length === 0 && !pending) return null;
  const renderRect = (
    range: [number, number],
    key: string,
    fillOpacity: number | undefined,
    strokeOpacity: number,
  ) => (
    <rect
      key={key}
      x={xScale(range[0])}
      y={y}
      width={Math.max(1, xScale(range[1]) - xScale(range[0]))}
      height={height}
      fill={fill}
      fillOpacity={fillOpacity}
      stroke={stroke}
      strokeOpacity={strokeOpacity}
      strokeWidth={1}
      strokeDasharray={strokeDasharray}
      pointerEvents="none"
    />
  );
  return (
    <g clipPath={`url(#${clipId})`}>
      {zones.map((range, i) =>
        renderRect(range, `${keyPrefix}-${i}`, committedFillOpacity, committedStrokeOpacity),
      )}
      {pending &&
        renderRect(pending, `${keyPrefix}-pending`, pendingFillOpacity, pendingStrokeOpacity)}
    </g>
  );
}

/** Small circular × close button anchored at ``(cx, cy)`` in SVG
 *  coords. Rendered outside the main-panel clipPath so it stays
 *  visible + clickable even when its owning zone is partially
 *  clipped. Used for both selection and exclusion zone removal. */
function ZoneCloseButton({
  cx,
  cy,
  stroke,
  bg,
  onRemove,
  title,
}: {
  cx: number;
  cy: number;
  stroke: string;
  bg: string;
  onRemove: () => void;
  title: string;
}) {
  return (
    <g
      onClick={(e) => {
        e.stopPropagation();
        onRemove();
      }}
      style={{ cursor: "pointer" }}
    >
      <title>{title}</title>
      <circle
        cx={cx}
        cy={cy}
        r={7}
        fill={bg}
        stroke={stroke}
        strokeOpacity={0.8}
        strokeWidth={1}
      />
      <text
        x={cx}
        y={cy}
        textAnchor="middle"
        dominantBaseline="central"
        fontSize={11}
        fontWeight={600}
        fill={stroke}
        pointerEvents="none"
      >
        ×
      </text>
    </g>
  );
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

/** Compact human-readable formatter for star-mass values. The full
 *  numbers run 5–7 digits and don't fit a slider tooltip cleanly;
 *  ``43k`` / ``1.2M`` / ``8.5M`` is the standard astrophotography
 *  abbreviation. Sub-1k values (rare — would only appear if the
 *  user pulled the slider all the way down) render in raw integer
 *  form. */
function formatMassShort(v: number): string {
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `${(v / 1_000).toFixed(0)}k`;
  return Math.round(v).toString();
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
