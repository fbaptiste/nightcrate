import type { HeaderCard } from "@/api/images";

/**
 * Pure header helpers shared by the Image Analyzer and anything else that needs
 * plate-solve hints out of a FITS header (the project Plate Solve tab).
 */

/** A header value, or null when absent / empty / the literal string "None". */
export function headerValue(cards: HeaderCard[], key: string): string | null {
  const card = cards.find((c) => c.key === key);
  return card?.value && card.value !== "" && card.value !== "None" ? card.value : null;
}

/**
 * First parseable coordinate among *keys*, in degrees.
 *
 * Accepts both sexagesimal (`"14 03 12.0"` or `"14:03:12.0"`) and plain decimal
 * degrees, because different capture software writes RA/Dec either way. RA in
 * sexagesimal is in hours, so it is multiplied by 15.
 */
export function parseHeaderCoord(
  cards: HeaderCard[],
  isRa: boolean,
  ...keys: string[]
): number | null {
  for (const k of keys) {
    const v = headerValue(cards, k);
    if (!v) continue;
    const parts = v.trim().replace(/:/g, " ").split(/\s+/);
    if (parts.length === 3) {
      const [a, b, c] = parts.map(Number);
      if ([a, b, c].every((x) => !isNaN(x))) {
        const deg = Math.abs(a) + b / 60 + c / 3600;
        const sign = v.trim().startsWith("-") ? -1 : 1;
        return isRa ? deg * 15 * sign : deg * sign;
      }
    }
    const n = parseFloat(v);
    if (!isNaN(n)) return n;
  }
  return null;
}

/** Numeric header value, or null. */
export function headerNumber(cards: HeaderCard[], key: string): number | null {
  const v = headerValue(cards, key);
  if (!v) return null;
  const n = parseFloat(v);
  return isNaN(n) ? null : n;
}
