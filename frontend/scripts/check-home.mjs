import assert from "node:assert/strict";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import ts from "typescript";

process.env.TZ = "America/New_York";

const root = process.cwd();
const cache = path.join(root, "node_modules/.cache/home-check");
await mkdir(cache, { recursive: true });
for (const name of ["projectStatus", "home"]) {
  const source = await readFile(path.join(root, `src/lib/${name}.ts`), "utf8");
  const output = ts
    .transpileModule(source, {
      compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
      fileName: `${name}.ts`,
    })
    .outputText.replace(
      'from "@/lib/projectStatus"',
      'from "./projectStatus.mjs"',
    );
  await writeFile(path.join(cache, `${name}.mjs`), output);
}

const home = await import(pathToFileURL(path.join(cache, "home.mjs")));
const projectStatus = await import(
  pathToFileURL(path.join(cache, "projectStatus.mjs"))
);

assert.deepEqual(
  Object.fromEntries(
    projectStatus.PROJECT_STATUS_ORDER.map((status) => [
      status,
      projectStatus.projectStatusLabel(status),
    ]),
  ),
  {
    active: "Active",
    ready_to_process: "Ready to process",
    paused: "Paused",
    complete: "Complete",
    abandoned: "Abandoned",
  },
);

const stages = {
  not_started: 0,
  capturing: 4,
  ready_to_process: 1,
  complete: 0,
  paused: 2,
  abandoned: 0,
};
assert.deepEqual(
  home.stageSegments(stages).map(({ key, count }) => [key, count]),
  [["capturing", 4], ["ready_to_process", 1], ["paused", 2]],
);

const bars = home.monthBars([
  { month: "2026-09", minutes: 0 },
  { month: "2026-10", minutes: 30 },
  { month: "2026-11", minutes: 60 },
]);
assert.equal(bars[0].empty, true);
assert.equal(bars[0].heightPx, 2);
assert.equal(bars[1].heightPx, 26);
assert.equal(bars[2].heightPx, 52);

assert.equal(
  home.forecastCellLabel("Backyard", "2026-11-16", "go", 6.8),
  "Backyard, Monday 16 November: Go; 6.8 h of dark sky with the Moon down",
);

assert.equal(home.fortnightDates(new Date(2026, 10, 14, 11, 59))[0], "2026-11-13");
assert.equal(home.fortnightDates(new Date(2026, 10, 14, 12, 0))[0], "2026-11-14");
const acrossDst = home.fortnightDates(new Date(2026, 9, 28, 12, 0));
assert.equal(acrossDst.length, 14);
assert.deepEqual(acrossDst.slice(3, 7), [
  "2026-10-31",
  "2026-11-01",
  "2026-11-02",
  "2026-11-03",
]);

assert.deepEqual(
  [0, 59, 60, 2760, 2761].map(home.formatHours),
  ["0 hours", "1 hour", "1 hour", "46 hours", "46 hours"],
);

assert.equal(home.rowEnabled(0, ["pending", "pending"]), true);
assert.equal(home.rowEnabled(1, ["pending", "pending"]), false);
assert.equal(home.rowEnabled(1, ["success", "pending"]), true);
assert.equal(home.rowEnabled(1, ["error", "pending"]), true);
assert.equal(home.rowEnabled(2, ["success", "pending", "pending"]), false);
assert.equal(home.rowEnabled(2, ["success", "error", "pending"]), true);

console.log("Home helper checks passed.");
