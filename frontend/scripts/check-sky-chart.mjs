import assert from "node:assert/strict";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import * as d3 from "d3";
import ts from "typescript";

const root = process.cwd();
const cache = path.join(root, "node_modules/.cache/sky-check");
await mkdir(cache, { recursive: true });
for (const name of ["geometry", "text", "palette", "draw"]) {
  const source = await readFile(path.join(root, `src/lib/skyChart/${name}.ts`), "utf8");
  const output = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
    fileName: `${name}.ts`,
  }).outputText
    .replace(/from "\.\/(geometry|text|palette)"/g, 'from "./$1.mjs"')
    .replace(/from "\.\.\/constellations"/g, 'from "./constellations.mjs"');
  await writeFile(path.join(cache, `${name}.mjs`), output);
}
{
  const source = await readFile(path.join(root, "src/lib/constellations.ts"), "utf8");
  const output = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
    fileName: "constellations.ts",
  }).outputText;
  await writeFile(path.join(cache, "constellations.mjs"), output);
}

const g = await import(pathToFileURL(path.join(cache, "geometry.mjs")));
const text = await import(pathToFileURL(path.join(cache, "text.mjs")));
const { SKY_PALETTES } = await import(pathToFileURL(path.join(cache, "palette.mjs")));
const { drawSkyChart } = await import(pathToFileURL(path.join(cache, "draw.mjs")));
const sky = JSON.parse(await readFile(path.join(root, "src/data/sky/sky.json"), "utf8"));
const near = (actual, expected, tolerance = 1e-9, message = "") => assert.ok(Math.abs(actual - expected) <= tolerance, `${message}: ${actual} vs ${expected}`);
const pointNear = (actual, expected, tolerance, message = "") => {
  near(actual[0], expected[0], tolerance, `${message} x`);
  near(actual[1], expected[1], tolerance, `${message} y`);
};
const angularRaDelta = (a, b) => Math.abs(((a - b + 540) % 360) - 180);

assert.equal(sky.names.length, 186);
assert.equal(sky.names.filter(([index]) => sky.stars[index][2] <= 1.5).length, 23);
assert.deepEqual(sky.names[0], [0, "Sirius"]);
assert.ok(sky.names.every(([index], position) => index < sky.stars.length
  && sky.stars[index][2] <= 3.5
  && (position === 0 || sky.names[position - 1][0] < index)));

near(g.scaleForSpan(90, 900), 450 / Math.tan(Math.PI / 8), 1e-9, "scaleForSpan");
assert.deepEqual(g.trimSegment([0, 0], [100, 0], 5, 8), [[5, 0], [92, 0]]);
assert.deepEqual(g.trimSegment([0, 0], [10, 0], 5, 5), [[4, 0], [6, 0]]);
assert.equal(g.segmentTouchesRect([-30, 50], [130, 50], 100, 100, 20), true);
assert.equal(g.segmentTouchesRect([-30, -30], [130, -30], 100, 100, 20), false);
assert.equal(g.segmentTouchesRect([50, 50], [130, 130], 100, 100, 20), true);
{
  const candidate = (time, point = [100, 100], movementPx = 0, blocked = false) => ({
    time, point, movementPx, blocked, durationMs: 100,
  });
  const first = g.classifyTap(candidate(100), null);
  assert.equal(first.kind, "tap");
  assert.equal(g.classifyTap(candidate(250, [110, 110]), first.lastTap).kind, "double");

  const beforeDrag = g.classifyTap(candidate(100), null);
  const drag = g.classifyTap(candidate(200, [130, 100], 30), beforeDrag.lastTap);
  assert.deepEqual(drag, { kind: "none", lastTap: null });
  assert.equal(g.classifyTap(candidate(300), drag.lastTap).kind, "tap");

  const beforePinch = g.classifyTap(candidate(100), null);
  const pinchRelease = g.classifyTap(candidate(200, [100, 100], 0, true), beforePinch.lastTap);
  assert.deepEqual(pinchRelease, { kind: "none", lastTap: null });

  const separated = g.classifyTap(candidate(500), first.lastTap);
  assert.equal(separated.kind, "tap");
}
near(g.starRadius(0, 10), 4.96);
near(g.starRadius(6, 180), 0.55);
near(g.starRadius(2, 84), 2.728);
assert.deepEqual([180, 150, 100, 80, 10].map(g.magnitudeLimit), [4.5, 4.5, 5.2, Infinity, Infinity]);
assert.deepEqual([180, 150, 120, 90, 20, 0.5].map(g.starNameMagnitudeLimit), [1.5, 1.5, 2.5, 3.5, 3.5, 3.5]);
near(g.starNameMagnitudeLimit(149.9), 1.5 + 0.2 / 60, 1e-12, "star-name limit just below 150");
assert.deepEqual([100, 50, 10, 5].map(g.gridStep), [[15, 10], [5, 5], [1, 1], [0.25, 0.25]]);
{
  const star = [50, 50];
  const viewport = { width: 100, height: 100 };
  const right = g.placeStarName(star, 2, 20, 10, [], viewport);
  assert.equal(right.align, "left");
  assert.equal(right.x, 56);
  const rightBlock = { x: 70, y: 50, width: 1, height: 1 };
  const left = g.placeStarName(star, 2, 20, 10, [rightBlock], viewport);
  assert.equal(left.align, "right");
  const leftBlock = { x: 30, y: 50, width: 1, height: 1 };
  const above = g.placeStarName(star, 2, 20, 10, [rightBlock, leftBlock], viewport);
  assert.equal(above.align, "center");
  assert.ok(above.y < star[1]);
  const aboveBlock = { x: 50, y: 38, width: 1, height: 1 };
  const below = g.placeStarName(star, 2, 20, 10, [rightBlock, leftBlock, aboveBlock], viewport);
  assert.equal(below.align, "center");
  assert.ok(below.y > star[1]);
  const belowBlock = { x: 50, y: 66, width: 1, height: 1 };
  assert.equal(g.placeStarName(star, 2, 20, 10, [rightBlock, leftBlock, aboveBlock, belowBlock], viewport), null);
  for (const edgeStar of [[1, 50], [99, 50], [50, 1], [50, 99]]) {
    const placement = g.placeStarName(edgeStar, 1, 12, 10, [], viewport);
    assert.ok(placement, `no placement at canvas edge ${edgeStar}`);
    assert.ok(placement.box.x >= 0 && placement.box.y >= 0);
    assert.ok(placement.box.x + placement.box.width <= viewport.width);
    assert.ok(placement.box.y + placement.box.height <= viewport.height);
  }
}
{
  const view = { centre: [45, 89], spanDeg: 7 };
  const pixelsPerDegree = g.pxPerDegree(view, 1000, 750);
  const segments = g.meridianSegments(pixelsPerDegree, 1);
  for (const segment of segments) {
    const latitude = segment[1][1];
    if (latitude >= 89.999999) continue;
    const continuing = segments.filter((other) => other !== segment && other[1][1] + 1e-9 >= latitude);
    const nearestRa = Math.min(...continuing.map((other) => angularRaDelta(segment[0][0], other[0][0])));
    const separationPx = nearestRa * Math.cos(latitude * Math.PI / 180) * pixelsPerDegree;
    assert.ok(separationPx >= 14 - 1e-7, `meridian separation ${separationPx} px at ${latitude}°`);
  }
}
{
  const view = { centre: [210, 40], spanDeg: 60 };
  const segments = g.meridianSegments(g.pxPerDegree(view, 1000, 750), 5);
  for (const ra of [0, 90, 180, 270]) {
    const segment = segments.find((candidate) => candidate[0][0] === ra);
    assert.deepEqual(segment, [[ra, -90], [ra, 90]]);
  }
}
{
  const view = { centre: [210.8, 54.35], spanDeg: 2 };
  const grid = g.visibleSkyGrid(view, 1440, 796);
  assert.ok(grid.meridians.length <= 80, `visible meridians at S=2: ${grid.meridians.length}`);
  assert.ok(grid.parallels.length <= 80, `visible parallels at S=2: ${grid.parallels.length}`);
}
{
  const view = { centre: [210.8, 54.35], spanDeg: 180 };
  const visible = g.visibleSkyGrid(view, 1440, 796);
  const full = g.fullSkyGrid(view, 1440, 796);
  assert.equal(visible.meridians.length, full.meridians.length);
  assert.equal(visible.parallels.length, full.parallels.length);
}
const gridLineTouchesCanvas = (line, view, width, height) => {
  const projection = g.makeProjection(view, width, height);
  const samples = [];
  if (line.id.startsWith("m:")) {
    const ra = line.coordinates[0][0];
    const start = line.coordinates[0][1];
    const end = line.coordinates[1][1];
    for (let dec = start; dec <= end + 1e-9; dec += 0.5) samples.push([ra, Math.min(dec, end)]);
  } else {
    const dec = line.coordinates[0][1];
    for (let ra = 0; ra < 360; ra += 0.5) samples.push([ra, dec]);
  }
  return samples.some((point) => {
    const projected = projection(point);
    return projected && projected[0] >= 0 && projected[0] <= width && projected[1] >= 0 && projected[1] <= height;
  });
};
for (const spanDeg of [2, 20, 60]) {
  for (const centre of [[210.8, 54.35], [0.2, 30], [45, 89], [160.9, -59.87]]) {
    const view = { centre, spanDeg };
    const visible = g.visibleSkyGrid(view, 1440, 796);
    const visibleIds = new Set([...visible.meridians, ...visible.parallels].map((line) => line.id));
    const full = g.fullSkyGrid(view, 1440, 796);
    for (const line of [...full.meridians, ...full.parallels]) {
      if (gridLineTouchesCanvas(line, view, 1440, 796)) {
        assert.ok(visibleIds.has(line.id), `missing visible grid line ${line.id} at S=${spanDeg}, centre=${centre}`);
      }
    }
  }
}
assert.deepEqual(g.scaleBarStep(3), { deg: 30, px: 90, label: "30°" });
assert.deepEqual(g.scaleBarStep(300), { deg: 1 / 6, px: 50, label: "10′" });
near(g.scaleBarStep(10_000).px, 1000 / 3, 1e-9);
assert.equal(g.scaleBarStep(10_000).label, "2′");
assert.equal(g.showsAllNames(149.9), true);
assert.equal(g.showsAllNames(150), false);

const anchorResidual = (view, from, to, span = view.spanDeg) => {
  const grabbed = g.makeProjection(view, 1000, 750).invert(from);
  const result = g.anchorView(view, span, grabbed, to, 1000, 750);
  const projected = g.makeProjection(result.view, 1000, 750)(grabbed);
  const actual = Math.hypot(projected[0] - to[0], projected[1] - to[1]);
  near(result.residualPx, actual, 1e-7, "reported anchor residual");
  return { ...result, grabbed };
};

const reachableAnchors = [
  [60, [210, 40], [100, 100], [160, 140]], [60, [210, 40], [900, 650], [850, 600]],
  [60, [210, 40], [500, 375], [700, 375]], [60, [359, 20], [100, 100], [160, 140]],
  [60, [359, 20], [900, 650], [850, 600]], [60, [359, 20], [500, 375], [700, 375]],
  [60, [10, -80], [100, 100], [160, 140]], [60, [10, -80], [900, 650], [850, 600]],
  [180, [210, 40], [100, 100], [160, 140]], [180, [359, 20], [100, 100], [160, 140]],
  [180, [359, 20], [500, 375], [700, 375]], [180, [120, 85], [900, 650], [850, 600]],
];
let maximumReachableAnchor = 0;
for (const [span, centre, from, to] of reachableAnchors) {
  const result = anchorResidual({ centre, spanDeg: span }, from, to);
  maximumReachableAnchor = Math.max(maximumReachableAnchor, result.residualPx);
  assert.ok(result.residualPx <= 0.5, `reachable anchor S=${span} c=${centre} ${from}->${to}: ${result.residualPx}`);
  assert.ok(result.view.centre[0] >= 0 && result.view.centre[0] < 360);
  assert.ok(result.view.centre.every(Number.isFinite));
}
console.log(`anchor reachable maximum residual: ${maximumReachableAnchor.toFixed(4)} px`);

const analyticProject = (centre, point, span) => {
  const rad = Math.PI / 180;
  const lon0 = centre[0] * rad;
  const lat0 = centre[1] * rad;
  const lon = point[0] * rad;
  const lat = point[1] * rad;
  const cosine = Math.sin(lat0) * Math.sin(lat) + Math.cos(lat0) * Math.cos(lat) * Math.cos(lon - lon0);
  const factor = 1 / Math.max(1e-12, 1 + cosine);
  const x = factor * Math.cos(lat) * Math.sin(lon - lon0);
  const y = factor * (Math.cos(lat0) * Math.sin(lat) - Math.sin(lat0) * Math.cos(lat) * Math.cos(lon - lon0));
  const scale = g.scaleForSpan(span, 750);
  return [500 - scale * x, 375 - scale * y];
};
const bruteForceAnchor = (grabbed, pointer, span) => {
  let best = Infinity;
  for (let latitude = -90; latitude <= 90; latitude += 0.5) {
    for (let longitude = 0; longitude < 360; longitude += 0.5) {
      const projected = analyticProject([longitude, latitude], grabbed, span);
      best = Math.min(best, Math.hypot(projected[0] - pointer[0], projected[1] - pointer[1]));
    }
  }
  return best;
};
const bestEffortAnchors = [
  [180, [210, 40], [900, 650], [850, 600], 17.55],
  [180, [210, 40], [500, 375], [700, 375], 25.13],
  [180, [359, 20], [900, 650], [850, 600], 27.61],
  [60, [120, 85], [500, 375], [700, 375], 138.90],
];
for (const [span, centre, from, to, expectedGrid] of bestEffortAnchors) {
  const result = anchorResidual({ centre, spanDeg: span }, from, to);
  const brute = bruteForceAnchor(result.grabbed, to, span);
  near(brute, expectedGrid, 0.2, `brute-force anchor S=${span} c=${centre}`);
  assert.ok(result.residualPx <= brute + 1, `best-effort anchor S=${span} c=${centre}: ${result.residualPx} vs ${brute}`);
  console.log(`anchor best effort S=${span} c=${centre}: ${result.residualPx.toFixed(4)} px (0.5° grid ${brute.toFixed(4)} px)`);
}

{
  const view = { centre: [120, 20], spanDeg: 60 };
  const moved = g.panViewBy(view, 40, -25, 1000, 750);
  const projected = g.makeProjection(moved, 1000, 750)(view.centre);
  pointNear(projected, [540, 350], 0.5);
  console.log(`panViewBy residual: ${Math.hypot(projected[0] - 540, projected[1] - 350).toFixed(4)} px`);
}
let maximumExactZoom = 0;
for (const factor of [2, 0.5]) {
  for (const at of [[100, 100], [900, 650], [500, 375]]) {
    if (factor === 0.5 && at[0] === 100) continue;
    const view = { centre: [210, 40], spanDeg: 60 };
    const grabbed = g.makeProjection(view, 1000, 750).invert(at);
    const zoomed = g.zoomViewAt(view, factor, at, 1000, 750);
    const projected = g.makeProjection(zoomed, 1000, 750)(grabbed);
    pointNear(projected, at, 0.5, `zoom ${factor}`);
    maximumExactZoom = Math.max(maximumExactZoom, Math.hypot(projected[0] - at[0], projected[1] - at[1]));
  }
}
console.log(`zoom reachable maximum residual: ${maximumExactZoom.toFixed(4)} px`);
{
  const view = { centre: [210, 40], spanDeg: 60 };
  const at = [100, 100];
  const grabbed = g.makeProjection(view, 1000, 750).invert(at);
  const zoomed = g.zoomViewAt(view, 0.5, at, 1000, 750);
  const projected = g.makeProjection(zoomed, 1000, 750)(grabbed);
  const residual = Math.hypot(projected[0] - at[0], projected[1] - at[1]);
  const brute = bruteForceAnchor(grabbed, at, 120);
  assert.ok(residual <= brute + 1, `best-effort zoom-out: ${residual} vs ${brute}`);
  console.log(`zoom best effort: ${residual.toFixed(4)} px (0.5° grid ${brute.toFixed(4)} px)`);
}
assert.equal(g.zoomViewAt({ centre: [0, 0], spanDeg: 0.1 }, 2, [500, 375], 1000, 750).spanDeg, 0.1);
assert.equal(g.zoomViewAt({ centre: [0, 0], spanDeg: 180 }, 0.5, [500, 375], 1000, 750).spanDeg, 180);

for (const size of [[1000, 750], [312, 234]]) {
  for (const code of ["UMa", "Peg", "Oct", "Hya", "Ser"]) {
    const rings = sky.boundaries[code];
    const centre = sky.labels[code].points[0].at;
    const view = g.fitConstellationView(rings, centre, ...size);
    assert.ok(view.spanDeg >= 20 && view.spanDeg <= 120, `${code} span ${view.spanDeg}`);
    const projection = g.makeProjection(view, ...size);
    for (const point of rings.flat()) {
      const projected = projection(point);
      assert.ok(projected && projected[0] >= size[0] * 0.08 - 1 && projected[0] <= size[0] * 0.92 + 1 && projected[1] >= size[1] * 0.08 - 1 && projected[1] <= size[1] * 0.92 + 1, `${code} fit at ${size}: ${projected}`);
    }
  }
  const crux = g.fitConstellationView(sky.boundaries.Cru, sky.labels.Cru.points[0].at, ...size);
  near(crux.spanDeg, 20, 1e-9, "Crux minimum fit");
}
assert.equal(g.pictureView([0, 0], 40).spanDeg, 140);
assert.equal(g.pictureView([0, 0], 60).spanDeg, 180);
assert.equal(g.pictureView([0, 0], 0.02).spanDeg, 0.1);

for (const ring of [
  [[10, 0], [13.5, 0], [13.5, 2], [10, 0]],
  [[359.5, 10], [1.5, 10], [1.5, 11], [359.5, 10]],
]) {
  const dense = g.densifyRing(ring);
  assert.deepEqual(dense.at(-1), dense[0]);
  for (const vertex of ring) assert.ok(dense.some((point) => point[0] === vertex[0] && point[1] === vertex[1]));
  for (let index = 1; index < dense.length; index += 1) {
    assert.ok(angularRaDelta(dense[index][0], dense[index - 1][0]) <= 0.2500001);
    assert.ok(Math.abs(dense[index][1] - dense[index - 1][1]) <= 0.2500001);
    assert.ok(dense[index][0] >= 0 && dense[index][0] < 360);
  }
}

{
  const width = 1440;
  const height = 796;
  const ring = g.densifyRing(sky.boundaries.UMa[0], 0.25);
  const centrePoints = [ring[37], ring[200], ring[Math.floor(ring.length / 2)]];
  for (const point of centrePoints) {
    for (const spanDeg of [0.1, 0.5, 2, 20]) {
      const view = { centre: [point[0] + 0.01, point[1] + 0.005], spanDeg };
      const projection = g.makeProjection(view, width, height);
      const radius = g.visibleRadiusDeg(view, width, height);
      const runs = g.visibleLineRuns(ring, view.centre, radius);
      const kept = new Set();
      for (const run of runs) {
        for (let index = 1; index < run.length; index += 1) {
          kept.add(`${run[index - 1][0]},${run[index - 1][1]}|${run[index][0]},${run[index][1]}`);
        }
      }
      let onCanvasSegments = 0;
      for (let index = 1; index < ring.length; index += 1) {
        const start = ring[index - 1];
        const end = ring[index];
        const interpolate = d3.geoInterpolate(start, end);
        const touchesCanvas = Array.from({ length: 21 }, (_, sample) => interpolate(sample / 20)).some((sampled) => {
          const projected = projection(sampled);
          return projected && projected[0] >= 0 && projected[0] <= width
            && projected[1] >= 0 && projected[1] <= height;
        });
        if (!touchesCanvas) continue;
        onCanvasSegments += 1;
        assert.ok(
          kept.has(`${start[0]},${start[1]}|${end[0]},${end[1]}`),
          `boundary culling dropped visible segment at S=${spanDeg}: ${start} -> ${end}`,
        );
      }
      assert.ok(onCanvasSegments > 0, `boundary culling fixture is vacuous at S=${spanDeg}, centre=${view.centre}`);
      console.log(`boundary culling S=${spanDeg} centre=${view.centre}: kept all ${onCanvasSegments} on-canvas segments`);
    }
  }
}

const wcsCases = [
  {
    name: "unrotated", wcs: { crval1: 180, crval2: 0, crpix1: 500.5, crpix2: 250.5, cd1_1: -0.001, cd1_2: 0, cd2_1: 0, cd2_2: -0.001, width: 1000, height: 500 },
    points: [[[-0.5, -0.5], [180.49999, 0.24999]], [[999.5, -0.5], [179.50001, 0.24999]], [[999.5, 499.5], [179.50001, -0.24999]], [[-0.5, 499.5], [180.49999, -0.24999]], [[499.5, -0.5], [180, 0.25]], [[499.5, 249.5], [180, 0]]],
  },
  {
    name: "rotated", wcs: { crval1: 83.82, crval2: -5.39, crpix1: 500.5, crpix2: 250.5, cd1_1: 0, cd1_2: -0.001, cd2_1: -0.001, cd2_2: 0, width: 1000, height: 500 },
    points: [[[-0.5, -0.5], [84.07090, -4.88997]], [[999.5, -0.5], [84.07132, -5.88993]], [[999.5, 499.5], [83.56868, -5.88993]], [[-0.5, 499.5], [83.56910, -4.88997]], [[499.5, -0.5], [84.07111, -5.38995]]],
  },
  {
    name: "ra0", wcs: { crval1: 0.2, crval2: 30, crpix1: 1000.5, crpix2: 500.5, cd1_1: -0.0005, cd1_2: 0, cd2_1: 0, cd2_2: -0.0005, width: 2000, height: 1000 },
    points: [[[-0.5, -0.5], [0.77879, 30.24873]], [[1999.5, -0.5], [359.62121, 30.24873]], [[1999.5, 999.5], [359.62412, 29.74875]], [[-0.5, 999.5], [0.77588, 29.74875]]],
  },
  {
    name: "pole", wcs: { crval1: 45, crval2: 89, crpix1: 1000.5, crpix2: 1000.5, cd1_1: -0.001, cd1_2: 0, cd2_1: 0, cd2_2: -0.001, width: 2000, height: 2000 },
    points: [[[-0.5, -0.5], [134.99418, 89.00025]], [[1999.5, -0.5], [315.00582, 89.00025]], [[1999.5, 1999.5], [18.43262, 87.76423]], [[-0.5, 1999.5], [71.56738, 87.76423]], [[999.5, -0.5], [45, 89.9999]]],
  },
  {
    name: "mirrored", wcs: { crval1: 210.8, crval2: 54.35, crpix1: 1500.5, crpix2: 1000.5, cd1_1: 0.0002, cd1_2: 0, cd2_1: 0, cd2_2: -0.0002, width: 3000, height: 2000 },
    points: [[[-0.5, -0.5], [210.28277, 54.54890]], [[2999.5, -0.5], [211.31723, 54.54890]], [[2999.5, 1999.5], [211.31222, 54.14891]], [[-0.5, 1999.5], [210.28778, 54.14891]], [[1499.5, -0.5], [210.8, 54.55]]],
  },
];
for (const test of wcsCases) {
  for (const [pixel, expected] of test.points) {
    const actual = g.tanPixelToSky(test.wcs, ...pixel);
    assert.ok(angularRaDelta(actual[0], expected[0]) <= 1e-4, `${test.name} RA ${actual[0]}`);
    near(actual[1], expected[1], 1e-4, `${test.name} Dec`);
    assert.ok(actual[0] >= 0 && actual[0] < 360);
  }
}
const outline = g.pictureOutline(wcsCases[0].wcs);
assert.equal(outline.length, 32);
for (const [index, expected] of [0, 1, 2, 3].map((corner, index) => [index * 8, wcsCases[0].points[corner][1]])) {
  assert.ok(angularRaDelta(outline[index][0], expected[0]) < 1e-4);
  near(outline[index][1], expected[1], 1e-4);
}

const src = [[0, 0], [1000, 0], [0, 500]];
const dst = [[100, 100], [300, 100], [100, 200]];
assert.deepEqual(g.triangleAffine(src, dst), [0.2, 0, 0, 0.2, 100, 100]);
for (const mirrored of [dst, [[300, 100], [100, 100], [300, 200]]]) {
  const affine = g.triangleAffine(src, mirrored);
  if (mirrored !== dst) assert.ok(affine[0] * affine[3] - affine[1] * affine[2] < 0);
  src.forEach(([x, y], index) => pointNear([affine[0] * x + affine[2] * y + affine[4], affine[1] * x + affine[3] * y + affine[5]], mirrored[index], 1e-9));
}
const grown = g.growTriangle([[0, 0], [100, 0], [0, 100]], 0.6);
near(grown[0][1], -0.6, 1e-9);
near(grown[1][0] + grown[1][1] - 100, 0.6 * Math.sqrt(2), 1e-9);
near(grown[2][0], -0.6, 1e-9);
const sliver = [[0, 0], [100, 0], [100, 0.5]];
g.growTriangle(sliver, 0.6).forEach((point, index) => assert.ok(Math.hypot(point[0] - sliver[index][0], point[1] - sliver[index][1]) <= 3.0000001));
assert.deepEqual(g.sourceRect([[-0.6, -0.6], [10.6, -0.6], [-0.6, 10.6]], [1, 0, 0, 1, 0, 0], 20, 20), { sx: 0, sy: 0, sw: 13, sh: 13 });

const meshCases = [
  ["counterexample", { crval1: 70, crval2: 0, crpix1: 2000.5, crpix2: 1350.5, cd1_1: -14.86 / 4000, cd1_2: 0, cd2_1: 0, cd2_2: -9.9 / 2700, width: 4000, height: 2700 }, [0, 0], 180],
  ["wide-180", { crval1: 0, crval2: 0, crpix1: 2000.5, crpix2: 1350.5, cd1_1: -0.01, cd1_2: 0, cd2_1: 0, cd2_2: -0.01, width: 4000, height: 2700 }, [0, 0], 180],
  ["wide-60", { crval1: 0, crval2: 0, crpix1: 2000.5, crpix2: 1350.5, cd1_1: -0.01, cd1_2: 0, cd2_1: 0, cd2_2: -0.01, width: 4000, height: 2700 }, [0, 0], 60],
  ["medium-20", { crval1: 0, crval2: 0, crpix1: 2000.5, crpix2: 1350.5, cd1_1: -14.86 / 4000, cd1_2: 0, cd2_1: 0, cd2_2: -9.9 / 2700, width: 4000, height: 2700 }, [0, 0], 20],
  ["medium-10", { crval1: 0, crval2: 0, crpix1: 2000.5, crpix2: 1350.5, cd1_1: -14.86 / 4000, cd1_2: 0, cd2_1: 0, cd2_2: -9.9 / 2700, width: 4000, height: 2700 }, [0, 0], 10],
];
const wide = meshCases[1][1];
const offCentre = g.tanPixelToSky(wide, wide.width / 3, wide.height / 3);
meshCases.push(["wide-offset-2", wide, offCentre, 2], ["wide-offset-0.1", wide, offCentre, 0.1]);
const wideEdge = { ...wide, crval1: 105 };
{
  const centre = [0, 0];
  const projection = g.makeProjection({ centre, spanDeg: 180 }, 1440, 900);
  const outline = g.pictureOutline(wideEdge);
  const onCanvas = outline.filter((coord) => {
    const projected = projection(coord);
    return projected && projected[0] >= 0 && projected[0] <= 1440
      && projected[1] >= 0 && projected[1] <= 900;
  });
  const farCorners = [0, 8, 16, 24].filter((index) => d3.geoDistance(outline[index], centre) > 120 * Math.PI / 180);
  assert.ok(onCanvas.length >= 10, `wide edge outline points on canvas: ${onCanvas.length}`);
  assert.ok(farCorners.length >= 1, "wide edge fixture has no corner beyond 120°");
}
meshCases.push(["wide-edge-180", wideEdge, [0, 0], 180]);
const timedWide = { ...wide, crval1: 83.8 };
meshCases.push(
  ["wide-view-190", timedWide, [190, 0], 180],
  ["wide-view-175-10", timedWide, [175, 10], 180],
);
const angle = 37 * Math.PI / 180;
meshCases.push(["rotated", { crval1: 30, crval2: 20, crpix1: 2000.5, crpix2: 1350.5, cd1_1: -0.0003 * Math.cos(angle), cd1_2: 0.0003 * Math.sin(angle), cd2_1: 0.0003 * Math.sin(angle), cd2_2: 0.0003 * Math.cos(angle), width: 4000, height: 2700 }, [30, 20], 2]);
const m101Angle = -38 * Math.PI / 180;
const m101ScaleX = 0.6 / 4000;
const m101ScaleY = 0.38 / 2700;
const m101 = {
  crval1: 210.8, crval2: 54.35, crpix1: 2000.5, crpix2: 1350.5,
  cd1_1: -m101ScaleX * Math.cos(m101Angle), cd1_2: m101ScaleY * Math.sin(m101Angle),
  cd2_1: m101ScaleX * Math.sin(m101Angle), cd2_2: m101ScaleY * Math.cos(m101Angle),
  width: 4000, height: 2700,
};
for (const span of [2, 0.5, 0.1]) meshCases.push([`m101-${span}`, m101, [210.8, 54.35], span]);
const round4 = { crval1: 0, crval2: 0, crpix1: 2000.5, crpix2: 1350.5, cd1_1: 0.01, cd1_2: 0, cd2_1: 0, cd2_2: -0.01, width: 4000, height: 2700 };
for (const span of [0.5, 0.1]) meshCases.push([`round4-${span}`, round4, [353.3631769533, 9.4128123270], span]);

for (const [name, wcs, centre, spanDeg] of meshCases) {
  const view = { centre, spanDeg };
  const projection = g.makeProjection(view, 1440, 900);
  const project = (coord) => projection(coord);
  const mesh = g.adaptiveMesh({
    wcs, imageW: 4000, imageH: 2700, project,
    isFar: (coord) => d3.geoDistance(coord, centre) > 120 * Math.PI / 180,
    isWide: (coord) => d3.geoDistance(coord, centre) > 90 * Math.PI / 180,
    viewport: { width: 1440, height: 900 },
  });
  assert.ok(mesh.length > 0, `${name} mesh is empty`);
  let maximum = 0;
  let nearMaximum = 0;
  let wideMaximum = 0;
  let projectedCentroids = 0;
  for (const triangle of mesh) {
    const sourceCentroid = [triangle.src.reduce((sum, point) => sum + point[0], 0) / 3, triangle.src.reduce((sum, point) => sum + point[1], 0) / 3];
    const x = sourceCentroid[0] * wcs.width / 4000 - 0.5;
    const y = sourceCentroid[1] * wcs.height / 2700 - 0.5;
    const exact = project(g.tanPixelToSky(wcs, x, y));
    if (!exact) continue;
    projectedCentroids += 1;
    const affine = g.triangleAffine(triangle.src, triangle.dst);
    const estimated = [affine[0] * sourceCentroid[0] + affine[2] * sourceCentroid[1] + affine[4], affine[1] * sourceCentroid[0] + affine[3] * sourceCentroid[1] + affine[5]];
    const residual = Math.hypot(exact[0] - estimated[0], exact[1] - estimated[1]);
    const skyVertices = triangle.src.map(([sourceX, sourceY]) => g.tanPixelToSky(
      wcs,
      sourceX * wcs.width / 4000 - 0.5,
      sourceY * wcs.height / 2700 - 0.5,
    ));
    const within90 = skyVertices.every((coord) => d3.geoDistance(coord, centre) <= 90 * Math.PI / 180);
    assert.ok(residual <= (within90 ? 0.5 : 1.5), `${name} mesh residual ${residual} (${within90 ? "near" : "wide"})`);
    maximum = Math.max(maximum, residual);
    if (within90) nearMaximum = Math.max(nearMaximum, residual);
    else wideMaximum = Math.max(wideMaximum, residual);
  }
  assert.ok(projectedCentroids > 0, `${name} has no projected triangle centroids`);
  assert.ok(mesh.length <= 1024, `${name} triangle budget ${mesh.length}`);
  if (name.startsWith("m101-")) assert.ok(mesh.length <= 8, `${name} triangle target ${mesh.length}`);
  if (name.startsWith("wide-offset")) pointNear(project(offCentre), [720, 450], 0.5, name);
  console.log(`mesh ${name}: ${mesh.length} triangles, max centroid residual ${maximum.toFixed(4)} px (near ${nearMaximum.toFixed(4)}, wide ${wideMaximum.toFixed(4)})`);
}

function recordingContext() {
  let state = {
    fillStyle: "#000000", strokeStyle: "#000000", font: "10px sans-serif",
    textAlign: "start", lineWidth: 1, lineJoin: "miter", globalAlpha: 1,
  };
  const stack = [];
  const records = [];
  const methods = {
    save: () => stack.push({ ...state }),
    restore: () => { state = stack.pop() ?? state; },
    measureText: (value) => ({ width: String(value).length * 6 }),
    fillText: (value, x, y) => records.push({
      kind: "fill", text: String(value), x, y, ...state,
    }),
    strokeText: (value, x, y) => records.push({
      kind: "stroke", text: String(value), x, y, ...state,
    }),
  };
  const context = new Proxy({}, {
    get: (_target, property) => {
      if (property === "records") return records;
      if (property in methods) return methods[property];
      if (property in state) return state[property];
      return () => {};
    },
    set: (_target, property, value) => {
      state[property] = value;
      return true;
    },
  });
  return context;
}

const fixtureWcs = (ra, dec, scale = 0.00001, angleDeg = 0) => {
  const angleRad = angleDeg * Math.PI / 180;
  return {
    crval1: ra, crval2: dec, crpix1: 500.5, crpix2: 350.5,
    cd1_1: -scale * Math.cos(angleRad), cd1_2: scale * Math.sin(angleRad),
    cd2_1: scale * Math.sin(angleRad), cd2_2: scale * Math.cos(angleRad),
    width: 1000, height: 700,
  };
};
const renderFixture = ({
  centre, spanDeg, targetCode = "UMa", mode = "full", wcs = fixtureWcs(120, -60), data = sky, reserved,
}) => {
  const context = recordingContext();
  drawSkyChart(context, {
    data,
    view: { centre, spanDeg },
    palette: SKY_PALETTES.night,
    fontFamily: "Test Sans",
    targetCode,
    wcs,
    pictureCentre: [wcs.crval1, wcs.crval2],
    image: null,
    imageSize: null,
    label: "Test target",
    mode,
    reserved,
  }, { width: 1440, height: 796, dpr: 1 });
  return context.records;
};
const starNameRecords = (records) => records.filter((record) => record.kind === "fill"
  && record.fillStyle === SKY_PALETTES.night.starNames);

const brightNames = new Set(sky.names
  .filter(([index]) => sky.stars[index][2] <= 1.5)
  .map(([_index, name]) => name));
const wholeSkyNames = starNameRecords(renderFixture({ centre: [0, 0], spanDeg: 180 }));
assert.ok(wholeSkyNames.length > 0);
assert.ok(wholeSkyNames.every((record) => brightNames.has(record.text)));

const dubheIndex = sky.names.find(([_, name]) => name === "Dubhe")[0];
const dubhe = sky.stars[dubheIndex].slice(0, 2);
const dipperNames = new Set(["Dubhe", "Merak", "Phecda", "Megrez", "Alioth", "Mizar", "Alkaid"]);
const umaRecords = starNameRecords(renderFixture({
  centre: dubhe,
  spanDeg: 60,
  wcs: fixtureWcs(190, 35),
}));
assert.deepEqual(new Set(umaRecords.filter((record) => dipperNames.has(record.text)).map((record) => record.text)), dipperNames);

const compactRecords = starNameRecords(renderFixture({ centre: dubhe, spanDeg: 60, mode: "compact" }));
assert.equal(compactRecords.length, 0);

const textBox = (record, kind = "star") => {
  const fontSize = Number(/([\d.]+)px/.exec(record.font)?.[1] ?? 10);
  const width = record.text.length * 6;
  const x = record.textAlign === "left"
    ? record.x - 2
    : record.textAlign === "right"
      ? record.x - width - 2
      : record.x - width / 2 - 2;
  return kind === "star"
    ? { x, y: record.y - 0.8 * fontSize - 2, width: width + 4, height: 1.05 * fontSize + 4 }
    : { x, y: record.y - fontSize, width: width + 4, height: fontSize + 4 };
};
const assertNamesAvoidPictureAndConstellations = (wcs, spanDeg) => {
  const records = renderFixture({ centre: dubhe, spanDeg, wcs });
  const projection = g.makeProjection({ centre: dubhe, spanDeg }, 1440, 796);
  const projected = g.pictureOutline(wcs).map((point) => projection(point));
  const corners = [0, 8, 16, 24].map((index) => projected[index]);
  const longer = Math.max(...corners.map((point, index) => {
    const next = corners[(index + 1) % corners.length];
    return point && next ? Math.hypot(next[0] - point[0], next[1] - point[1]) : 0;
  }));
  const pictureCentre = projection([wcs.crval1, wcs.crval2]) ?? [720, 398];
  let pictureBox;
  if (longer >= 10 && projected.every(Boolean)) {
    pictureBox = {
      x: Math.min(...projected.map((point) => point[0])) - 3,
      y: Math.min(...projected.map((point) => point[1])) - 3,
      width: Math.max(...projected.map((point) => point[0])) - Math.min(...projected.map((point) => point[0])) + 6,
      height: Math.max(...projected.map((point) => point[1])) - Math.min(...projected.map((point) => point[1])) + 6,
    };
  } else {
    const radius = 20;
    pictureBox = { x: pictureCentre[0] - radius, y: pictureCentre[1] - radius, width: 2 * radius, height: 2 * radius };
  }
  const constellationBoxes = records.filter((record) => record.kind === "fill"
    && [SKY_PALETTES.night.names, SKY_PALETTES.night.nameHighlight].includes(record.fillStyle))
    .map((record) => textBox(record, "constellation"));
  const pictureLabel = records.find((record) => record.kind === "fill"
    && record.fillStyle === SKY_PALETTES.night.target && record.text === "Test target");
  assert.ok(pictureLabel);
  const pictureLabelBox = {
    x: pictureLabel.x - 2,
    y: pictureLabel.y - 13,
    width: pictureLabel.text.length * 6 + 4,
    height: 17,
  };
  const starBoxes = starNameRecords(records).map((record) => textBox(record));
  assert.ok(starBoxes.length > 0);
  for (const box of starBoxes) {
    assert.equal(g.rectsOverlap(box, pictureBox), false);
    assert.equal(g.rectsOverlap(box, pictureLabelBox), false);
    assert.ok(constellationBoxes.every((constellationBox) => !g.rectsOverlap(box, constellationBox)));
  }
  return starBoxes.length;
};
const rotatedNameCount = assertNamesAvoidPictureAndConstellations(fixtureWcs(dubhe[0], dubhe[1], 0.01, 37), 60);
const reticleNameCount = assertNamesAvoidPictureAndConstellations(fixtureWcs(dubhe[0], dubhe[1]), 60);

const siriusIndex = sky.names.find(([_, name]) => name === "Sirius")[0];
const sirius = sky.stars[siriusIndex].slice(0, 2);
const collisionData = {
  ...sky,
  labels: {
    ...sky.labels,
    CMa: { ...sky.labels.CMa, points: [{ at: sirius }] },
  },
};
const siriusRecord = starNameRecords(renderFixture({
  centre: sirius,
  spanDeg: 20,
  targetCode: "CMa",
  wcs: fixtureWcs(110, -5),
  data: collisionData,
})).find((record) => record.text === "Sirius");
assert.ok(!siriusRecord || siriusRecord.textAlign !== "left");
{
  // Reserved areas (the dialog's buttons and scale bar) keep every name off them, including the
  // target constellation's fallback placement below or above a large picture.
  const umaLabel = sky.labels.UMa.points[0].at;
  const bigPicture = fixtureWcs(umaLabel[0], umaLabel[1], 0.01, 0);
  const projection = g.makeProjection({ centre: umaLabel, spanDeg: 60 }, 1440, 796);
  const [, pictureY] = projection(umaLabel);
  const belowPicture = { x: 0, y: pictureY, width: 1440, height: 796 - pictureY };
  const toolbar = { x: 1300, y: 0, width: 140, height: 200 };
  const reserved = [belowPicture, toolbar];
  const records = renderFixture({ centre: umaLabel, spanDeg: 60, targetCode: "UMa", wcs: bigPicture, reserved });
  const nameRecords = records.filter((record) => record.kind === "fill" && [
    SKY_PALETTES.night.names, SKY_PALETTES.night.nameHighlight, SKY_PALETTES.night.starNames,
  ].includes(record.fillStyle));
  assert.ok(nameRecords.length > 0);
  for (const record of nameRecords) {
    const kind = record.fillStyle === SKY_PALETTES.night.starNames ? "star" : "constellation";
    const box = textBox(record, kind);
    assert.ok(reserved.every((area) => !g.rectsOverlap(box, area)), `${record.text} overlaps a reserved area`);
  }
  const target = nameRecords.find((record) => record.fillStyle === SKY_PALETTES.night.nameHighlight);
  assert.ok(!target || target.y < pictureY, "the target's name went above the picture, not into the reserved area");
  console.log(`renderer reserved areas: ${nameRecords.length} names clear; target name ${target ? "above the picture" : "hidden"}`);
}
console.log(`renderer star names: whole sky ${wholeSkyNames.length}, UMa ${umaRecords.length}, rotated ${rotatedNameCount}, reticle ${reticleNameCount}, compact ${compactRecords.length}`);

{
  const view = { centre: [0, 89], spanDeg: 60 };
  const grabbed = g.makeProjection(view, 1000, 750).invert([510, 375]);
  const anchored = g.anchorView(view, 120, grabbed, [510, 375], 1000, 750);
  const zoomed = g.zoomViewAt(view, 0.5, [510, 375], 1000, 750);
  const brute = bruteForceAnchor(grabbed, [510, 375], 120);
  assert.ok(Number.isFinite(anchored.residualPx));
  assert.ok(anchored.view.centre.every(Number.isFinite) && anchored.view.centre[1] <= 90);
  assert.ok(zoomed.centre.every(Number.isFinite) && zoomed.centre[1] <= 90);
  assert.ok(anchored.residualPx <= brute + 1, `pole anchor ${anchored.residualPx} vs ${brute}`);
  console.log(`pole anchor residual: ${anchored.residualPx.toFixed(4)} px (0.5° grid ${brute.toFixed(4)} px)`);
}

assert.equal(text.formatMonthDay(4, 23), "April 23");
assert.equal(text.headerSubtitle([], "Ursa Major"), "Centred in Ursa Major");
assert.equal(text.headerSubtitle(["M 101"], "Ursa Major"), "M 101 in Ursa Major");
assert.equal(text.headerSubtitle(["M 65", "M 66"], "Leo"), "M 65 and M 66 in Leo");
assert.equal(text.headerSubtitle(["a", "b", "c"], "Leo"), "3 targets in Leo");
assert.equal(text.pictureLabel("x".repeat(40)), `${"x".repeat(31)}…`);
assert.equal(text.pictureLabel("x".repeat(32)), "x".repeat(32));
assert.equal(SKY_PALETTES.night.sky, "#0e1628");
assert.equal(SKY_PALETTES.paper.target, "#b8661a");
console.log("sky chart assertions passed");
