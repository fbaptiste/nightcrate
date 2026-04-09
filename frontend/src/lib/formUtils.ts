/** Parse a form input string to a float, returning null for empty/invalid values. */
export function parseOptionalFloat(val: string): number | null {
  const n = parseFloat(val);
  return val.trim() !== "" && !isNaN(n) ? n : null;
}

/** Parse a form input string to an integer, returning null for empty/invalid values. */
export function parseOptionalInt(val: string): number | null {
  const n = parseInt(val, 10);
  return val.trim() !== "" && !isNaN(n) ? n : null;
}

/** Format a snake_case name for display (e.g., "plate_solving" → "Plate Solving"). */
export function formatSnakeCase(name: string): string {
  return name
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}
