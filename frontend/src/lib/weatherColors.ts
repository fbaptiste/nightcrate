/**
 * Score-to-color mapping for imaging quality scores.
 * Sequential blue palette: darker = better (good imaging = dark sky).
 */

import type { QualityLabel } from "@/api/weather";

export function scoreToBackground(score: number): string {
  const clamped = Math.max(0, Math.min(100, score));
  const saturation = 15 + (clamped / 100) * 50;
  const lightness = 75 - (clamped / 100) * 57;
  return `hsl(215, ${saturation.toFixed(1)}%, ${lightness.toFixed(1)}%)`;
}

export function scoreToTextColor(score: number): string {
  return score >= 45 ? "#e2e0dd" : "#1a1c20";
}

/**
 * Fallback label when the server did not supply one.
 *
 * Thresholds mirror `services/imaging_quality.py:LABEL_THRESHOLDS`. It can never
 * return "Unusable" — that is a statement about *availability*, not about the
 * score, so it cannot be re-derived from the number alone. Prefer the server's
 * `imaging_quality_label` wherever you have it.
 */
export function scoreToLabel(score: number): QualityLabel {
  if (score >= 75) return "Excellent";
  if (score >= 50) return "Good";
  if (score >= 25) return "Marginal";
  return "Poor";
}

/**
 * An unusable hour scores 0, and on a darker-is-better ramp that paints it the
 * palest, most innocuous cell on the chart — the deadest night looking like the
 * calmest one. Colour alone can't carry it (and the project rule is not to lean
 * on colour alone anyway), so unusable cells get a diagonal hatch as well.
 */
export const UNUSABLE_HATCH_ID = "unusable-hatch";

export function isUnusable(label: string | null | undefined): boolean {
  return label === "Unusable";
}
