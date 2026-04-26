/**
 * Client-side port of the backend PHD2 section-metrics math.
 *
 * Mirrors ``compute_section_metrics`` in
 * ``backend/src/nightcrate/services/phd2_metrics.py``. Used by the
 * Section Summary AND Viewport Summary panels so the page-level
 * "Include settle in stats" toggle and shift-drag selection /
 * exclusion can recompute without a backend round-trip.
 *
 * Formulas:
 *   - RMS = population standard deviation.
 *   - RA drift = ``(ra_last − ra_first − Σ ra_guide) / Δt`` × 60.
 *   - Dec drift = LS slope of unguided-frames-only y_accum × 60.
 *   - PA error = ``3.8197 · |drift_dec| · pixel_scale / cos(δ)``.
 *   - Peak = sign-preserving max-by-absolute-value.
 *   - Oscillation = sign-flip rate; zero values treated as positive.
 *
 * Distances stay in pixels; ``arcsec_scale`` is surfaced on the
 * returned metrics so ``StatsPanel`` renders dual-unit labels the
 * same way as for the section-wide metrics.
 *
 * Settle-window exclusion (default behaviour): samples inside
 * ``settle_begin`` / ``settle_end`` event pairs are excluded from
 * every quality metric so dither-settle excursions don't get
 * counted as guiding errors. ``frame_count_total`` and
 * ``duration_total_seconds`` stay unfiltered so the UI can render
 * the "N total · M in stats · K in settle" decomposition.
 */
import type { GuidingSample, LogEvent, SectionMetrics } from "@/api/phd2";

export interface ComputeGuidingMetricsOptions {
  /** When ``true``, disable the settle-window filter so metrics match
   *  the pre-v0.22.0 "include everything" behaviour.
   *  ``frame_count_in_settle`` is still reported so the UI can show
   *  "X frames would have been excluded" even in include mode. */
  includeSettle?: boolean;
  /** Section header's declination in degrees, used by the PA-error
   *  formula. ``null`` when the header didn't declare one — PA error
   *  resolves to ``null`` in that case. */
  declinationDeg?: number | null;
}

export function computeGuidingMetrics(
  samples: GuidingSample[],
  events: LogEvent[],
  arcsecScale: number | null,
  options: ComputeGuidingMetricsOptions = {},
): SectionMetrics {
  const includeSettle = options.includeSettle ?? false;
  const declinationDeg = options.declinationDeg ?? null;

  const fallbackEndT =
    samples.length > 0 ? samples[samples.length - 1].time_seconds : 0;
  const intervals = computeSettleIntervals(events, fallbackEndT);

  // Partition: in-settle vs candidates for stats. When ``includeSettle``
  // is true, every sample is a stats candidate but ``inSettleCount`` still
  // gets computed so the UI can show "X frames in settle" regardless.
  let inSettleCount = 0;
  const statsSamples: GuidingSample[] = [];
  for (const s of samples) {
    const inSettle = inAnyInterval(s.time_seconds, intervals);
    if (inSettle) inSettleCount += 1;
    if (includeSettle || !inSettle) statsSamples.push(s);
  }

  const raRaw = statsSamples
    .map((s) => s.ra_raw_px)
    .filter((v): v is number => v !== null);
  const decRaw = statsSamples
    .map((s) => s.dec_raw_px)
    .filter((v): v is number => v !== null);
  const snrs = statsSamples
    .map((s) => s.snr)
    .filter((v): v is number => v !== null);
  const masses = statsSamples
    .map((s) => s.star_mass)
    .filter((v): v is number => v !== null);

  const rmsRa = stddev(raRaw);
  const rmsDec = stddev(decRaw);
  const rmsTotal =
    rmsRa !== null && rmsDec !== null
      ? Math.sqrt(rmsRa * rmsRa + rmsDec * rmsDec)
      : null;

  const peakRa = signedPeak(raRaw);
  const peakDec = signedPeak(decRaw);

  const driftRa = raDriftCorrectionsSubtracted(statsSamples);
  const driftDec = decDriftUnguidedOnly(statsSamples);
  const paArcmin = polarAlignmentErrorArcmin(driftDec, declinationDeg, arcsecScale);

  const oscRa = oscillationRate(raRaw);
  const oscDec = oscillationRate(decRaw);
  const elong = elongation(statsSamples);

  const durationTotal =
    samples.length >= 2
      ? samples[samples.length - 1].time_seconds - samples[0].time_seconds
      : 0;
  const durationIncluded = computeDurationIncluded(samples, intervals);

  return {
    rms_ra_px: rmsRa,
    rms_dec_px: rmsDec,
    rms_total_px: rmsTotal,
    peak_ra_px: peakRa,
    peak_dec_px: peakDec,
    drift_ra_px_per_min: driftRa,
    drift_dec_px_per_min: driftDec,
    polar_alignment_error_arcmin: paArcmin,
    oscillation_ra: oscRa,
    oscillation_dec: oscDec,
    elongation: elong,
    frame_count_total: samples.length,
    frame_count_error: statsSamples.reduce(
      (n, s) => (s.error_code !== 0 ? n + 1 : n),
      0,
    ),
    frame_count_in_settle: inSettleCount,
    // Samples that actually had positional data AND made it into the
    // stats pool. Matches backend ``frame_count_in_stats`` semantics.
    frame_count_in_stats: raRaw.length,
    duration_total_seconds: durationTotal,
    duration_included_seconds: durationIncluded,
    mean_snr: snrs.length ? sum(snrs) / snrs.length : null,
    median_snr: snrs.length ? median(snrs) : null,
    mean_star_mass: masses.length ? sum(masses) / masses.length : null,
    arcsec_scale: arcsecScale,
  };
}

/**
 * Derive closed settle intervals from a section's INFO events.
 *
 * State-machine over sorted ``settle_begin`` / ``settle_end`` events.
 * Mirrors the backend algorithm in ``_settle_intervals`` — keep in sync.
 *
 * Edge cases:
 * - ``time_seconds == null`` on a begin → anchor at 0 (section start).
 * - ``time_seconds == null`` on an end → skip (can't anchor a close).
 * - Duplicate begin while open → ignore.
 * - Lone end (section opened mid-settle) → emit ``[0, t]``.
 * - Unclosed begin at walk end → close at ``fallbackEndT``.
 */
export function computeSettleIntervals(
  events: LogEvent[],
  fallbackEndT: number,
): Array<[number, number]> {
  const relevant: Array<[number, "settle_begin" | "settle_end"]> = [];
  for (const e of events) {
    if (e.kind !== "settle_begin" && e.kind !== "settle_end") continue;
    if (e.time_seconds === null || e.time_seconds === undefined) {
      if (e.kind === "settle_begin") relevant.push([0, "settle_begin"]);
      continue;
    }
    relevant.push([e.time_seconds, e.kind]);
  }
  relevant.sort((a, b) => a[0] - b[0]);

  const intervals: Array<[number, number]> = [];
  let openStart: number | null = null;
  for (const [t, kind] of relevant) {
    if (kind === "settle_begin") {
      if (openStart === null) openStart = t;
      // Duplicate begin while open — ignore.
      continue;
    }
    // settle_end
    if (openStart !== null) {
      intervals.push([openStart, t]);
      openStart = null;
    } else {
      intervals.push([0, t]);
    }
  }
  if (openStart !== null) {
    intervals.push([openStart, fallbackEndT]);
  }
  return intervals;
}

function inAnyInterval(t: number, intervals: Array<[number, number]>): boolean {
  for (const [t0, t1] of intervals) {
    if (t0 <= t && t <= t1) return true;
  }
  return false;
}

function sum(values: number[]): number {
  let s = 0;
  for (const v of values) s += v;
  return s;
}

/** Population standard deviation: ``sqrt(mean((x − x̄)²))``, NOT
 *  ``sqrt(mean(x²))``. Returns null on empty input; for a single
 *  value returns 0. */
function stddev(values: number[]): number | null {
  if (values.length === 0) return null;
  const mean = sum(values) / values.length;
  let acc = 0;
  for (const v of values) {
    const d = v - mean;
    acc += d * d;
  }
  return Math.sqrt(acc / values.length);
}

/** Sign-preserving max-by-absolute-value (§5.2.2). For [+0.3, -0.5,
 *  +0.4], returns -0.5. Null on empty input. */
function signedPeak(values: number[]): number | null {
  if (values.length === 0) return null;
  let best = values[0];
  for (let i = 1; i < values.length; i++) {
    if (Math.abs(values[i]) > Math.abs(best)) best = values[i];
  }
  return best;
}

function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = sorted.length >>> 1;
  return sorted.length % 2 === 0
    ? (sorted[mid - 1] + sorted[mid]) / 2
    : sorted[mid];
}

/** Fraction of consecutive value pairs whose signs differ. **Zero
 *  values count as positive**. Returns null when fewer than two
 *  values. */
function oscillationRate(values: number[]): number | null {
  if (values.length < 2) return null;
  let flips = 0;
  let prevSign = values[0] >= 0 ? 1 : -1;
  for (let i = 1; i < values.length; i++) {
    const sign = values[i] >= 0 ? 1 : -1;
    if (sign !== prevSign) flips += 1;
    prevSign = sign;
  }
  return flips / (values.length - 1);
}

/** RA drift in px / minute via the corrections-subtraction algorithm:
 *  total raw RA change minus total RA guide correction over the
 *  section duration. The Σ runs over all settle-filtered samples
 *  with ``ra_duration_ms != 0`` and a non-null ``ra_guide_px``. */
function raDriftCorrectionsSubtracted(
  statsSamples: GuidingSample[],
): number | null {
  const valid = statsSamples.filter(
    (s): s is GuidingSample & { ra_raw_px: number } => s.ra_raw_px !== null,
  );
  if (valid.length < 2) return null;
  const first = valid[0];
  const last = valid[valid.length - 1];
  const dt = last.time_seconds - first.time_seconds;
  if (dt <= 0) return null;
  let sumRaguide = 0;
  for (const s of statsSamples) {
    if (s.ra_duration_ms === null || s.ra_duration_ms === 0) continue;
    if (s.ra_guide_px === null) continue;
    sumRaguide += s.ra_guide_px;
  }
  const driftPerSec = (last.ra_raw_px - first.ra_raw_px - sumRaguide) / dt;
  return driftPerSec * 60;
}

/** Dec drift in px / minute via the unguided-frames-only
 *  accumulation algorithm. Position changes accumulate only when
 *  the previous frame was unguided (``dec_duration_ms == 0``); the
 *  slope of ``y_accum vs t`` is the drift rate. Bypasses the
 *  asymmetric-Dec-correction problem that breaks the RA algorithm
 *  for Dec. */
function decDriftUnguidedOnly(
  statsSamples: GuidingSample[],
): number | null {
  const valid = statsSamples.filter(
    (s): s is GuidingSample & { dec_raw_px: number } => s.dec_raw_px !== null,
  );
  if (valid.length < 2) return null;

  const first = valid[0];
  let n = 1;
  let sumX = first.time_seconds;
  let sumY = 0;
  let sumXX = first.time_seconds * first.time_seconds;
  let sumXY = 0;

  let yAccum = 0;
  let prevY = first.dec_raw_px;
  let prevGuided =
    first.dec_duration_ms !== null && first.dec_duration_ms !== 0;

  for (let i = 1; i < valid.length; i++) {
    const s = valid[i];
    if (!prevGuided) {
      yAccum += s.dec_raw_px - prevY;
      n += 1;
      sumX += s.time_seconds;
      sumY += yAccum;
      sumXX += s.time_seconds * s.time_seconds;
      sumXY += s.time_seconds * yAccum;
    }
    prevY = s.dec_raw_px;
    prevGuided = s.dec_duration_ms !== null && s.dec_duration_ms !== 0;
  }

  if (n < 2) return 0; // all-guided — no unguided drift to estimate
  const meanX = sumX / n;
  const denom = sumXX - n * meanX * meanX;
  if (denom === 0) return 0;
  const meanY = sumY / n;
  const numer = sumXY - n * meanX * meanY;
  return (numer / denom) * 60;
}

/** Scatter-ellipse elongation. Computes ``|lx − ly| / (lx + ly)``
 *  over the rotated mount-axis frame (raraw/decraw, centred on
 *  per-axis means; rotation ``θ = atan2(cov_xy, var_x)``). Range
 *  [0, 1]: 0 = circular, 1 = degenerate line (or near-zero
 *  dispersion — defensive 1.0). Null when fewer than two samples
 *  have both axes populated. */
function elongation(statsSamples: GuidingSample[]): number | null {
  const pairs: Array<[number, number]> = [];
  for (const s of statsSamples) {
    if (s.ra_raw_px === null || s.dec_raw_px === null) continue;
    pairs.push([s.ra_raw_px, s.dec_raw_px]);
  }
  if (pairs.length < 2) return null;
  const n = pairs.length;
  let sx = 0;
  let sy = 0;
  for (const [x, y] of pairs) {
    sx += x;
    sy += y;
  }
  const mx = sx / n;
  const my = sy / n;
  let vxx = 0;
  let vyy = 0;
  let vxy = 0;
  for (const [x, y] of pairs) {
    const dx = x - mx;
    const dy = y - my;
    vxx += dx * dx;
    vyy += dy * dy;
    vxy += dx * dy;
  }
  vxx /= n;
  vyy /= n;
  vxy /= n;
  const theta = Math.atan2(vxy, vxx);
  const cost = Math.cos(theta);
  const sint = Math.sin(theta);
  let rotVx = 0;
  let rotVy = 0;
  for (const [x, y] of pairs) {
    const dx = x - mx;
    const dy = y - my;
    const xr = dx * cost + dy * sint;
    const yr = dy * cost - dx * sint;
    rotVx += xr * xr;
    rotVy += yr * yr;
  }
  rotVx /= n;
  rotVy /= n;
  const lx = Math.sqrt(Math.max(0, rotVx));
  const ly = Math.sqrt(Math.max(0, rotVy));
  if (lx + ly < 1e-6) return 1;
  return Math.abs(lx - ly) / (lx + ly);
}

/** Polar alignment error in arcminutes — Barrett's formula:
 *  α = 3.8197 · |drift| · pixel_scale / cos(δ). Returns null when
 *  any input is missing or near the celestial pole where the
 *  formula diverges. */
function polarAlignmentErrorArcmin(
  driftDecPxPerMin: number | null,
  declinationDeg: number | null,
  pixelScale: number | null,
): number | null {
  if (
    driftDecPxPerMin === null ||
    declinationDeg === null ||
    pixelScale === null
  ) {
    return null;
  }
  const cosDec = Math.cos((declinationDeg * Math.PI) / 180);
  if (Math.abs(cosDec) < 1e-6) return null;
  return (3.8197 * Math.abs(driftDecPxPerMin) * pixelScale) / cosDec;
}

/** Sum of inter-frame intervals where both endpoints are outside
 *  every settle window (§5.2.8 ``duration_included``). The "active"
 *  duration a user looks at when asking "how long was I actually
 *  guiding?". */
function computeDurationIncluded(
  samples: GuidingSample[],
  intervals: Array<[number, number]>,
): number {
  if (samples.length < 2) return 0;
  let total = 0;
  let prev = samples[0];
  let prevInStats = !inAnyInterval(prev.time_seconds, intervals);
  for (let i = 1; i < samples.length; i++) {
    const s = samples[i];
    const inStats = !inAnyInterval(s.time_seconds, intervals);
    if (prevInStats && inStats) {
      total += s.time_seconds - prev.time_seconds;
    }
    prev = s;
    prevInStats = inStats;
  }
  return total;
}
