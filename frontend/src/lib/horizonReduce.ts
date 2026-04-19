import type { HorizonPoint } from "@/components/locations/HorizonChart";

/**
 * Douglas-Peucker simplification for horizon data.
 *
 * Uses vertical altitude distance from the straight-line interpolation
 * between two anchor points as the error metric. Preserves the altitude
 * extremes (tall obstructions, low clearings) to within ``epsilonDeg``.
 * Iterative implementation — safe on long point lists.
 *
 * Points must be sorted ascending by azimuth on input; the output is the
 * same subset in the same order.
 */
export function reduceHorizon(points: HorizonPoint[], epsilonDeg: number): HorizonPoint[] {
  if (points.length < 3 || epsilonDeg <= 0) return [...points];
  const keep = new Array<boolean>(points.length).fill(false);
  keep[0] = true;
  keep[points.length - 1] = true;

  const stack: Array<[number, number]> = [[0, points.length - 1]];
  while (stack.length > 0) {
    const pair = stack.pop();
    if (!pair) break;
    const [start, end] = pair;
    if (end <= start + 1) continue;
    const a = points[start];
    const b = points[end];
    let maxD = 0;
    let index = -1;
    for (let i = start + 1; i < end; i++) {
      const d = verticalAltDistance(points[i], a, b);
      if (d > maxD) {
        maxD = d;
        index = i;
      }
    }
    if (index !== -1 && maxD > epsilonDeg) {
      keep[index] = true;
      stack.push([start, index]);
      stack.push([index, end]);
    }
  }
  return points.filter((_, i) => keep[i]);
}

/**
 * Absolute vertical difference between ``p.altitude_deg`` and the
 * altitude predicted by linearly interpolating between ``a`` and ``b`` at
 * ``p.azimuth_deg``. Horizon simplification cares about altitude error,
 * not geometric perpendicular distance.
 */
function verticalAltDistance(p: HorizonPoint, a: HorizonPoint, b: HorizonPoint): number {
  const dAz = b.azimuth_deg - a.azimuth_deg;
  if (dAz === 0) return Math.abs(p.altitude_deg - a.altitude_deg);
  const t = (p.azimuth_deg - a.azimuth_deg) / dAz;
  const interp = a.altitude_deg + t * (b.altitude_deg - a.altitude_deg);
  return Math.abs(p.altitude_deg - interp);
}
