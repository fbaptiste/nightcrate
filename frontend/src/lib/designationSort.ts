const PREFIX_RE = /^([A-Za-z]+(?:2(?=[\s-]|\d))?)/;
const NUMBER_RE = /\d+/g;

// Parsed by the backend parity test so both implementations share edge cases.
export const DESIGNATION_SORT_VECTORS = [
  ["NGC 2", "NGC 10"],
  ["M 31", "Mel 1"],
  ["Sh2-2", "Sh2-155"],
  ["ESO 107-2", "ESO 107-010"],
  ["NGC 1", "NGC 1A"],
  ["PGC 99999999999999999999", "PGC 100000000000000000000"]
] as const;

/** Mirror of backend services/dso_sorting.py for client-side DSO lists. */
export function designationSortKey(value: string): string {
  const normalized = value.trim().toLocaleLowerCase("en-US");
  const match = normalized.match(PREFIX_RE);
  const prefix = match?.[1] ?? "";
  const rest = match ? normalized.slice(match[0].length) : normalized;
  const numbers = [...rest.matchAll(NUMBER_RE)].map((part) => {
    const canonical = part[0].replace(/^0+(?=\d)/, "");
    return `N${canonical.length.toString().padStart(10, "0")}:${canonical}`;
  });
  const remainder = rest.replace(NUMBER_RE, "").replace(/[\s_-]+/g, "");
  return `${prefix}\u001f${numbers.join("")}!${remainder}`;
}

export function compareDesignations(left: string, right: string): number {
  const leftKey = designationSortKey(left);
  const rightKey = designationSortKey(right);
  return leftKey < rightKey ? -1 : leftKey > rightKey ? 1 : 0;
}
