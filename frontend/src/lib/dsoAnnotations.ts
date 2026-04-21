/**
 * Pure-function helpers for the FOV Simulator's DSO annotation overlay.
 *
 * Kept dependency-free and side-effect-free so they're cheap to test
 * and safe to call in render paths.
 */

const DEG_TO_RAD = Math.PI / 180;

/** Gnomonic (tangent-plane, TAN) projection of a sky position onto the
 *  tangent plane at ``(tangentRaDeg, tangentDecDeg)``. Returns
 *  ``(xi, eta)`` in radians on that plane — east-positive for xi,
 *  north-positive for eta.
 *
 *  Matches the projection hips2fits uses to render its tiles.
 */
function gnomonicProject(
  raDeg: number,
  decDeg: number,
  tangentRaDeg: number,
  tangentDecDeg: number,
): { xi: number; eta: number } {
  // RA wraps at 360°; collapse the delta onto (-180, +180] so an
  // object at 359.5° near a tangent at 0.5° doesn't render half a sky
  // away. (Full wrap-around region query is still deferred upstream.)
  let dRaDeg = raDeg - tangentRaDeg;
  if (dRaDeg > 180) dRaDeg -= 360;
  if (dRaDeg < -180) dRaDeg += 360;

  const dRa = dRaDeg * DEG_TO_RAD;
  const dec = decDeg * DEG_TO_RAD;
  const dec0 = tangentDecDeg * DEG_TO_RAD;

  const sinDec = Math.sin(dec);
  const cosDec = Math.cos(dec);
  const sinDec0 = Math.sin(dec0);
  const cosDec0 = Math.cos(dec0);
  const cosDRa = Math.cos(dRa);

  // ``cosC`` is the cosine of the angular separation between the
  // sky point and the tangent point; diverges for points > 90° away
  // (deep-sky annotations are always ≤ a few degrees, so this is safe).
  const cosC = sinDec0 * sinDec + cosDec0 * cosDec * cosDRa;
  const safeCosC = Math.max(cosC, 1e-6);
  const xi = (cosDec * Math.sin(dRa)) / safeCosC;
  const eta = (sinDec * cosDec0 - cosDec * sinDec0 * cosDRa) / safeCosC;
  return { xi, eta };
}

/** Project a DSO's RA/Dec into a composite that shares a single
 *  gnomonic tangent — matches the v0.18.0 sky-tile architecture where
 *  every cell in a HEALPix region renders on the region's shared
 *  tangent plane.
 *
 *  Returns pixel coords in the composite's east-left / north-up
 *  screen-coord system (the same system ``compute_grid_layout``
 *  returns on the backend). ``composite_width_px`` /
 *  ``composite_height_px`` and the ``view_center_*`` come from the
 *  grid-layout response; together with ``cell_size_deg`` they define
 *  the projection completely.
 */
export function projectRaDecInRegion(
  raDeg: number,
  decDeg: number,
  tangentRaDeg: number,
  tangentDecDeg: number,
  cellSizeDeg: number,
  cellPxSize: number,
  compositeViewCenterPxX: number,
  compositeViewCenterPxY: number,
  primaryRaDeg: number,
  primaryDecDeg: number,
): { cx: number; cy: number } {
  // Gnomonic project both the primary and the annotation onto the region
  // tangent, then compute the screen-pixel delta from the primary.
  const { xi: xiAnn, eta: etaAnn } = gnomonicProject(
    raDeg,
    decDeg,
    tangentRaDeg,
    tangentDecDeg,
  );
  const { xi: xiPri, eta: etaPri } = gnomonicProject(
    primaryRaDeg,
    primaryDecDeg,
    tangentRaDeg,
    tangentDecDeg,
  );
  // Pixel scale on the tangent plane.
  const pxPerRad = cellPxSize / 2 / Math.tan((cellSizeDeg / 2) * DEG_TO_RAD);
  // East-left / north-up conversion: +xi (east) → -dx (left),
  // +eta (north) → -dy (up, i.e. decreasing screen Y).
  const dx = -(xiAnn - xiPri) * pxPerRad;
  const dy = -(etaAnn - etaPri) * pxPerRad;
  return {
    cx: compositeViewCenterPxX + dx,
    cy: compositeViewCenterPxY + dy,
  };
}


/** Circle radius in pixels for an object of given angular diameter. */
export function radiusPxForArcmin(
  majorArcmin: number,
  sizePx: number,
  extentDeg: number,
): number {
  const scale = sizePx / extentDeg;
  const diameterDeg = majorArcmin / 60;
  return (diameterDeg / 2) * scale;
}

/** True when an object is too large to circle sensibly — its diameter
 *  exceeds ~half the image's angular extent. Callers should fall back
 *  to a label-only annotation in that case. */
export function isLabelOnly(
  majorArcmin: number | null,
  extentDeg: number,
): boolean {
  if (majorArcmin == null) return false;
  return majorArcmin / 60 > extentDeg / 2;
}

/** Map a linear slider position ([0, 1]) to an arcminute threshold on
 *  a log scale so the slider is perceptually uniform across the range
 *  — small objects spread out over the lower half, large ones at the
 *  top. ``v === 0`` always returns 0 (show everything with size). */
export function sliderToArcmin(v: number, maxArcmin: number): number {
  if (maxArcmin <= 0) return 0;
  const clamped = Math.max(0, Math.min(1, v));
  return Math.expm1(clamped * Math.log1p(maxArcmin));
}

/** Inverse of ``sliderToArcmin`` — given an arcminute threshold, what
 *  slider position produces it? Useful for seeding the slider when
 *  callers want to anchor to a specific arcmin value. */
export function arcminToSlider(arcmin: number, maxArcmin: number): number {
  if (maxArcmin <= 0) return 0;
  const clamped = Math.max(0, Math.min(arcmin, maxArcmin));
  return Math.log1p(clamped) / Math.log1p(maxArcmin);
}

/** True iff an annotation with the given (possibly null) angular size
 *  should render given the current arcmin threshold. Primary-target
 *  visibility is decided separately by the caller. */
export function passesThreshold(
  majorArcmin: number | null,
  thresholdArcmin: number,
): boolean {
  if (thresholdArcmin <= 0) return true;
  if (majorArcmin == null) return false;
  return majorArcmin >= thresholdArcmin;
}
