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

// A night's darkness, 01:50–12:30 UTC, with the Moon setting at 04:50 UTC.
const astroNight = {
  date: "2026-11-14",
  verdict: "go",
  darkness: "astronomical",
  dark_hours: 10.67,
  moonless_dark_hours: 7.67,
  midnight_utc: "2026-11-15T07:00:00Z",
  runs: [
    { start: "18:50", end: "21:50", start_utc: "2026-11-15T01:50:00Z", end_utc: "2026-11-15T04:50:00Z", moon_up: true },
    { start: "21:50", end: "05:30", start_utc: "2026-11-15T04:50:00Z", end_utc: "2026-11-15T12:30:00Z", moon_up: false },
  ],
};
assert.deepEqual(home.darknessLine(astroNight), {
  segments: [
    { left: 0, width: 28.125, moonUp: true },
    { left: 28.125, width: 71.875, moonUp: false },
  ],
  midnight: 48.4375,
});
assert.equal(
  home.forecastCellLabel("Backyard", astroNight),
  "Backyard, Saturday 14 November: Go; 10.7 h of astronomical darkness, 18:50–05:30; Moon up 18:50–21:50; 7.7 h with the Moon down",
);
assert.equal(home.darknessFigure(astroNight), "of 10.7");

const nauticalNight = {
  ...astroNight,
  verdict: "uncertain",
  darkness: "nautical",
  dark_hours: 4.18,
  moonless_dark_hours: 4.18,
  midnight_utc: "2026-11-15T20:00:00Z",
  runs: [{ ...astroNight.runs[1], moon_up: false }],
};
assert.deepEqual(home.darknessLine(nauticalNight), {
  segments: [{ left: 0, width: 100, moonUp: false }],
  midnight: null,
});
assert.equal(
  home.forecastCellLabel("Ushuaia", nauticalNight),
  "Ushuaia, Saturday 14 November: Uncertain; 4.2 h of nautical darkness, 21:50–05:30 (the Sun never gets 18° below the horizon); Moon down throughout; 4.2 h with the Moon down",
);
assert.equal(home.darknessFigure(nauticalNight), "of 4.2 naut.");
assert.equal(home.darknessFigure({ darkness: "civil", dark_hours: 3.14 }), "of 3.1 civil");

// Two stretches of darkness with daylight between them (high latitude).
const splitNight = {
  ...astroNight,
  dark_hours: 10.2,
  moonless_dark_hours: 10.2,
  runs: [
    { start: "12:00", end: "12:23", start_utc: "2026-12-21T12:00:00Z", end_utc: "2026-12-21T12:23:00Z", moon_up: false },
    { start: "13:32", end: "18:00", start_utc: "2026-12-21T13:32:00Z", end_utc: "2026-12-21T18:00:00Z", moon_up: false },
    { start: "18:00", end: "12:00", start_utc: "2026-12-21T18:00:00Z", end_utc: "2026-12-22T12:00:00Z", moon_up: false },
  ],
};
assert.equal(
  home.forecastCellLabel("Far north", splitNight),
  "Far north, Saturday 14 November: Go; 10.2 h of astronomical darkness, 12:00–12:23 and 13:32–12:00; Moon down throughout; 10.2 h with the Moon down",
);

const darklessNight = { ...astroNight, verdict: "no", darkness: "none", dark_hours: 0, moonless_dark_hours: 0, runs: [] };
assert.equal(home.darknessLine(darklessNight), null);
assert.equal(
  home.forecastCellLabel("McMurdo", darklessNight),
  "McMurdo, Saturday 14 November: No; no darkness: the Sun stays within 6° of the horizon",
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
