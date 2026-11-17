import assert from "node:assert/strict";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import ts from "typescript";

const root = process.cwd();
const cache = path.join(root, "node_modules/.cache/home-framing-check");
await mkdir(cache, { recursive: true });
const source = await readFile(path.join(root, "src/lib/galleryRendition.ts"), "utf8");
const output = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
  fileName: "galleryRendition.ts",
}).outputText.replace(
  /import\s*\{[^}]+\}\s*from\s*"@\/api\/projects";/,
  "const projectThumbnailUrl = () => ''; const renderedImageUrl = () => '';",
);
const file = path.join(cache, "galleryRendition.mjs");
await writeFile(file, output);
const { homeFramingSize } = await import(pathToFileURL(file).href);

const large = { id: 1, image_id: 9 };
const medium = { id: 2, image_id: 9 };
const small = { id: 3, image_id: 5 };

assert.equal(homeFramingSize({ large, medium }), "large");
assert.equal(homeFramingSize({ medium }), "medium");
assert.equal(homeFramingSize({}), null);
assert.equal(homeFramingSize({ large, small }, 5), "small");
assert.equal(homeFramingSize({ large, medium }, 5), null);

console.log("home framing: all checks passed");
