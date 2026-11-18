import assert from "node:assert/strict";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import ts from "typescript";

const root = process.cwd();
const cache = path.join(root, "node_modules/.cache/rig-provenance-check");
await mkdir(cache, { recursive: true });
const source = await readFile(
  path.join(root, "src/components/projects/rigProvenance.ts"),
  "utf8",
);
const output = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
  fileName: "rigProvenance.ts",
}).outputText;
const file = path.join(cache, "rigProvenance.mjs");
await writeFile(file, output);
const { rigProvenanceBadge } = await import(pathToFileURL(file).href);

assert.deepEqual(rigProvenanceBadge("files"), {
  label: "from files",
  title: "Your files in this project were taken with this rig, set on their folder in the Files tab. You didn't add it to the project yourself.",
});
assert.deepEqual(rigProvenanceBadge("manual_sessions"), {
  label: "from sessions",
  title: "Sessions you entered by hand in this project use this rig. You didn't add it to the project yourself.",
});
assert.deepEqual(rigProvenanceBadge("auto_sessions"), {
  label: "from sessions",
  title: "Sessions built from this project's files use this rig, but none of its files do any more. Rebuild the sessions to update them.",
});
assert.deepEqual(rigProvenanceBadge(null), {
  label: "source unknown",
  title: "This project uses this rig, but its source couldn't be determined.",
});
assert.deepEqual(rigProvenanceBadge(undefined), {
  label: "source unknown",
  title: "This project uses this rig, but its source couldn't be determined.",
});

console.log("rig provenance: all checks passed");
