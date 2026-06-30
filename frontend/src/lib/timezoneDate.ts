/**
 * Date helpers that resolve a calendar date in a specific IANA timezone —
 * used to anchor "today / tonight" to the *location's* timezone rather than
 * the browser's, so the planner and the Tonight calculator agree on what
 * night it is regardless of where the user's machine is.
 */

/** Today's date (`YYYY-MM-DD`) in the given IANA timezone. Falls back to the
 *  browser-local date if the timezone is unknown to `Intl`. */
export function todayInTimezone(timezone: string): string {
  try {
    const parts = new Intl.DateTimeFormat("en-CA", {
      timeZone: timezone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).formatToParts(new Date());
    const y = parts.find((p) => p.type === "year")?.value ?? "";
    const m = parts.find((p) => p.type === "month")?.value ?? "";
    const d = parts.find((p) => p.type === "day")?.value ?? "";
    if (y && m && d) return `${y}-${m}-${d}`;
  } catch {
    // fall through
  }
  const now = new Date();
  const pad = (n: number) => (n < 10 ? `0${n}` : String(n));
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}
