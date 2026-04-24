/**
 * Client-side port of the backend PHD2 section-metrics math.
 *
 * Mirrors ``compute_section_metrics`` in
 * ``backend/src/nightcrate/services/phd2_metrics.py`` for the guiding
 * case. Used by the Section Summary AND Viewport Summary panels so the
 * page-level "Include settle in stats" toggle can flip both without a
 * backend round-trip.
 *
 * Distances stay in pixels; the ``arcsec_scale`` is surfaced on the
 * returned ``SectionMetrics`` so ``StatsPanel`` renders the dual-unit
 * labels the same way as for the section-wide metrics.
 *
 * Settle-window exclusion (PHD2 / PHDLogViewer convention):
 *   Samples inside ``settle_begin`` / ``settle_end`` event pairs are
 *   excluded from every quality metric — RMS, peak, SNR, star mass,
 *   and the error count — because large dither-settle excursions
 *   should not be counted as guiding errors. ``frame_count_total`` and
 *   ``duration_seconds`` stay unfiltered so the UI can render the
 *   "N total · M in stats · K in settle" decomposition.
 */
import type { GuidingSample, LogEvent, SectionMetrics } from "@/api/phd2";

export interface ComputeGuidingMetricsOptions {
  /** When ``true``, disable the settle-window filter so metrics match
   *  the pre-v0.22.0 "include everything" behaviour. ``frame_count_in_settle``
   *  is still reported so the UI can show "X frames would have been
   *  excluded" even in include mode. Default ``false`` — matches PHD2
   *  and PHDLogViewer. */
  includeSettle?: boolean;
}

export function computeGuidingMetrics(
  samples: GuidingSample[],
  events: LogEvent[],
  arcsecScale: number | null,
  options: ComputeGuidingMetricsOptions = {},
): SectionMetrics {
  const includeSettle = options.includeSettle ?? false;

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

  const rmsRa = rms(raRaw);
  const rmsDec = rms(decRaw);
  const rmsTotal =
    rmsRa !== null && rmsDec !== null
      ? Math.sqrt(rmsRa * rmsRa + rmsDec * rmsDec)
      : null;

  const peakRa = raRaw.length
    ? raRaw.reduce((m, v) => Math.max(m, Math.abs(v)), 0)
    : null;
  const peakDec = decRaw.length
    ? decRaw.reduce((m, v) => Math.max(m, Math.abs(v)), 0)
    : null;

  // Drift + oscillation on the same stats-sample subset as RMS/peak.
  // Pairs are (time_seconds, value) — nulls filtered out per axis.
  const raPairs: Array<[number, number]> = [];
  const decPairs: Array<[number, number]> = [];
  for (const s of statsSamples) {
    if (s.ra_raw_px !== null) raPairs.push([s.time_seconds, s.ra_raw_px]);
    if (s.dec_raw_px !== null) decPairs.push([s.time_seconds, s.dec_raw_px]);
  }
  const driftRa = slopePerMinute(raPairs);
  const driftDec = slopePerMinute(decPairs);
  const oscRa = oscillationRate(raRaw);
  const oscDec = oscillationRate(decRaw);

  const duration =
    samples.length >= 2
      ? samples[samples.length - 1].time_seconds - samples[0].time_seconds
      : 0;

  return {
    rms_ra_px: rmsRa,
    rms_dec_px: rmsDec,
    rms_total_px: rmsTotal,
    peak_ra_px: peakRa,
    peak_dec_px: peakDec,
    drift_ra_px_per_min: driftRa,
    drift_dec_px_per_min: driftDec,
    oscillation_ra: oscRa,
    oscillation_dec: oscDec,
    frame_count_total: samples.length,
    frame_count_error: statsSamples.reduce(
      (n, s) => (s.error_code !== 0 ? n + 1 : n),
      0,
    ),
    frame_count_in_settle: inSettleCount,
    // Samples that actually had positional data AND made it into the
    // stats pool. Matches backend ``frame_count_in_stats`` semantics.
    frame_count_in_stats: raRaw.length,
    duration_seconds: duration,
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

function rms(values: number[]): number | null {
  if (values.length === 0) return null;
  let s = 0;
  for (const v of values) s += v * v;
  return Math.sqrt(s / values.length);
}

function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = sorted.length >>> 1;
  return sorted.length % 2 === 0
    ? (sorted[mid - 1] + sorted[mid]) / 2
    : sorted[mid];
}

/** Least-squares slope of value vs time in units per MINUTE. Mirrors
 *  the backend ``_slope_per_minute`` helper. Returns null on <2 pairs
 *  or when all x values are identical. */
function slopePerMinute(pairs: Array<[number, number]>): number | null {
  if (pairs.length < 2) return null;
  let sx = 0;
  let sy = 0;
  for (const [x, y] of pairs) {
    sx += x;
    sy += y;
  }
  const mx = sx / pairs.length;
  const my = sy / pairs.length;
  let num = 0;
  let den = 0;
  for (const [x, y] of pairs) {
    const dx = x - mx;
    num += dx * (y - my);
    den += dx * dx;
  }
  if (den === 0) return null;
  return (num / den) * 60;
}

/** Fraction of consecutive value pairs whose signs differ. Zero-valued
 *  samples are skipped (no sign). Returns null when fewer than two
 *  non-zero values exist. */
function oscillationRate(values: number[]): number | null {
  const nonZero = values.filter((v) => v !== 0);
  if (nonZero.length < 2) return null;
  let flips = 0;
  for (let i = 1; i < nonZero.length; i++) {
    if (nonZero[i - 1] > 0 !== nonZero[i] > 0) flips += 1;
  }
  return flips / (nonZero.length - 1);
}
