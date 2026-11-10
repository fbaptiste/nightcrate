const MONTH = new Intl.DateTimeFormat("en-US", { month: "short", timeZone: "UTC" });

function parseDate(value: string): Date {
  const [year, month, day] = value.slice(0, 10).split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day, 12));
}

export function formatDateRange(first: string | null, last: string | null): string {
  if (!first || !last) return "No dates";
  const start = parseDate(first);
  const end = parseDate(last);
  const startMonth = MONTH.format(start);
  const endMonth = MONTH.format(end);
  const startYear = start.getUTCFullYear();
  const endYear = end.getUTCFullYear();
  if (first.slice(0, 10) === last.slice(0, 10)) {
    return `${startMonth} ${start.getUTCDate()}, ${startYear}`;
  }
  if (startYear === endYear && start.getUTCMonth() === end.getUTCMonth()) {
    return `${startMonth} ${start.getUTCDate()} – ${end.getUTCDate()}, ${startYear}`;
  }
  if (startYear === endYear) return `${startMonth}–${endMonth} ${startYear}`;
  return `${startMonth} ${startYear} – ${endMonth} ${endYear}`;
}

export function formatField(majorDeg: number, minorDeg: number): string {
  if (majorDeg >= 1) return `${majorDeg.toFixed(1)}° × ${minorDeg.toFixed(1)}°`;
  return `${Math.round(majorDeg * 60)}′ × ${Math.round(minorDeg * 60)}′`;
}
