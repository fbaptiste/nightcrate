/** Shared helpers + types for the planner sky-position dials. */

/** One (azimuth, altitude) point on a body's path across the sky. */
export interface SkyPathPoint {
  az: number;
  alt: number;
}

/** A single resolved sky-position sample, shared by the flat and 3-D dome
 *  renderings and the readout. */
export interface SkyDialSample {
  targetAz: number;
  targetAlt: number;
  moonAz: number;
  moonAlt: number;
  /** Tonight's lunar illumination (0–100) — shades the Moon glyph. */
  moonIllumPct: number;
  /** True angular target↔Moon separation at this instant, degrees. */
  separationDeg: number;
}

const COMPASS_16 = [
  "N",
  "NNE",
  "NE",
  "ENE",
  "E",
  "ESE",
  "SE",
  "SSE",
  "S",
  "SSW",
  "SW",
  "WSW",
  "W",
  "WNW",
  "NW",
  "NNW",
];

/** Format an azimuth bearing as "143° SE" — the cardinal abbreviation
 *  makes "opposite side of the sky" readable at a glance. */
export function azLabel(azDeg: number): string {
  const norm = ((azDeg % 360) + 360) % 360;
  const idx = Math.round(norm / 22.5) % 16;
  return `${Math.round(norm)}° ${COMPASS_16[idx]}`;
}
