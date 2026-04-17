/**
 * Shared color palette for rig calculator visualizations.
 *
 * Uses a blue/orange/teal palette that's colorblind-safe (Fred is red-green
 * color blind). Lighter variants provide 4-tier ratings where needed.
 */

export const RIG_BLUE = "#1976d2";
export const RIG_BLUE_LIGHT = "#64b5f6";
export const RIG_ORANGE = "#ed6c02";
export const RIG_ORANGE_LIGHT = "#ffb74d";
export const RIG_TEAL = "#00695c";

export type SamplingAssessmentValue =
  | "oversampled"
  | "well_sampled"
  | "undersampled";

export function samplingColor(assessment: SamplingAssessmentValue | string): string {
  if (assessment === "well_sampled") return RIG_BLUE;
  if (assessment === "oversampled") return RIG_ORANGE;
  return RIG_TEAL; // undersampled (and any unknown value falls here)
}

export type GuideRating = "excellent" | "good" | "marginal" | "poor";

/** Fill/text color for a guide-suitability rating chip or bar. */
export function ratingColor(rating: GuideRating | string): string {
  switch (rating) {
    case "excellent":
      return RIG_BLUE;
    case "good":
      return RIG_BLUE_LIGHT;
    case "marginal":
      return RIG_ORANGE_LIGHT;
    case "poor":
    default:
      return RIG_ORANGE;
  }
}

/**
 * Whether white or near-black text reads best against the rating color.
 * Excellent (solid blue) and poor (solid orange) want white; the light
 * variants want dark text.
 */
export function ratingTextColor(rating: GuideRating | string): string {
  if (rating === "excellent" || rating === "poor") return "#ffffff";
  return "rgba(0, 0, 0, 0.87)";
}

export function ratingLabel(rating: GuideRating | string): string {
  switch (rating) {
    case "excellent":
      return "Excellent";
    case "good":
      return "Good";
    case "marginal":
      return "Marginal";
    case "poor":
      return "Poor";
    default:
      return rating;
  }
}
