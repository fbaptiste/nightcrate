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

/** The current observing night (`YYYY-MM-DD`) in the given IANA timezone.
 * Before local noon this returns the previous calendar date; at noon it
 * advances to today. Calendar-day rollback (rather than subtracting 12
 * elapsed hours) keeps this aligned with the backend across DST changes. */
export function tonightDate(timezone: string): string {
  const now = new Date();
  let date = calendarDate(now, timezone);
  let hour: number;
  try {
    const hourPart = new Intl.DateTimeFormat("en-US", {
      timeZone: timezone,
      hour: "2-digit",
      hourCycle: "h23",
    }).formatToParts(now).find((part) => part.type === "hour")?.value;
    hour = Number.parseInt(hourPart ?? "", 10);
    if (!Number.isFinite(hour)) throw new Error("Missing hour");
  } catch {
    hour = now.getHours();
  }
  if (hour < 12) {
    const [year, month, day] = date.split("-").map(Number);
    const previous = new Date(Date.UTC(year!, month! - 1, day! - 1));
    date = previous.toISOString().slice(0, 10);
  }
  return date;
}
