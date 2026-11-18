import assert from "node:assert/strict";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import ts from "typescript";

const root = process.cwd();
const cache = path.join(root, "node_modules/.cache/plate-solve-check");
await mkdir(cache, { recursive: true });
const source = await readFile(path.join(root, "src/lib/plateSolveObjects.ts"), "utf8");
const output = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
  fileName: "plateSolveObjects.ts",
}).outputText;
const file = path.join(cache, "plateSolveObjects.mjs");
await writeFile(file, output);
const {
  clampView,
  facetCounts,
  filterObjects,
  fitScale,
  keepCentre,
  sizeToSlider,
  sliderToSize,
  sortObjects,
  zoomAt,
} = await import(pathToFileURL(file).href);
const sidePanelSource = await readFile(
  path.join(root, "src/components/projects/plate-solve/PlateSolveSidePanel.tsx"),
  "utf8",
);
const tablesSource = await readFile(
  path.join(root, "src/components/projects/plate-solve/PlateSolveObjectTables.tsx"),
  "utf8",
);
const workspaceSource = await readFile(
  path.join(root, "src/components/projects/plate-solve/SolvedPlateSolveWorkspace.tsx"),
  "utf8",
);
const viewerSource = await readFile(
  path.join(root, "src/components/projects/plate-solve/PlateSolveViewer.tsx"),
  "utf8",
);

const objects = [
  { dso_id: 1, primary_designation: "NGC 10", common_name: null, obj_type: "G", catalogs: ["ngc"], maj_axis_arcmin: 5, min_axis_arcmin: 3 },
  { dso_id: 2, primary_designation: "NGC 9", common_name: null, obj_type: "G", catalogs: ["ngc", "messier"], maj_axis_arcmin: 10, min_axis_arcmin: 8 },
  { dso_id: 3, primary_designation: "LBN 1", common_name: "Cloud", obj_type: "DN", catalogs: ["lbn"], maj_axis_arcmin: null, min_axis_arcmin: null },
  { dso_id: 4, primary_designation: "Sh2-1", common_name: "Cloud", obj_type: "EN", catalogs: ["sharpless2"], maj_axis_arcmin: 5, min_axis_arcmin: 2 },
  { dso_id: 5, primary_designation: "Main 1", common_name: null, obj_type: "OC", catalogs: [], maj_axis_arcmin: 0.05, min_axis_arcmin: 0.04 },
];
const mainIds = new Set([5]);
const empty = { catalogs: new Set(), types: new Set(), minSizeArcmin: 0 };

assert.deepEqual(filterObjects(objects, empty, mainIds).map((item) => item.dso_id), [1, 2, 3, 4, 5]);
assert.deepEqual(
  filterObjects(objects, { ...empty, catalogs: new Set(["lbn", "messier"]) }, mainIds).map((item) => item.dso_id),
  [2, 3, 5],
  "catalog selections form a union",
);
assert.deepEqual(
  filterObjects(objects, { catalogs: new Set(["ngc"]), types: new Set(["G"]), minSizeArcmin: 6 }, mainIds).map((item) => item.dso_id),
  [2, 5],
  "different filter dimensions intersect and main targets always remain",
);
assert.deepEqual(
  filterObjects(objects, { ...empty, minSizeArcmin: 5 }, mainIds).map((item) => item.dso_id),
  [1, 2, 4, 5],
  "the minimum is inclusive and hides unsized objects",
);

const counts = facetCounts(objects, { catalogs: new Set(["ngc"]), types: new Set(["G"]), minSizeArcmin: 6 }, mainIds);
assert.deepEqual(Object.fromEntries(counts.catalogs), { messier: 1, ngc: 1 });
assert.deepEqual(Object.fromEntries(counts.types), { G: 1 });

assert.deepEqual(sortObjects(objects, "name", "asc").map((item) => item.dso_id), [3, 5, 2, 1, 4]);
assert.deepEqual(sortObjects(objects, "name", "desc").map((item) => item.dso_id), [4, 1, 2, 5, 3]);
assert.deepEqual(sortObjects(objects, "size", "asc").map((item) => item.dso_id), [5, 1, 4, 2, 3]);
assert.deepEqual(sortObjects(objects, "size", "desc").map((item) => item.dso_id), [2, 1, 4, 5, 3]);
assert.deepEqual(
  sortObjects(objects, "type", "asc").map((item) => item.dso_id),
  [3, 4, 2, 1, 5],
  "ties use natural primary-designation order, then id",
);
const sameName = [
  { ...objects[0], dso_id: 7 },
  { ...objects[0], dso_id: 6 },
];
assert.deepEqual(sortObjects(sameName, "name", "asc").map((item) => item.dso_id), [6, 7]);
assert.deepEqual(sortObjects(sameName, "name", "desc").map((item) => item.dso_id), [6, 7]);

for (const maximum of [0.05, 0.1, 140]) {
  assert.equal(sliderToSize(0, maximum), 0);
  assert.equal(sliderToSize(100, maximum), maximum);
  for (const position of [1, 25, 50, 75, 100]) {
    const size = sliderToSize(position, maximum);
    assert.ok(size > 0 && size <= maximum);
    assert.ok(Math.abs(sizeToSlider(size, maximum) - position) < 1e-8);
  }
}
assert.equal(sizeToSlider(0, 0), 0, "no positive sizes leaves the slider disabled");
assert.match(sidePanelSource, /disabled=\{maxSizeArcmin <= 0\}/);
assert.match(tablesSource, /aria-selected=\{selected\}/);
assert.match(tablesSource, /role="columnheader"\s+aria-sort=\{ariaSort\}/);
assert.match(tablesSource, /component="h2" tabIndex=\{-1\}/);
assert.match(
  workspaceSource,
  /focusCheckbox\(object\.dso_id, changed \? isMain : !isMain\)/,
);
assert.match(
  viewerSource,
  /useEffect\(\(\) => \{\s+dsosRef\.current = dsos;\s+cullNow\(\);/,
);

const bounds = { imageWidth: 1000, imageHeight: 500, viewportWidth: 500, viewportHeight: 300, minScale: 0.5, maxScale: 4 };
assert.equal(fitScale(1000, 500, 500, 300), 0.5);
const start = { scale: 0.5, x: 0, y: 25 };
const anchored = zoomAt(start, { x: 125, y: 100 }, 2, bounds);
assert.deepEqual(anchored, { scale: 1, x: -125, y: -50 });
assert.deepEqual(clampView({ scale: 1, x: 500, y: -999 }, bounds), { scale: 1, x: 0, y: -200 });
assert.deepEqual(
  keepCentre(start, { width: 500, height: 300 }, { width: 700, height: 400 }, { ...bounds, viewportWidth: 700, viewportHeight: 400 }),
  { scale: 0.5, x: 100, y: 75 },
);
const smallBounds = { imageWidth: 200, imageHeight: 100, viewportWidth: 500, viewportHeight: 300, minScale: 1, maxScale: 4 };
assert.deepEqual(clampView({ scale: 1, x: 0, y: 0 }, smallBounds), { scale: 1, x: 150, y: 100 }, "1:1 remains available for a smaller image");

console.log("plate solve: all checks passed");
