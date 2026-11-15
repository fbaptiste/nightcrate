// Assertions for src/lib/paths.ts: POSIX, Windows drive and network paths.
import assert from "node:assert/strict";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import ts from "typescript";

const root = process.cwd();
const cache = path.join(root, "node_modules/.cache/paths-check");
await mkdir(cache, { recursive: true });
const source = await readFile(path.join(root, "src/lib/paths.ts"), "utf8");
const output = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
  fileName: "paths.ts",
}).outputText;
const file = path.join(cache, "paths.mjs");
await writeFile(file, output);
const { baseName, joinPath, parentPath, pathCrumbs } = await import(pathToFileURL(file).href);

const crumbs = (p) => pathCrumbs(p).map((c) => `${c.name}=${c.path}`).join(" | ");
assert.equal(crumbs("/Users/me/Astro"), "/=/ | Users=/Users | me=/Users/me | Astro=/Users/me/Astro");
assert.equal(crumbs("/"), "/=/");
assert.equal(crumbs("/Volumes/Data/"), "/=/ | Volumes=/Volumes | Data=/Volumes/Data");
assert.equal(crumbs("C:\\Users\\me"), "C:=C:\\ | Users=C:\\Users | me=C:\\Users\\me");
assert.equal(crumbs("C:\\"), "C:=C:\\");
assert.equal(crumbs("D:"), "D:=D:\\");
assert.equal(
  crumbs("\\\\nas\\images\\2026"),
  "\\\\nas\\images=\\\\nas\\images\\ | 2026=\\\\nas\\images\\2026",
);
assert.equal(crumbs("\\\\nas\\images"), "\\\\nas\\images=\\\\nas\\images\\");

assert.equal(parentPath("/Users/me/a.fits"), "/Users/me");
assert.equal(parentPath("/a.fits"), "/");
assert.equal(parentPath("/"), "/");
assert.equal(parentPath("C:\\Data\\m31.xisf"), "C:\\Data");
assert.equal(parentPath("C:\\m31.xisf"), "C:\\");
assert.equal(parentPath("C:\\"), "C:\\");

assert.equal(baseName("/Users/me/x.zip"), "x.zip");
assert.equal(baseName("C:\\Data\\x.zip"), "x.zip");
assert.equal(baseName("/"), "/");

assert.equal(joinPath("/Users/me", "New"), "/Users/me/New");
assert.equal(joinPath("/", "New"), "/New");
assert.equal(joinPath("C:\\Users\\me", "New"), "C:\\Users\\me\\New");
assert.equal(joinPath("C:\\", "New"), "C:\\New");
assert.equal(joinPath("\\\\nas\\images", "New"), "\\\\nas\\images\\New");

console.log("paths: all checks passed");
