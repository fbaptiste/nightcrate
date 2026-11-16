import assert from "node:assert/strict";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import ts from "typescript";

const root = process.cwd();
const cache = path.join(root, "node_modules/.cache/notice-text-check");
await mkdir(cache, { recursive: true });
const source = await readFile(path.join(root, "src/components/notices/noticeText.ts"), "utf8");
const output = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
  fileName: "noticeText.ts",
}).outputText;
await writeFile(path.join(cache, "noticeText.mjs"), output);
const text = await import(pathToFileURL(path.join(cache, "noticeText.mjs")));

const now = new Date("2026-11-20T21:00:00Z");
assert.equal(text.monthsSince("2026-04-20T21:00:00Z", now), 7);
assert.equal(text.releaseDate("2026-11-20T12:00:00Z"), "20 November 2026");
assert.equal(text.noticeTitle({ id: "wikidata_query" }, now), "NightCrate now downloads more from Wikidata");
assert.equal(text.noticeDescription({ id: "openngc", latest_tag: "2026-11-02", installed_tag: "2023-12-03" }), "Version 2026-11-02 is available. You have 2023-12-03.");
assert.match(text.formatCheckTime("2026-11-20T20:04:00Z", now), /^today at /);
console.log("notice text checks passed");
