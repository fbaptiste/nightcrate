import assert from "node:assert/strict";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import ts from "typescript";

const root = process.cwd();
const cache = path.join(root, "node_modules/.cache/mine-group-check");
await mkdir(cache, { recursive: true });
const source = await readFile(path.join(root, "src/components/rigs/mineGroup.ts"), "utf8");
const output = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
  fileName: "mineGroup.ts",
}).outputText;
const file = path.join(cache, "mineGroup.mjs");
await writeFile(file, output);
const { mineOptionKey, withMineGroup } = await import(pathToFileURL(file).href);

const options = [
  { id: 1, is_mine: true, manufacturer_name: "ZWO" },
  { id: 2, is_mine: false, manufacturer_name: "Askar" },
];
const grouped = withMineGroup(options);
assert.deepEqual(grouped.map((option) => option.id), [1, 2, 1]);
assert.equal(grouped[0].__mine_group, "My Equipment");
assert.equal(grouped[1].__mine_group, undefined);
assert.equal(grouped[2].__mine_group, undefined);

const unowned = [
  { id: 1, is_mine: false, manufacturer_name: "ZWO" },
  { id: 2, is_mine: false, manufacturer_name: "Askar" },
];
assert.deepEqual(withMineGroup(unowned), [unowned[1], unowned[0]]);

const software = [
  { id: 1, name: "Siril", is_mine: true },
  { id: 2, name: "ASTAP", is_mine: true },
  { id: 3, name: "N.I.N.A.", is_mine: false },
];
const softwareGrouped = withMineGroup(
  software,
  "My Software",
  (a, b) => a.name.localeCompare(b.name),
);
assert.deepEqual(softwareGrouped.map((option) => option.id), [2, 1, 2, 3, 1]);
assert.equal(softwareGrouped[0].__mine_group, "My Software");

assert.notEqual(
  mineOptionKey({ id: 1, __mine_group: "My Equipment" }),
  mineOptionKey({ id: 1 }),
);
assert.equal(mineOptionKey({ id: 1, __mine_group: "My Equipment" }), "mine-1");
assert.equal(mineOptionKey({ id: 1, retired: true }), "retired-1");

console.log("mine group: all checks passed");
