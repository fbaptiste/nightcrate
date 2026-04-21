/**
 * Auto-zoom logic for DSO catalog previews.
 *
 * Picks a preview extent + tier that fills the frame with the object
 * plus a little padding, so a 30″ planetary nebula isn't rendered as
 * 3 pixels inside a 1° frame. Shared between the catalog detail panel
 * and (eventually) the full-size preview modal so both views resolve
 * to the same auto-tier decision.
 */
import type { SkyTileTier } from "@/api/planner";

/** Minimum useful preview extent — matches DSS2's ~1″/px native and
 *  keeps a small planetary nebula readable even at the zoom floor. */
const MIN_EXTENT_ARCMIN = 2.0;
const ARCMIN_PER_DEG = 60;

/** Compute preview extent (degrees) from a DSO's major axis. */
export function previewExtentDeg(majArcmin: number | null): number {
  // Default floor for objects with no size on record — shows a field
  // the user can orient against even with zero metadata.
  if (majArcmin == null || majArcmin <= 0) {
    return 0.25; // 15 arcmin — roomy enough to spot the target by eye
  }
  let arcmin: number;
  if (majArcmin < 5) {
    arcmin = 10; // small objects get a fixed 10' frame for context
  } else if (majArcmin < 30) {
    arcmin = majArcmin * 2;
  } else if (majArcmin < 120) {
    arcmin = majArcmin * 1.3;
  } else {
    arcmin = majArcmin * 1.1;
  }
  arcmin = Math.max(arcmin, MIN_EXTENT_ARCMIN);
  return arcmin / ARCMIN_PER_DEG;
}

/** Pick the tier whose cells comfortably contain the given extent.
 *  Matches the backend's ``tier_for_fov`` thresholds so cache keys
 *  line up across rigs / previews. */
export function tierForExtent(extentDeg: number): SkyTileTier {
  if (extentDeg <= 1.0) return "narrow";
  if (extentDeg <= 3.0) return "med";
  return "wide";
}

/** All-in-one: given a DSO's major axis, return the (tier, extent)
 *  pair the SkyPreview component should request. */
export function previewSpecForDsoSize(majArcmin: number | null): {
  tier: SkyTileTier;
  extentDeg: number;
} {
  const extentDeg = previewExtentDeg(majArcmin);
  return { tier: tierForExtent(extentDeg), extentDeg };
}
