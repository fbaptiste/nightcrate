import assert from "node:assert/strict";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import ts from "typescript";

const root = process.cwd();
const cache = path.join(root, "node_modules/.cache/ingest-completion-check");
await mkdir(cache, { recursive: true });
const source = await readFile(path.join(root, "src/lib/ingestCompletion.ts"), "utf8");
const output = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
  fileName: "ingestCompletion.ts",
}).outputText;
const file = path.join(cache, "ingestCompletion.mjs");
await writeFile(file, output);
const { ingestCompletionAction } = await import(pathToFileURL(file).href);

const decide = (overrides) => ingestCompletionAction({
  running: false,
  handled: false,
  observed: false,
  startPending: false,
  startedHere: false,
  ...overrides,
});

assert.equal(decide({ running: true }), "observe");
assert.equal(decide({ observed: true }), "show");
assert.equal(decide({ startedHere: true }), "show");
assert.equal(decide({ startPending: true }), "none");
assert.equal(decide({}), "dismiss");
assert.equal(decide({ handled: true, observed: true }), "none");

console.log("ingest completion: all checks passed");
