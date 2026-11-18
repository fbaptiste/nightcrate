import assert from "node:assert/strict";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import ts from "typescript";

const root = process.cwd();
const cache = path.join(root, "node_modules/.cache/catalog-markers-check");
await mkdir(cache, { recursive: true });
const source = await readFile(
  path.join(root, "src/components/projects/catalogMarkers.ts"),
  "utf8",
);
const output = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
  fileName: "catalogMarkers.ts",
}).outputText;
const file = path.join(cache, "catalogMarkers.mjs");
await writeFile(file, output);
const {
  filterSuggestions,
  frameTypeNote,
  qualityLevelText,
  timeSourceNote,
} = await import(pathToFileURL(file).href);
const cardsSource = await readFile(
  path.join(root, "src/components/projects/CatalogCards.tsx"),
  "utf8",
);
const cardsOutput = ts.transpileModule(cardsSource, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
  fileName: "CatalogCards.tsx",
}).outputText;
const cardsFile = path.join(cache, "CatalogCards.mjs");
await writeFile(cardsFile, cardsOutput);
const { formatSubExposure } = await import(pathToFileURL(cardsFile).href);
const tableSource = await readFile(
  path.join(root, "src/components/projects/CatalogFrameTable.tsx"),
  "utf8",
);

assert.deepEqual(frameTypeNote("auto", "file_name"), {
  label: "guessed",
  title: "Guessed from the file and folder names",
});
assert.deepEqual(frameTypeNote("auto", "folder_name"), frameTypeNote("auto", "file_name"));
assert.equal(frameTypeNote("auto", "header"), null);
assert.equal(frameTypeNote("user", "file_name"), null);
assert.deepEqual(timeSourceNote("estimated_project_zone"), {
  label: "estimated",
  title: "Estimated: the file records no time zone, so the project location's zone was used",
});
assert.deepEqual(timeSourceNote("estimated_computer_zone"), {
  label: "estimated",
  title: "Estimated: the file records no time zone, so this computer's zone was used",
});
assert.deepEqual(timeSourceNote("file_time"), {
  label: "file time",
  title: "From the file's modification time",
});
assert.equal(timeSourceNote("maker_note"), null);

assert.deepEqual(filterSuggestions(["L-Pro", "Ha"], ["Ha", "Oiii"]), [
  { value: "L-Pro", group: "This rig's filters" },
  { value: "Ha", group: "This rig's filters" },
  { value: "Oiii", group: "Bandpasses" },
]);
assert.equal(qualityLevelText(1234.4, "adu"), "1,234 ADU");
assert.equal(qualityLevelText(0.123456, "float"), "0.123456");
assert.equal(qualityLevelText(null, "adu"), "");
assert.equal(formatSubExposure(1 / 125), "0.008s");
assert.equal(formatSubExposure(0.25), "0.25s");
assert.equal(formatSubExposure(1), "1.0s");
assert.match(
  tableSource,
  /function HfrCell[\s\S]*whiteSpace: "nowrap"/,
  "HFR and the other numeric table cells do not wrap",
);

console.log("catalog markers: all checks passed");
