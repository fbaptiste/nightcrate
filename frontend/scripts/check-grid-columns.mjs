import assert from "node:assert/strict";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import ts from "typescript";

const root = process.cwd();
const cache = path.join(root, "node_modules/.cache/grid-columns-check");
await mkdir(cache, { recursive: true });
const source = await readFile(path.join(root, "src/lib/gridDropdownColumns.ts"), "utf8");
const output = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
  fileName: "gridDropdownColumns.ts",
}).outputText;
const file = path.join(cache, "gridDropdownColumns.mjs");
await writeFile(file, output);
const { dropdownOptions, withDropdownFilters } = await import(pathToFileURL(file).href);

const manufacturer = { field: "m" };
const rows = [{ m: "ZWO" }, { m: "Celestron" }, { m: "ZWO" }, { m: null }, { m: "—" }];
const [manufacturerDropdown] = withDropdownFilters([manufacturer], rows, ["m"]);
assert.equal(manufacturerDropdown.type, "singleSelect");
assert.deepEqual(manufacturerDropdown.valueOptions, ["Celestron", "ZWO"]);

const [emptyDropdown] = withDropdownFilters([manufacturer], [], ["m"]);
assert.equal(emptyDropdown.type, "singleSelect");
assert.deepEqual(emptyDropdown.valueOptions, []);

const numbers = dropdownOptions([{ n: 7 }, { n: 5 }, { n: 7 }], "n", (row) => row.n);
assert.deepEqual(numbers, [5, 7]);
assert.equal(typeof numbers[0], "number");

const getterColumn = {
  field: "name",
  valueGetter: (_value, row) => row.x?.name ?? "—",
};
const [getterDropdown] = withDropdownFilters(
  [getterColumn],
  [{ x: { name: "ZWO" } }, { x: null }, { x: { name: "Askar" } }],
  ["name"],
);
assert.deepEqual(getterDropdown.valueOptions, ["Askar", "ZWO"]);

const untouched = { field: "other" };
assert.equal(withDropdownFilters([untouched], rows, ["m"])[0], untouched);

assert.deepEqual(
  dropdownOptions([{ f: "Filter 10" }, { f: "Filter 2" }], "f", (row) => row.f),
  ["Filter 2", "Filter 10"],
);

console.log("grid columns: all checks passed");
