import assert from "node:assert/strict";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import ts from "typescript";

const root = process.cwd();
const cache = path.join(root, "node_modules/.cache/session-build-prompt-check");
await mkdir(cache, { recursive: true });
const source = await readFile(
  path.join(root, "src/components/projects/sessionBuildPrompt.ts"),
  "utf8",
);
const output = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
  fileName: "sessionBuildPrompt.ts",
}).outputText;
const file = path.join(cache, "sessionBuildPrompt.mjs");
await writeFile(file, output);
const { shouldOfferSessionBuild } = await import(pathToFileURL(file).href);
const componentSource = await readFile(
  path.join(root, "src/components/projects/ProjectSessionsTab.tsx"),
  "utf8",
);
const nightBlockSource = await readFile(
  path.join(root, "src/components/projects/SessionNightBlock.tsx"),
  "utf8",
);
const valueColumnsSource = await readFile(
  path.join(root, "src/components/projects/sessionValueColumns.ts"),
  "utf8",
);
const valueColumnsOutput = ts.transpileModule(valueColumnsSource, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
  fileName: "sessionValueColumns.ts",
}).outputText;
const valueColumnsFile = path.join(cache, "sessionValueColumns.mjs");
await writeFile(valueColumnsFile, valueColumnsOutput);
const { sessionValueColumns } = await import(pathToFileURL(valueColumnsFile).href);

assert.equal(shouldOfferSessionBuild(4, 0), true, "manual-only projects get the prompt");
assert.equal(shouldOfferSessionBuild(1, 0), true, "emptied automatic batches get the prompt");
assert.equal(shouldOfferSessionBuild(0, 0), false, "no lights means no build prompt");
assert.equal(shouldOfferSessionBuild(4, 1), false, "automatic batches suppress the prompt");
assert.match(componentSource, /"Rebuild from subs"/, "the quiet rebuild action remains available");
assert.match(
  componentSource,
  /The sessions were rebuilt\. Choose the setup again\./,
  "a stale setup edit explains the rebuild after refetching",
);
assert.deepEqual(sessionValueColumns([{ iso: 800, gain: null }]), ["iso"]);
assert.deepEqual(sessionValueColumns([{ iso: null, gain: 100 }]), ["gain"]);
assert.deepEqual(sessionValueColumns([{ iso: 800, gain: null }, { iso: null, gain: 100 }]), ["iso", "gain"]);
assert.deepEqual(sessionValueColumns([{ iso: null, gain: null }]), []);
assert.match(nightBlockSource, /session\[column\] \?\? "—"/);

console.log("session build prompt: all checks passed");
