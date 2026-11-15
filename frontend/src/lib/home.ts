import type { MonthSummary, StageCounts, YearSummary } from "@/api/home";
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

export function forecastCellLabel(
  name: string,
  date: string,
  verdict: Verdict,
  hours: number,
): string {
  const night = formatDate(date, {
    weekday: "long",
    day: "numeric",
    month: "long",
  });
  return `${name}, ${night}: ${VERDICT_LABELS[verdict]}; ${hours.toFixed(1)} h of dark sky with the Moon down`;
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
