/** The user's local calendar date of an ISO timestamp, as YYYY-MM-DD.
 *
 * Returns null for a missing value or anything that is not a timestamp, such
 * as a release tag like "v20260501". Catalog fetch times are stored in UTC, so
 * slicing the string would show tomorrow's date on an American evening.
 */
export function formatLocalDate(value: string | null | undefined): string | null {
  if (!value || !/^\d{4}-\d{2}-\d{2}T/.test(value)) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

const nightFormatter = new Intl.DateTimeFormat("en-GB", {
  weekday: "short",
  day: "numeric",
  month: "short",
  year: "numeric",
  timeZone: "UTC",
});

/** Format an observing-night date without letting the browser's zone move it. */
export function formatNight(date: string): string {
  return nightFormatter
    .format(new Date(`${date.slice(0, 10)}T00:00:00Z`))
    .replace(/,/g, "");
}
