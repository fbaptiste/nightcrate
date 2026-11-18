import assert from "node:assert/strict";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import ts from "typescript";

const root = process.cwd();
const cache = path.join(root, "node_modules/.cache/analyzer-colour-check");
await mkdir(cache, { recursive: true });
const source = await readFile(
  path.join(root, "src/components/analyzer/analyzerColour.ts"),
  "utf8",
);
const output = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
  fileName: "analyzerColour.ts",
}).outputText;
const file = path.join(cache, "analyzerColour.mjs");
await writeFile(file, output);
const {
  analyzerImageKey,
  imageInfoFields,
  inspectorLabel,
  metadataGroups,
  patternOptions,
  pixelPlaceholderData,
  shouldResetPatternChoice,
  showPatternChoicePill,
} =
  await import(pathToFileURL(file).href);
const analyzerSource = await readFile(
  path.join(root, "src/components/analyzer/ImageAnalyzerView.tsx"),
  "utf8",
);
const pillSource = await readFile(
  path.join(root, "src/components/common/InferredPill.tsx"),
  "utf8",
);

assert.equal(inspectorLabel({ K: 1234.4, units: "adu", site_colour: "R" }), "1,234 ADU, under a red filter");
assert.equal(inspectorLabel({ K: 0.1234, units: "float", site_colour: "G" }), "0.123, under a green filter");
assert.equal(inspectorLabel({ K: 1234.4, units: "adu", site_colour: null }), "1,234 ADU");

const previousPixel = { K: 1234.4, units: "adu" };
const previousPixelKey = ["image-pixel", "/one.fits", 2, 10, 20, "RGGB"];
assert.equal(
  pixelPlaceholderData(previousPixel, previousPixelKey, "/one.fits", 2, "RGGB"),
  previousPixel,
  "coordinate changes keep the previous value on the same image",
);
assert.equal(pixelPlaceholderData(previousPixel, previousPixelKey, "/two.fits", 2, "RGGB"), undefined);
assert.equal(pixelPlaceholderData(previousPixel, previousPixelKey, "/one.fits", 3, "RGGB"), undefined);
assert.equal(pixelPlaceholderData(previousPixel, previousPixelKey, "/one.fits", 2, "BGGR"), undefined);
assert.equal(pixelPlaceholderData(previousPixel, undefined, "/one.fits", 2, "RGGB"), undefined);

assert.deepEqual(patternOptions("RGGB"), [
  { value: "RGGB", label: "RGGB (this rig's camera)" },
  { value: "", label: "None (mono)" },
  { value: "GRBG", label: "GRBG" },
  { value: "GBRG", label: "GBRG" },
  { value: "BGGR", label: "BGGR" },
]);

const groups = metadataGroups([
  { group: "EXIF", key: "Exif.Image.Make", value: "Canon", comment: "Camera make" },
  { group: "Capture", key: "ISO", value: "800", comment: "" },
  { group: "Colour data", key: "Pattern", value: "RG/GB", comment: "" },
  { group: "Colour data", key: "Pattern source", value: "the raw file", comment: "" },
  { group: "Maker notes", key: "Exif.Canon.Serial", value: "123", comment: "" },
]);
assert.deepEqual(groups.map((group) => group.name), ["Capture", "Colour data", "EXIF", "Maker notes"]);
assert.equal(groups[1].rows[0].name, "Colour pattern");
assert.equal(groups[1].rows[0].value, "RGGB, from the raw file");
assert.equal(groups[1].rows.length, 1, "raw metadata does not invent a row-order assumption");

const xTrans = metadataGroups([
  { group: "Colour data", key: "Pattern", value: "RGBGRG/GBGGRG/GRGGBG/BGRGRG/GRGGRG/GBGBRG" },
  { group: "Colour data", key: "Pattern source", value: "the raw file" },
]);
assert.equal(xTrans[0].rows[0].value, "X-Trans (6×6), from the raw file");

assert.equal(showPatternChoicePill(null), false);
assert.equal(showPatternChoicePill(""), false, "None returns to the default view");
assert.equal(showPatternChoicePill("GRBG"), true);
assert.equal(analyzerImageKey("/one.fits", 2), "/one.fits::2");
assert.equal(shouldResetPatternChoice("/one.fits::2", "/one.fits", 2), false);
assert.equal(shouldResetPatternChoice("/one.fits::2", "/one.fits", 3), true);
assert.equal(shouldResetPatternChoice("/one.fits::2", "/two.fits", 2), true);

assert.deepEqual(imageInfoFields({ exposure_time: 0.008, iso: 800, model: "X-T5", focal_length_mm: 200, lens: "XF 200" }, true), [
  ["exposure_time", "Exposure"],
  ["iso", "ISO"],
  ["model", "Camera"],
  ["focal_length_mm", "Focal length"],
  ["lens", "Lens"],
]);
assert.deepEqual(imageInfoFields({ object_name: "M31", camera_name: "ASI2600" }, false), [
  ["object_name", "Object"],
  ["camera_name", "Camera"],
]);
assert.match(analyzerSource, /isRaw \? formatSubExposure\(Number\(meta\[key\]\)\)/);
assert.match(analyzerSource, />\s*On screen\s*</);
assert.match(analyzerSource, /pixelData\.R\.toFixed\(5\)/);
assert.match(analyzerSource, /rgbToHex\(pixelData\.R, pixelData\.G, pixelData\.B\)/);
assert.match(analyzerSource, /findColorName\(pixelData\.R, pixelData\.G, pixelData\.B\)/);
assert.match(analyzerSource, /pixelData === null\s*\? inspectorLabel\(null\)/);
assert.match(analyzerSource, /placeholderData: \(previousData, previousQuery\) => pixelPlaceholderData\(/);
assert.match(analyzerSource, /if \(lastImageKey !== imageKey\) \{[\s\S]*?setPixelData\(null\);[\s\S]*?\}/);
assert.match(pillSource, /fontFamily: theme\.typography\.body1\.fontFamily/);
assert.match(pillSource, /letterSpacing: "normal"/);

console.log("analyzer colour: all checks passed");
