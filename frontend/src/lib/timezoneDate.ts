/**
 * Date helpers that resolve a calendar date in a specific IANA timezone —
 * used to anchor "today / tonight" to the *location's* timezone rather than
 * the browser's, so the planner and the Tonight calculator agree on what
 * night it is regardless of where the user's machine is.
 */

/** Format an instant's calendar date (`YYYY-MM-DD`) in the given IANA
 *  timezone. Falls back to the browser-local date if the timezone is
 *  unknown to `Intl`. */
function calendarDate(instant: Date, timezone: string): string {
  try {
    const parts = new Intl.DateTimeFormat("en-CA", {
      timeZone: timezone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).formatToParts(instant);
    const y = parts.find((p) => p.type === "year")?.value ?? "";
    const m = parts.find((p) => p.type === "month")?.value ?? "";
    const d = parts.find((p) => p.type === "day")?.value ?? "";
    if (y && m && d) return `${y}-${m}-${d}`;
  } catch {
    // fall through
  }
  const pad = (n: number) => (n < 10 ? `0${n}` : String(n));
  return `${instant.getFullYear()}-${pad(instant.getMonth() + 1)}-${pad(instant.getDate())}`;
}

/** Today's date (`YYYY-MM-DD`) in the given IANA timezone — the plain
 *  calendar date with no observing-night rollback. */
export function todayInTimezone(timezone: string): string {
  return calendarDate(new Date(), timezone);
}

/** The current observing night (`YYYY-MM-DD`) in the given IANA timezone:
 *  the location-tz calendar date rolled back 12 h, so "tonight" stays put
 *  until local noon. Mirrors the backend's `tonight_date` (the single
 *  source of truth for "what night is it"). Use THIS — not
 *  `todayInTimezone` — anywhere the value must agree with a planner /
 *  visibility computation, or the display and the computed night drift
 *  apart in the local-midnight-to-noon window. */
export function tonightDate(timezone: string): string {
  return calendarDate(new Date(Date.now() - 12 * 60 * 60 * 1000), timezone);
}
