/**
 * Shared formatters for PHD2 guide-log data.
 *
 * PHD2 logs contain naive local-time timestamps (no timezone suffix) on
 * section headers, plus elapsed-seconds offsets per sample. Combining
 * the two gives the wall-clock time of each sample / event.
 *
 * JavaScript's ``new Date("2026-03-07T19:38:23")`` parses naive ISO
 * strings as LOCAL time (per ES2015+), which matches PHD2's convention
 * of machine-local times — so no extra timezone handling is needed.
 */

/** Wall-clock time of a sample or event as "HH:MM:SS" (24-hour, local).
 *
 *  ``startIso`` is the section's ``start_time`` from the parser;
 *  ``elapsedSec`` is the per-sample/event offset. When a session spans
 *  midnight the clock wraps naturally — the Time(s) column is the
 *  unambiguous ordering key. */
export function formatWallClock(startIso: string, elapsedSec: number): string {
  const start = new Date(startIso);
  if (Number.isNaN(start.getTime())) return "—";
  const dt = new Date(start.getTime() + elapsedSec * 1000);
  const h = String(dt.getHours()).padStart(2, "0");
  const m = String(dt.getMinutes()).padStart(2, "0");
  const s = String(dt.getSeconds()).padStart(2, "0");
  return `${h}:${m}:${s}`;
}
