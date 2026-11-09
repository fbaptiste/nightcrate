const setupDateFormatter = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
  timeZone: "UTC",
});

export function setupLabel(untilAt: string | null | undefined): string {
  if (untilAt === undefined) return "—";
  return untilAt
    ? `Until ${setupDateFormatter.format(new Date(`${untilAt.slice(0, 10)}T00:00:00Z`))}`
    : "Now";
}
