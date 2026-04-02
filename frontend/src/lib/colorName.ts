/**
 * Find the nearest named color for an RGB value.
 * Uses the XKCD crowd-sourced color survey (~950 descriptive names).
 * Matching is done in RGB space via squared Euclidean distance.
 */

import { NAMED_COLORS } from "./namedColors";

/** Convert 0-1 RGB to hex string like "#7a3f2b" */
export function rgbToHex(r: number, g: number, b: number): string {
  const toHex = (v: number) =>
    Math.round(Math.max(0, Math.min(1, v)) * 255)
      .toString(16)
      .padStart(2, "0");
  return `#${toHex(r)}${toHex(g)}${toHex(b)}`;
}

/** Find the closest named color to the given RGB (0-1 range). Returns the color name. */
export function findColorName(r: number, g: number, b: number): string {
  const ri = Math.round(r * 255);
  const gi = Math.round(g * 255);
  const bi = Math.round(b * 255);

  let bestName = "unknown";
  let bestDist = Infinity;

  for (const [name, cr, cg, cb] of NAMED_COLORS) {
    const dr = ri - cr;
    const dg = gi - cg;
    const db = bi - cb;
    const dist = dr * dr + dg * dg + db * db;
    if (dist < bestDist) {
      bestDist = dist;
      bestName = name;
      if (dist === 0) break;
    }
  }

  return bestName;
}
