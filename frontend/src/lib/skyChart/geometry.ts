import * as d3 from "d3";
import type { SolveWcs } from "../../api/projectInfo";

export type SkyCoord = [ra: number, dec: number];
export interface SkyView { centre: SkyCoord; spanDeg: number }
export type Tri = [[number, number], [number, number], [number, number]];
export type Rect = { x: number; y: number; width: number; height: number };

export const MIN_SPAN_DEG = 0.1;
export const MAX_SPAN_DEG = 180;
export const CLIP_DEG = 150;
export const WHOLE_SKY_SPAN_DEG = 180;

const DEG = Math.PI / 180;
const clamp = (value: number, low: number, high: number) => Math.max(low, Math.min(high, value));
const wrapRa = (ra: number) => ((ra % 360) + 360) % 360;

export function scaleForSpan(spanDeg: number, shortSidePx: number): number {
  return shortSidePx / (2 * Math.tan(spanDeg * DEG / 4));
}

export function makeProjection(view: SkyView, widthPx: number, heightPx: number): d3.GeoProjection {
  return d3.geoStereographic()
    .rotate([-view.centre[0], -view.centre[1]])
    .reflectX(true)
    .clipAngle(CLIP_DEG)
    .scale(scaleForSpan(view.spanDeg, Math.min(widthPx, heightPx)))
    .translate([widthPx / 2, heightPx / 2]);
}

export function pxPerDegree(view: SkyView, widthPx: number, heightPx: number): number {
  return scaleForSpan(view.spanDeg, Math.min(widthPx, heightPx)) * Math.PI / 360;
}

function projectedResidual(
  centre: SkyCoord,
  spanDeg: number,
  grabbed: SkyCoord,
  pointerPx: [number, number],
  widthPx: number,
  heightPx: number,
): { vector: [number, number]; length: number } | null {
  const projected = makeProjection({ centre, spanDeg }, widthPx, heightPx)(grabbed);
  if (!projected || !projected.every(Number.isFinite)) return null;
  const vector: [number, number] = [projected[0] - pointerPx[0], projected[1] - pointerPx[1]];
  return { vector, length: Math.hypot(...vector) };
}

function destination(start: SkyCoord, bearingRad: number, distanceRad: number): SkyCoord {
  const latitude = start[1] * DEG;
  const longitude = start[0] * DEG;
  const destinationLatitude = Math.asin(
    Math.sin(latitude) * Math.cos(distanceRad)
      + Math.cos(latitude) * Math.sin(distanceRad) * Math.cos(bearingRad),
  );
  const destinationLongitude = longitude + Math.atan2(
    Math.sin(bearingRad) * Math.sin(distanceRad) * Math.cos(latitude),
    Math.cos(distanceRad) - Math.sin(latitude) * Math.sin(destinationLatitude),
  );
  return [wrapRa(destinationLongitude / DEG), clamp(destinationLatitude / DEG, -90, 90)];
}

function bearing(start: SkyCoord, end: SkyCoord): number {
  const startLatitude = start[1] * DEG;
  const endLatitude = end[1] * DEG;
  const longitudeDelta = (end[0] - start[0]) * DEG;
  return Math.atan2(
    Math.sin(longitudeDelta) * Math.cos(endLatitude),
    Math.cos(startLatitude) * Math.sin(endLatitude)
      - Math.sin(startLatitude) * Math.cos(endLatitude) * Math.cos(longitudeDelta),
  );
}

function wrapRadians(angle: number): number {
  return ((angle + Math.PI) % (2 * Math.PI) + 2 * Math.PI) % (2 * Math.PI) - Math.PI;
}

export function anchorView(
  view: SkyView,
  spanDeg: number,
  grabbed: SkyCoord,
  pointerPx: [number, number],
  widthPx: number,
  heightPx: number,
): { view: SkyView; residualPx: number } {
  const span = clamp(spanDeg, MIN_SPAN_DEG, MAX_SPAN_DEG);
  const current: SkyCoord = [wrapRa(view.centre[0]), clamp(view.centre[1], -90, 90)];
  const dx = pointerPx[0] - widthPx / 2;
  const dy = pointerPx[1] - heightPx / 2;
  const radius = Math.hypot(dx, dy);
  if (radius < 1e-9) {
    const centre: SkyCoord = [wrapRa(grabbed[0]), clamp(grabbed[1], -90, 90)];
    const residual = projectedResidual(centre, span, grabbed, pointerPx, widthPx, heightPx);
    return { view: { centre, spanDeg: span }, residualPx: residual?.length ?? 0 };
  }

  const scale = scaleForSpan(span, Math.min(widthPx, heightPx));
  const angularDistance = 2 * Math.atan(radius / scale);
  const targetBearing = Math.atan2(-dx, -dy);
  const rootFunction = (alpha: number) => wrapRadians(
    bearing(destination(grabbed, alpha, angularDistance), grabbed) - targetBearing,
  );
  const roots: number[] = [];
  const sampleStep = Math.PI / 180;
  for (let index = 0; index < 360; index += 1) {
    let low = index * sampleStep;
    let high = (index + 1) * sampleStep;
    let lowValue = rootFunction(low);
    const highValue = rootFunction(high);
    if (Math.abs(lowValue) < 1e-12) {
      roots.push(low);
      continue;
    }
    if (lowValue * highValue >= 0 || Math.abs(lowValue - highValue) >= Math.PI) continue;
    for (let pass = 0; pass < 50; pass += 1) {
      const middle = (low + high) / 2;
      const middleValue = rootFunction(middle);
      if (lowValue * middleValue <= 0) {
        high = middle;
      } else {
        low = middle;
        lowValue = middleValue;
      }
    }
    roots.push((low + high) / 2);
  }

  type Candidate = { centre: SkyCoord; residual: number; fromCurrent: number };
  const evaluate = (centre: SkyCoord): Candidate | null => {
    const normalized: SkyCoord = [wrapRa(centre[0]), clamp(centre[1], -90, 90)];
    if (!normalized.every(Number.isFinite)) return null;
    const residual = projectedResidual(normalized, span, grabbed, pointerPx, widthPx, heightPx);
    if (!residual || !Number.isFinite(residual.length)) return null;
    return {
      centre: normalized,
      residual: residual.length,
      fromCurrent: d3.geoDistance(current, normalized),
    };
  };
  const better = (left: Candidate | null, right: Candidate | null): Candidate | null => {
    if (!left) return right;
    if (!right) return left;
    if (Math.abs(left.residual - right.residual) > 1e-9) return left.residual < right.residual ? left : right;
    return left.fromCurrent <= right.fromCurrent ? left : right;
  };

  let best: Candidate | null = null;
  for (const root of roots) best = better(best, evaluate(destination(grabbed, root, angularDistance)));

  if (!best || best.residual > 0.5) {
    const pole: SkyCoord = [grabbed[0], grabbed[1] >= 0 ? 90 : -90];
    let local = better(better(best, evaluate(current)), evaluate(pole));
    let longitudeStep = 45;
    let latitudeStep = 22.5;
    let projections = 0;
    while (local && projections + 8 <= 300 && Math.max(longitudeStep, latitudeStep) > 1e-7) {
      let next: Candidate | null = local;
      for (const longitudeDirection of [-1, 0, 1]) {
        for (const latitudeDirection of [-1, 0, 1]) {
          if (longitudeDirection === 0 && latitudeDirection === 0) continue;
          const candidate = evaluate([
            local.centre[0] + longitudeDirection * longitudeStep,
            local.centre[1] + latitudeDirection * latitudeStep,
          ]);
          projections += 1;
          next = better(next, candidate);
        }
      }
      if (next && next.residual + 1e-9 < local.residual) {
        local = next;
      } else {
        longitudeStep /= 2;
        latitudeStep /= 2;
      }
    }
    best = better(best, local);
  }

  const fallback = evaluate(current) ?? {
    centre: current,
    residual: Number.MAX_VALUE,
    fromCurrent: 0,
  };
  const result = best ?? fallback;
  return { view: { centre: result.centre, spanDeg: span }, residualPx: result.residual };
}

export function panView(
  view: SkyView,
  grabbed: SkyCoord,
  pointerPx: [number, number],
  widthPx: number,
  heightPx: number,
): SkyView {
  return anchorView(view, view.spanDeg, grabbed, pointerPx, widthPx, heightPx).view;
}

export function panViewBy(
  view: SkyView,
  dxPx: number,
  dyPx: number,
  widthPx: number,
  heightPx: number,
): SkyView {
  return panView(view, view.centre, [widthPx / 2 + dxPx, heightPx / 2 + dyPx], widthPx, heightPx);
}

export function zoomViewAt(
  view: SkyView,
  factor: number,
  pointPx: [number, number],
  widthPx: number,
  heightPx: number,
): SkyView {
  const grabbed = makeProjection(view, widthPx, heightPx).invert?.(pointPx);
  const span = clamp(view.spanDeg / factor, MIN_SPAN_DEG, MAX_SPAN_DEG);
  if (!grabbed || !grabbed.every(Number.isFinite)) return { ...view, spanDeg: span };
  return anchorView(view, span, [wrapRa(grabbed[0]), grabbed[1]], pointPx, widthPx, heightPx).view;
}

function circularRaCentre(points: SkyCoord[]): number {
  const sorted = points.map((point) => wrapRa(point[0])).sort((a, b) => a - b);
  if (sorted.length < 2) return sorted[0] ?? 0;
  let largestGap = -1;
  let gapIndex = 0;
  for (let index = 0; index < sorted.length; index += 1) {
    const next = index + 1 < sorted.length ? sorted[index + 1] : sorted[0] + 360;
    const gap = next - sorted[index];
    if (gap > largestGap) { largestGap = gap; gapIndex = index; }
  }
  const start = sorted[(gapIndex + 1) % sorted.length];
  return wrapRa(start + (360 - largestGap) / 2);
}

export function fitConstellationView(
  rings: SkyCoord[][],
  pictureCentre: SkyCoord,
  widthPx: number,
  heightPx: number,
): SkyView {
  const points = [...rings.flat(), pictureCentre];
  let centre: SkyCoord = [
    circularRaCentre(points),
    clamp((Math.min(...points.map((point) => point[1])) + Math.max(...points.map((point) => point[1]))) / 2, -90, 90),
  ];
  const marginX = widthPx * 0.08;
  const marginY = heightPx * 0.08;

  // Re-centre the projected bounds. This handles RA 0 and polar rings without
  // treating right ascension as a flat 0–360 axis.
  for (let pass = 0; pass < 8; pass += 1) {
    const projection = makeProjection({ centre, spanDeg: 120 }, widthPx, heightPx);
    const projected = points.map((point) => projection(point)).filter((point): point is [number, number] => !!point);
    if (!projected.length) break;
    const minX = Math.min(...projected.map((point) => point[0]));
    const maxX = Math.max(...projected.map((point) => point[0]));
    const minY = Math.min(...projected.map((point) => point[1]));
    const maxY = Math.max(...projected.map((point) => point[1]));
    const skyAtBoundsCentre = projection.invert?.([(minX + maxX) / 2, (minY + maxY) / 2]);
    if (!skyAtBoundsCentre || !skyAtBoundsCentre.every(Number.isFinite)) break;
    const moved = d3.geoDistance(centre, skyAtBoundsCentre) / DEG;
    centre = [wrapRa(skyAtBoundsCentre[0]), clamp(skyAtBoundsCentre[1], -90, 90)];
    if (moved < 1e-5) break;
  }

  const fits = (spanDeg: number) => {
    const projection = makeProjection({ centre, spanDeg }, widthPx, heightPx);
    return points.every((point) => {
      const projected = projection(point);
      return !!projected && projected[0] >= marginX && projected[0] <= widthPx - marginX && projected[1] >= marginY && projected[1] <= heightPx - marginY;
    });
  };
  let low = 20;
  let high = 120;
  if (!fits(low)) {
    for (let pass = 0; pass < 40; pass += 1) {
      const middle = (low + high) / 2;
      if (fits(middle)) high = middle;
      else low = middle;
    }
  } else high = 20;
  return { centre, spanDeg: clamp(high, 20, 120) };
}

export function tanPixelToSky(wcs: SolveWcs, x: number, y: number): SkyCoord {
  const dx = x + 1 - wcs.crpix1;
  const dy = y + 1 - wcs.crpix2;
  const xi = (wcs.cd1_1 * dx + wcs.cd1_2 * dy) * DEG;
  const eta = (wcs.cd2_1 * dx + wcs.cd2_2 * dy) * DEG;
  const ra0 = wcs.crval1 * DEG;
  const dec0 = wcs.crval2 * DEG;
  const denominator = Math.cos(dec0) - eta * Math.sin(dec0);
  const ra = ra0 + Math.atan2(xi, denominator);
  const dec = Math.atan2(
    Math.sin(dec0) + eta * Math.cos(dec0),
    Math.sqrt(denominator * denominator + xi * xi),
  );
  return [wrapRa(ra / DEG), dec / DEG];
}

export function pictureOutline(wcs: SolveWcs, perEdge = 8): SkyCoord[] {
  const x0 = -0.5;
  const y0 = -0.5;
  const x1 = wcs.width - 0.5;
  const y1 = wcs.height - 0.5;
  const result: SkyCoord[] = [];
  for (let index = 0; index < perEdge; index += 1) result.push(tanPixelToSky(wcs, x0 + (x1 - x0) * index / perEdge, y0));
  for (let index = 0; index < perEdge; index += 1) result.push(tanPixelToSky(wcs, x1, y0 + (y1 - y0) * index / perEdge));
  for (let index = 0; index < perEdge; index += 1) result.push(tanPixelToSky(wcs, x1 - (x1 - x0) * index / perEdge, y1));
  for (let index = 0; index < perEdge; index += 1) result.push(tanPixelToSky(wcs, x0, y1 - (y1 - y0) * index / perEdge));
  return result;
}

export function pictureLongerSideDeg(wcs: SolveWcs): number {
  const top = d3.geoDistance(tanPixelToSky(wcs, -0.5, -0.5), tanPixelToSky(wcs, wcs.width - 0.5, -0.5)) / DEG;
  const left = d3.geoDistance(tanPixelToSky(wcs, -0.5, -0.5), tanPixelToSky(wcs, -0.5, wcs.height - 0.5)) / DEG;
  return Math.max(top, left);
}

export function pictureView(centre: SkyCoord, longerSideDeg: number): SkyView {
  return { centre, spanDeg: clamp(longerSideDeg * 3.5, MIN_SPAN_DEG, MAX_SPAN_DEG) };
}

export function wholeSkyView(centre: SkyCoord): SkyView {
  return { centre, spanDeg: WHOLE_SKY_SPAN_DEG };
}

export function interpolateView(a: SkyView, b: SkyView): (t: number) => SkyView {
  const interpolateCentre = d3.geoInterpolate(a.centre, b.centre);
  const logA = Math.log(a.spanDeg);
  const logB = Math.log(b.spanDeg);
  return (t) => ({
    centre: interpolateCentre(t) as SkyCoord,
    spanDeg: Math.exp(logA + (logB - logA) * t),
  });
}

export function densifyRing(ring: SkyCoord[], maxStepDeg = 0.25): SkyCoord[] {
  if (!ring.length) return [];
  const closed = ring[0][0] === ring.at(-1)?.[0] && ring[0][1] === ring.at(-1)?.[1]
    ? ring
    : [...ring, ring[0]];
  const result: SkyCoord[] = [];
  for (let index = 1; index < closed.length; index += 1) {
    const start = closed[index - 1];
    const end = closed[index];
    let deltaRa = end[0] - start[0];
    if (deltaRa > 180) deltaRa -= 360;
    if (deltaRa < -180) deltaRa += 360;
    const deltaDec = end[1] - start[1];
    const steps = Math.max(1, Math.ceil(Math.max(Math.abs(deltaRa), Math.abs(deltaDec)) / maxStepDeg));
    if (index === 1) result.push([wrapRa(start[0]), start[1]]);
    for (let step = 1; step <= steps; step += 1) {
      result.push([wrapRa(start[0] + deltaRa * step / steps), start[1] + deltaDec * step / steps]);
    }
  }
  return result;
}

export function visibleLineRuns(
  coordinates: SkyCoord[],
  centre: SkyCoord,
  radiusDeg: number,
): SkyCoord[][] {
  const radius = radiusDeg * DEG;
  const runs: SkyCoord[][] = [];
  let run: SkyCoord[] = [];
  for (let index = 1; index < coordinates.length; index += 1) {
    const start = coordinates[index - 1];
    const end = coordinates[index];
    const lowerBound = Math.min(
      d3.geoDistance(centre, start),
      d3.geoDistance(centre, end),
    ) - d3.geoDistance(start, end);
    if (lowerBound <= radius + 1e-12) {
      if (!run.length) run.push(start);
      run.push(end);
    } else if (run.length) {
      runs.push(run);
      run = [];
    }
  }
  if (run.length) runs.push(run);

  const first = coordinates[0];
  const last = coordinates.at(-1);
  const closed = first && last && first[0] === last[0] && first[1] === last[1];
  if (closed && runs.length > 1) {
    const firstRun = runs[0];
    const lastRun = runs.at(-1)!;
    const join = firstRun[0];
    const end = lastRun.at(-1)!;
    if (join[0] === end[0] && join[1] === end[1]) {
      runs[0] = [...lastRun, ...firstRun.slice(1)];
      runs.pop();
    }
  }
  return runs;
}

export function triangleAffine(src: Tri, dst: Tri): [number, number, number, number, number, number] {
  const [[x0, y0], [x1, y1], [x2, y2]] = src;
  const [[u0, v0], [u1, v1], [u2, v2]] = dst;
  const determinant = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0);
  const a = ((u1 - u0) * (y2 - y0) - (u2 - u0) * (y1 - y0)) / determinant;
  const c = ((x1 - x0) * (u2 - u0) - (x2 - x0) * (u1 - u0)) / determinant;
  const b = ((v1 - v0) * (y2 - y0) - (v2 - v0) * (y1 - y0)) / determinant;
  const d = ((x1 - x0) * (v2 - v0) - (x2 - x0) * (v1 - v0)) / determinant;
  return [a, b, c, d, u0 - a * x0 - c * y0, v0 - b * x0 - d * y0];
}

function lineIntersection(pointA: [number, number], directionA: [number, number], pointB: [number, number], directionB: [number, number]): [number, number] | null {
  const determinant = directionA[0] * directionB[1] - directionA[1] * directionB[0];
  if (Math.abs(determinant) < 1e-12) return null;
  const dx = pointB[0] - pointA[0];
  const dy = pointB[1] - pointA[1];
  const t = (dx * directionB[1] - dy * directionB[0]) / determinant;
  return [pointA[0] + t * directionA[0], pointA[1] + t * directionA[1]];
}

export function growTriangle(tri: Tri, px: number, miterCapPx = 3): Tri {
  const area = (tri[1][0] - tri[0][0]) * (tri[2][1] - tri[0][1]) - (tri[1][1] - tri[0][1]) * (tri[2][0] - tri[0][0]);
  const orientation = Math.sign(area) || 1;
  const lines = tri.map((point, index) => {
    const next = tri[(index + 1) % 3];
    const dx = next[0] - point[0];
    const dy = next[1] - point[1];
    const length = Math.hypot(dx, dy) || 1;
    const normal: [number, number] = [orientation * dy / length, orientation * -dx / length];
    return { point: [point[0] + normal[0] * px, point[1] + normal[1] * px] as [number, number], direction: [dx, dy] as [number, number] };
  });
  return tri.map((vertex, index) => {
    const previous = lines[(index + 2) % 3];
    const current = lines[index];
    const intersection = lineIntersection(previous.point, previous.direction, current.point, current.direction) ?? current.point;
    const dx = intersection[0] - vertex[0];
    const dy = intersection[1] - vertex[1];
    const length = Math.hypot(dx, dy);
    const factor = length > miterCapPx ? miterCapPx / length : 1;
    return [vertex[0] + dx * factor, vertex[1] + dy * factor] as [number, number];
  }) as Tri;
}

export function sourceRect(
  grownDst: Tri,
  affine: [number, number, number, number, number, number],
  imageW: number,
  imageH: number,
  marginPx = 2,
): { sx: number; sy: number; sw: number; sh: number } | null {
  const [a, b, c, d, e, f] = affine;
  const determinant = a * d - b * c;
  if (!Number.isFinite(determinant) || Math.abs(determinant) < 1e-12) return null;
  const inverse = ([x, y]: [number, number]): [number, number] => {
    const tx = x - e;
    const ty = y - f;
    return [(d * tx - c * ty) / determinant, (-b * tx + a * ty) / determinant];
  };
  const points = grownDst.map(inverse);
  const sx = Math.max(0, Math.floor(Math.min(...points.map((point) => point[0])) - marginPx));
  const sy = Math.max(0, Math.floor(Math.min(...points.map((point) => point[1])) - marginPx));
  const ex = Math.min(imageW, Math.ceil(Math.max(...points.map((point) => point[0])) + marginPx));
  const ey = Math.min(imageH, Math.ceil(Math.max(...points.map((point) => point[1])) + marginPx));
  return ex > sx && ey > sy ? { sx, sy, sw: ex - sx, sh: ey - sy } : null;
}

export function segmentTouchesRect(
  start: [number, number],
  end: [number, number],
  width: number,
  height: number,
  margin = 0,
): boolean {
  const dx = end[0] - start[0];
  const dy = end[1] - start[1];
  let minimum = 0;
  let maximum = 1;
  for (const [direction, distance] of [
    [-dx, start[0] + margin],
    [dx, width + margin - start[0]],
    [-dy, start[1] + margin],
    [dy, height + margin - start[1]],
  ] as [number, number][]) {
    if (direction === 0) {
      if (distance < 0) return false;
      continue;
    }
    const ratio = distance / direction;
    if (direction < 0) minimum = Math.max(minimum, ratio);
    else maximum = Math.min(maximum, ratio);
    if (minimum > maximum) return false;
  }
  return true;
}

export interface TapRecord {
  time: number;
  point: [number, number];
}

export interface TapCandidate extends TapRecord {
  durationMs: number;
  movementPx: number;
  blocked: boolean;
}

export function classifyTap(
  candidate: TapCandidate,
  previous: TapRecord | null,
): { kind: "none" | "tap" | "double"; lastTap: TapRecord | null } {
  if (
    candidate.blocked
    || candidate.durationMs < 0
    || candidate.durationMs > 300
    || candidate.movementPx > 10
  ) return { kind: "none", lastTap: null };
  if (
    previous
    && candidate.time - previous.time >= 0
    && candidate.time - previous.time <= 300
    && Math.hypot(candidate.point[0] - previous.point[0], candidate.point[1] - previous.point[1]) <= 24
  ) return { kind: "double", lastTap: null };
  return { kind: "tap", lastTap: { time: candidate.time, point: candidate.point } };
}

interface MeshOptions {
  wcs: SolveWcs;
  imageW: number;
  imageH: number;
  project: (coord: SkyCoord) => [number, number] | null;
  isFar: (coord: SkyCoord) => boolean;
  isWide?: (coord: SkyCoord) => boolean;
  viewport: { width: number; height: number };
  tolerancePx?: number;
  wideTolerancePx?: number;
  maxDepth?: number;
  maxTriangles?: number;
}

export function adaptiveMesh(opts: MeshOptions): { src: Tri; dst: Tri }[] {
  const tolerance = opts.tolerancePx ?? 0.25;
  const wideTolerance = opts.wideTolerancePx ?? 1;
  const maxDepth = opts.maxDepth ?? 10;
  const maxTriangles = opts.maxTriangles ?? 1024;
  type MeshTriangle = { src: Tri; dst: Tri };
  type SplitKind = "size" | "visibility" | "error";
  interface Cell {
    x0: number;
    y0: number;
    x1: number;
    y1: number;
    depth: number;
    triangles: MeshTriangle[];
    splitKind: SplitKind | null;
    priority: number;
    cost: number;
  }
  const toSource = (x: number, y: number): [number, number] => [
    (x + 0.5) * opts.imageW / opts.wcs.width,
    (y + 0.5) * opts.imageH / opts.wcs.height,
  ];
  const exact = (x: number, y: number) => opts.project(tanPixelToSky(opts.wcs, x, y));

  const analyse = (
    x0: number,
    y0: number,
    x1: number,
    y1: number,
    depth: number,
  ): Cell => {
    const rasterCorners: [[number, number], [number, number], [number, number], [number, number]] = [
      [x0, y0], [x1, y0], [x1, y1], [x0, y1],
    ];
    const skyCorners = rasterCorners.map(([x, y]) => tanPixelToSky(opts.wcs, x, y));
    const farCorners = skyCorners.map(opts.isFar);
    const dstCorners = skyCorners.map(opts.project);
    const everyCornerProjects = dstCorners.every((point) => point?.every(Number.isFinite));
    const dst = everyCornerProjects
      ? dstCorners as [[number, number], [number, number], [number, number], [number, number]]
      : null;
    const src = rasterCorners.map(([x, y]) => toSource(x, y)) as [[number, number], [number, number], [number, number], [number, number]];
    const triA = dst ? { src: [src[0], src[1], src[3]] as Tri, dst: [dst[0], dst[1], dst[3]] as Tri } : null;
    const triB = dst ? { src: [src[1], src[2], src[3]] as Tri, dst: [dst[1], dst[2], dst[3]] as Tri } : null;
    const affineA = triA ? triangleAffine(triA.src, triA.dst) : null;
    const affineB = triB ? triangleAffine(triB.src, triB.dst) : null;
    const samples: [number, number, "a" | "b"][] = [
      [(2 * x0 + x1) / 3, (2 * y0 + y1) / 3, "a"],
      [(x0 + 2 * x1) / 3, (y0 + 2 * y1) / 3, "b"],
      [(x0 + x1) / 2, y0, "a"], [x1, (y0 + y1) / 2, "b"],
      [(x0 + x1) / 2, y1, "b"], [x0, (y0 + y1) / 2, "a"],
      [(x0 + x1) / 2, (y0 + y1) / 2, "a"],
    ];
    let sampleResidual = affineA && affineB ? 0 : Infinity;
    if (affineA && affineB) {
      for (const [x, y, side] of samples) {
        const projected = exact(x, y);
        if (!projected || !projected.every(Number.isFinite)) {
          sampleResidual = Infinity;
          break;
        }
        const [a, b, c, d, e, f] = side === "a" ? affineA : affineB;
        const [u, v] = toSource(x, y);
        const residual = Math.hypot(
          a * u + c * v + e - projected[0],
          b * u + d * v + f - projected[1],
        );
        sampleResidual = Number.isFinite(residual) ? Math.max(sampleResidual, residual) : Infinity;
      }
    }
    const longerEdgeDeg = Math.max(
      d3.geoDistance(skyCorners[0], skyCorners[1]),
      d3.geoDistance(skyCorners[1], skyCorners[2]),
      d3.geoDistance(skyCorners[2], skyCorners[3]),
      d3.geoDistance(skyCorners[3], skyCorners[0]),
    ) / DEG;
    const cellTriangles: MeshTriangle[] = [];
    let culled = farCorners.every(Boolean);
    if (dst) {
      const minX = Math.min(...dst.map((point) => point[0]));
      const maxX = Math.max(...dst.map((point) => point[0]));
      const minY = Math.min(...dst.map((point) => point[1]));
      const maxY = Math.max(...dst.map((point) => point[1]));
      if (maxX < -2 || minX > opts.viewport.width + 2 || maxY < -2 || minY > opts.viewport.height + 2) culled = true;
    }
    const emitTriangle = (indices: [number, number, number]) => {
      if (culled || indices.some((index) => farCorners[index] || !dstCorners[index]?.every(Number.isFinite))) return;
      cellTriangles.push({
        src: indices.map((index) => src[index]) as Tri,
        dst: indices.map((index) => dstCorners[index]!) as Tri,
      });
    };
    emitTriangle([0, 1, 3]);
    emitTriangle([1, 2, 3]);

    const threshold = opts.isWide && skyCorners.some(opts.isWide) ? wideTolerance : tolerance;
    let splitKind: SplitKind | null = null;
    let priority = 0;
    if (depth < maxDepth) {
      if (longerEdgeDeg > 8) {
        splitKind = "size";
        priority = longerEdgeDeg;
      } else if ((farCorners.some(Boolean) && !farCorners.every(Boolean)) || !everyCornerProjects) {
        splitKind = "visibility";
        priority = Number.isFinite(sampleResidual) ? sampleResidual : Number.MAX_VALUE;
      } else if (!culled && sampleResidual > threshold) {
        splitKind = "error";
        priority = sampleResidual;
      }
    }
    return {
      x0, y0, x1, y1, depth, triangles: cellTriangles, splitKind, priority,
      cost: splitKind ? 2 : cellTriangles.length,
    };
  };

  const root = analyse(-0.5, -0.5, opts.wcs.width - 0.5, opts.wcs.height - 0.5, 0);
  const leaves = new Set<Cell>([root]);
  const queue: Cell[] = root.splitKind ? [root] : [];
  let budgetCost = root.cost;
  const rank = (kind: SplitKind | null) => kind === "size" ? 3 : kind === "visibility" ? 2 : kind === "error" ? 1 : 0;

  while (queue.length) {
    queue.sort((left, right) => rank(left.splitKind) - rank(right.splitKind) || left.priority - right.priority);
    const cell = queue.pop()!;
    const xm = (cell.x0 + cell.x1) / 2;
    const ym = (cell.y0 + cell.y1) / 2;
    const children = [
      analyse(cell.x0, cell.y0, xm, ym, cell.depth + 1),
      analyse(xm, cell.y0, cell.x1, ym, cell.depth + 1),
      analyse(cell.x0, ym, xm, cell.y1, cell.depth + 1),
      analyse(xm, ym, cell.x1, cell.y1, cell.depth + 1),
    ];
    const nextCost = budgetCost - cell.cost + children.reduce((sum, child) => sum + child.cost, 0);
    if (nextCost > maxTriangles) {
      budgetCost += cell.triangles.length - cell.cost;
      cell.cost = cell.triangles.length;
      if (cell.splitKind === "error") break;
      continue;
    }
    budgetCost = nextCost;
    leaves.delete(cell);
    for (const child of children) {
      leaves.add(child);
      if (child.splitKind) queue.push(child);
    }
  }

  return [...leaves].flatMap((cell) => cell.triangles);
}

export function trimSegment(a: [number, number], b: [number, number], gapA: number, gapB: number): [[number, number], [number, number]] {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const length = Math.hypot(dx, dy);
  if (!length) return [a, b];
  const start = Math.min(gapA, length * 0.4) / length;
  const end = Math.min(gapB, length * 0.4) / length;
  return [[a[0] + dx * start, a[1] + dy * start], [b[0] - dx * end, b[1] - dy * end]];
}

export function starRadius(mag: number, spanDeg: number): number {
  const k = clamp(84 / spanDeg, 0.5, 1.25);
  return Math.max(0.55, (6.4 - mag) * 0.62 * k);
}

export function rectsOverlap(a: Rect, b: Rect): boolean {
  return a.x < b.x + b.width && a.x + a.width > b.x
    && a.y < b.y + b.height && a.y + a.height > b.y;
}

// Constellation views in a desktop window are at most about 70° wide (Hydra), so they name stars
// to 3.5; the whole sky names them only to 1.5.
// In between, the limit ramps, so zooming out doesn't drop from about 100 names to 10 in one step.
export function starNameMagnitudeLimit(spanDeg: number): number {
  if (spanDeg >= 150) return 1.5;
  if (spanDeg <= 90) return 3.5;
  return 3.5 - (2 * (spanDeg - 90)) / 60;
}

export function placeStarName(
  star: [number, number],
  radiusPx: number,
  textWidth: number,
  fontSizePx: number,
  occupied: readonly Rect[],
  viewport: { width: number; height: number },
): { x: number; y: number; align: "left" | "right" | "center"; box: Rect } | null {
  const [starX, starY] = star;
  const gap = 4;
  const candidates: { x: number; y: number; align: "left" | "right" | "center" }[] = [
    { x: starX + radiusPx + gap, y: starY + 0.35 * fontSizePx, align: "left" },
    { x: starX - radiusPx - gap, y: starY + 0.35 * fontSizePx, align: "right" },
    { x: starX, y: starY - radiusPx - gap, align: "center" },
    { x: starX, y: starY + radiusPx + gap + 0.8 * fontSizePx, align: "center" },
  ];
  for (const candidate of candidates) {
    const x = candidate.align === "left"
      ? candidate.x - 2
      : candidate.align === "right"
        ? candidate.x - textWidth - 2
        : candidate.x - textWidth / 2 - 2;
    const box: Rect = {
      x,
      y: candidate.y - 0.8 * fontSizePx - 2,
      width: textWidth + 4,
      height: 1.05 * fontSizePx + 4,
    };
    const inside = box.x >= 0 && box.y >= 0
      && box.x + box.width <= viewport.width
      && box.y + box.height <= viewport.height;
    if (inside && !occupied.some((item) => rectsOverlap(item, box))) {
      return { ...candidate, box };
    }
  }
  return null;
}

export function magnitudeLimit(spanDeg: number): number {
  if (spanDeg >= 150) return 4.5;
  if (spanDeg > 80) return 5.2;
  return Infinity;
}

export function gridStep(spanDeg: number): [number, number] {
  if (spanDeg > 80) return [15, 10];
  if (spanDeg > 20) return [5, 5];
  if (spanDeg > 6) return [1, 1];
  return [0.25, 0.25];
}

export function meridianSegments(pixelsPerDegree: number, raStepDeg: number): SkyCoord[][] {
  const count = Math.round(360 / raStepDeg);
  const maximumMultiplier = Math.round(90 / raStepDeg);
  const multipliers = [1, 2, 3];
  for (let multiplier = 6; multiplier < maximumMultiplier; multiplier *= 2) {
    multipliers.push(multiplier);
  }
  if (!multipliers.includes(maximumMultiplier)) multipliers.push(maximumMultiplier);
  const ranks = Array.from({ length: count }, (_, index) => multipliers
    .filter((candidate) => candidate <= maximumMultiplier && index % candidate === 0)
    .at(-1) ?? 1);
  return Array.from({ length: count }, (_, index) => {
    const ra = wrapRa(index * raStepDeg);
    if (index % maximumMultiplier === 0) return [[ra, -90], [ra, 90]];
    let neighbourDistance = 1;
    while (neighbourDistance < maximumMultiplier) {
      const before = (index - neighbourDistance + count) % count;
      const after = (index + neighbourDistance) % count;
      if (ranks[before] >= ranks[index] || ranks[after] >= ranks[index]) break;
      neighbourDistance += 1;
    }
    const spacingDeg = neighbourDistance * raStepDeg;
    const latitude = Math.acos(Math.min(1, 14 / (spacingDeg * pixelsPerDegree))) / DEG;
    return [[ra, -latitude], [ra, latitude]];
  });
}

export interface SkyGridLine {
  id: string;
  coordinates: SkyCoord[];
}

export interface SkyGridLines {
  meridians: SkyGridLine[];
  parallels: SkyGridLine[];
}

function parallelCoordinates(decDeg: number, startRaDeg: number, spanRaDeg: number): SkyCoord[] {
  const sampleStep = Math.min(1, spanRaDeg / 8);
  const samples = Math.max(1, Math.ceil(spanRaDeg / sampleStep));
  return Array.from({ length: samples + 1 }, (_, index) => [
    wrapRa(startRaDeg + spanRaDeg * index / samples),
    decDeg,
  ]);
}

export function fullSkyGrid(view: SkyView, widthPx: number, heightPx: number): SkyGridLines {
  const [raStep, decStep] = gridStep(view.spanDeg);
  const meridians = meridianSegments(pxPerDegree(view, widthPx, heightPx), raStep)
    .map((coordinates, index) => ({ id: `m:${index}`, coordinates }));
  const parallels: SkyGridLine[] = [];
  for (let dec = Math.ceil(-90 / decStep) * decStep; dec < 90; dec += decStep) {
    if (dec <= -90 + 1e-9) continue;
    parallels.push({
      id: `p:${dec.toFixed(6)}`,
      coordinates: parallelCoordinates(dec, -180, 360 - 1e-6),
    });
  }
  return { meridians, parallels };
}

export function visibleRadiusDeg(view: SkyView, widthPx: number, heightPx: number): number {
  const [raStep, decStep] = gridStep(view.spanDeg);
  const scale = scaleForSpan(view.spanDeg, Math.min(widthPx, heightPx));
  const cornerRadius = Math.hypot(widthPx, heightPx) / 2;
  return Math.min(
    180,
    2 * Math.atan(cornerRadius / scale) / DEG + Math.max(raStep, decStep),
  );
}

export function visibleSkyGrid(view: SkyView, widthPx: number, heightPx: number): SkyGridLines {
  const [raStep, decStep] = gridStep(view.spanDeg);
  const radiusDeg = visibleRadiusDeg(view, widthPx, heightPx);
  const decMinimum = Math.max(-90, view.centre[1] - radiusDeg);
  const decMaximum = Math.min(90, view.centre[1] + radiusDeg);
  const includesPole = Math.abs(view.centre[1]) + radiusDeg >= 90;
  const raHalfRange = includesPole
    ? 180
    : Math.asin(Math.min(1, Math.sin(radiusDeg * DEG) / Math.cos(view.centre[1] * DEG))) / DEG;
  const allMeridians = meridianSegments(pxPerDegree(view, widthPx, heightPx), raStep);
  const meridians: SkyGridLine[] = [];
  for (let index = 0; index < allMeridians.length; index += 1) {
    const coordinates = allMeridians[index];
    const ra = coordinates[0][0];
    if (!includesPole && Math.abs(((ra - view.centre[0] + 540) % 360) - 180) > raHalfRange + 1e-9) continue;
    const minimum = Math.max(decMinimum, coordinates[0][1]);
    const maximum = Math.min(decMaximum, coordinates[1][1]);
    if (minimum > maximum) continue;
    meridians.push({ id: `m:${index}`, coordinates: [[ra, minimum], [ra, maximum]] });
  }

  const parallels: SkyGridLine[] = [];
  const firstParallel = Math.max(-90 + decStep, Math.ceil((decMinimum - 1e-9) / decStep) * decStep);
  for (let dec = firstParallel; dec <= decMaximum + 1e-9 && dec < 90; dec += decStep) {
    parallels.push({
      id: `p:${dec.toFixed(6)}`,
      coordinates: parallelCoordinates(
        dec,
        includesPole ? -180 : view.centre[0] - raHalfRange,
        includesPole ? 360 - 1e-6 : raHalfRange * 2,
      ),
    });
  }
  return { meridians, parallels };
}

const SCALE_STEPS: { deg: number; label: string }[] = [
  { deg: 60, label: "60°" }, { deg: 30, label: "30°" }, { deg: 20, label: "20°" },
  { deg: 10, label: "10°" }, { deg: 5, label: "5°" }, { deg: 2, label: "2°" },
  { deg: 1, label: "1°" }, { deg: 0.5, label: "30′" }, { deg: 1 / 6, label: "10′" },
  { deg: 1 / 12, label: "5′" }, { deg: 1 / 30, label: "2′" },
];

export function scaleBarStep(pixelsPerDegree: number): { deg: number; px: number; label: string } {
  const step = SCALE_STEPS.find((candidate) => candidate.deg * pixelsPerDegree <= 110) ?? SCALE_STEPS.at(-1)!;
  return { ...step, px: step.deg * pixelsPerDegree };
}

export function showsAllNames(spanDeg: number): boolean {
  return spanDeg < 150;
}
