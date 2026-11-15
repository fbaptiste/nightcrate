import type { FortnightNight, MonthSummary, StageCounts, YearSummary } from "@/api/home";
import type { Stage } from "@/api/projects";
import type { Verdict } from "@/api/weather";
import { PROJECT_STATUS_DISPLAY } from "@/lib/projectStatus";

export const STAGE_ORDER: Stage[] = [
  "not_started",
  "capturing",
  "ready_to_process",
  "complete",
  "paused",
  "abandoned",
];

export const STAGE_LABELS: Record<Stage, string> = {
  not_started: "Not started",
  capturing: "Capturing",
  ready_to_process: PROJECT_STATUS_DISPLAY.ready_to_process.label,
  complete: PROJECT_STATUS_DISPLAY.complete.label,
  paused: PROJECT_STATUS_DISPLAY.paused.label,
  abandoned: PROJECT_STATUS_DISPLAY.abandoned.label,
};

export const STAGE_DESCRIPTIONS: Record<Stage, string> = {
  not_started: "Active, with no data captured",
  capturing: "Active, with data captured",
  ready_to_process: PROJECT_STATUS_DISPLAY.ready_to_process.description,
  complete: PROJECT_STATUS_DISPLAY.complete.description,
  paused: PROJECT_STATUS_DISPLAY.paused.description,
  abandoned: PROJECT_STATUS_DISPLAY.abandoned.description,
};

export interface StageSegment {
  key: Stage;
  label: string;
  count: number;
  description: string;
}

export function stageSegments(stages: StageCounts): StageSegment[] {
  return STAGE_ORDER.filter((key) => stages[key] > 0).map((key) => ({
    key,
    label: STAGE_LABELS[key],
    count: stages[key],
    description: STAGE_DESCRIPTIONS[key],
  }));
}

export interface MonthBar {
  label: string;
  initial: string;
  minutes: number;
  heightPx: number;
  empty: boolean;
}

function localDate(value: string): Date {
  const [year, month, day = 1] = value.split("-").map(Number);
  return new Date(year, month - 1, day, 12);
}

export function monthBars(months: MonthSummary[], maxPx = 52): MonthBar[] {
  const maximum = Math.max(0, ...months.map((month) => month.minutes));
  return months.map((month) => {
    const label = new Intl.DateTimeFormat("en-US", {
      month: "long",
      year: "numeric",
    }).format(localDate(month.month));
    const empty = month.minutes <= 0;
    return {
      label,
      initial: label.slice(0, 1),
      minutes: month.minutes,
      heightPx: empty || maximum === 0 ? 2 : (month.minutes / maximum) * maxPx,
      empty,
    };
  });
}

export function formatHours(minutes: number): string {
  const hours = Math.max(0, Math.round(minutes / 60));
  return `${hours} ${hours === 1 ? "hour" : "hours"}`;
}

export function formatPanelHours(minutes: number): string {
  return `${Math.round(minutes / 60)} h`;
}

export function formatHoursMinutes(minutes: number): string {
  const rounded = Math.max(0, Math.round(minutes));
  const hours = Math.floor(rounded / 60);
  const remainder = rounded % 60;
  if (hours === 0) return `${remainder} m`;
  return `${hours} h${remainder ? ` ${remainder} m` : ""}`;
}

export const VERDICT_LABELS: Record<Verdict, string> = {
  go: "Go",
  uncertain: "Uncertain",
  no: "No",
  not_enough_data: "Not enough data",
  night_over: "Night over",
};

export function formatDate(value: string, options?: Intl.DateTimeFormatOptions): string {
  return new Intl.DateTimeFormat("en-GB", options ?? {
    day: "numeric",
    month: "long",
  }).format(localDate(value));
}

const SHALLOW_NOTE = {
  nautical: "the Sun never gets 18° below the horizon",
  civil: "the Sun never gets 12° below the horizon",
} as const;

/** The figure under a night's line: "of 10.7", or "of 4.2 naut." for shallower darkness. */
export function darknessFigure(night: Pick<FortnightNight, "darkness" | "dark_hours">): string {
  const hours = night.dark_hours.toFixed(1);
  if (night.darkness === "nautical") return `of ${hours} naut.`;
  if (night.darkness === "civil") return `of ${hours} civil`;
  return `of ${hours}`;
}

export function forecastCellLabel(name: string, night: FortnightNight): string {
  const day = formatDate(night.date, {
    weekday: "long",
    day: "numeric",
    month: "long",
  });
  const lead = `${name}, ${day}: ${VERDICT_LABELS[night.verdict]}`;
  if (night.darkness === "none" || night.runs.length === 0) {
    return `${lead}; no darkness: the Sun stays within 6° of the horizon`;
  }
  // Runs are contiguous within a darkness interval; a gap means the Sun came back up.
  const spans: { start: string; end: string }[] = [];
  night.runs.forEach((run, index) => {
    const previous = night.runs[index - 1];
    if (previous && previous.end_utc === run.start_utc) {
      spans[spans.length - 1].end = run.end;
    } else {
      spans.push({ start: run.start, end: run.end });
    }
  });
  const range = spans.map((span) => `${span.start}–${span.end}`).join(" and ");
  const note = night.darkness === "astronomical" ? "" : ` (${SHALLOW_NOTE[night.darkness]})`;
  const moon =
    night.runs
      .filter((run) => run.moon_up)
      .map((run) => `Moon up ${run.start}–${run.end}`)
      .join("; ") || "Moon down throughout";
  return `${lead}; ${night.dark_hours.toFixed(1)} h of ${night.darkness} darkness, ${range}${note}; ${moon}; ${night.moonless_dark_hours.toFixed(1)} h with the Moon down`;
}

export interface DarknessLine {
  /** Percent of the line from its start, for each run. */
  segments: { left: number; width: number; moonUp: boolean }[];
  /** Percent of the line at local midnight; null when midnight falls outside it. */
  midnight: number | null;
}

/** Positions along one night's line, which runs from the start to the end of its darkness. */
export function darknessLine(night: Pick<FortnightNight, "runs" | "midnight_utc">): DarknessLine | null {
  if (night.runs.length === 0) return null;
  const start = Date.parse(night.runs[0].start_utc);
  const end = Date.parse(night.runs[night.runs.length - 1].end_utc);
  const span = end - start;
  if (!(span > 0)) return null;
  const percent = (value: number) => ((value - start) / span) * 100;
  const midnight = Date.parse(night.midnight_utc);
  return {
    segments: night.runs.map((run) => ({
      left: percent(Date.parse(run.start_utc)),
      width: percent(Date.parse(run.end_utc)) - percent(Date.parse(run.start_utc)),
      moonUp: run.moon_up,
    })),
    midnight: midnight > start && midnight < end ? percent(midnight) : null,
  };
}

function isoLocal(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function fortnightDates(now: Date): string[] {
  const first = new Date(now);
  if (first.getHours() < 12) first.setDate(first.getDate() - 1);
  first.setHours(12, 0, 0, 0);
  return Array.from({ length: 14 }, (_, index) => {
    const night = new Date(first);
    night.setDate(first.getDate() + index);
    return isoLocal(night);
  });
}

export type ForecastRowStatus = "pending" | "success" | "error";

export function rowEnabled(index: number, statuses: ForecastRowStatus[]): boolean {
  if (index === 0) return true;
  return statuses
    .slice(0, index)
    .every((status) => status === "success" || status === "error");
}

export function yearSentence(year: YearSummary): {
  hours: string;
  nights: string;
  pictures: string;
} {
  return {
    hours: formatHours(year.minutes),
    nights: `${year.nights} ${year.nights === 1 ? "night" : "nights"}`,
    pictures: `${year.new_pictures} new ${year.new_pictures === 1 ? "picture" : "pictures"}`,
  };
}
