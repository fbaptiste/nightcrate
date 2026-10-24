import type { Hour, Night, NightExtremes, Reason } from "@/api/weather";
import type { WeatherUnits } from "@/api/settings";

export interface ClockColumn {
  hour: number;
  time: string;
  label: string;
}

/** The Go pill's mark, also drawn in hour cells where every rule passes. */
export const GO_MARK = "✓";

/** Nights shown as the main forecast; the rest of the 14 are the outlook. */
export const WEEK_NIGHTS = 7;

export const WEATHER_ROW_DATE_WIDTH = 105;
export const WEATHER_ROW_VERDICT_WIDTH = 150;
export const WEATHER_ROW_SUMMARY_WIDTH = 310;
export const WEATHER_ROW_GAP = 12;
export const WEATHER_DETAIL_LABEL_WIDTH =
  WEATHER_ROW_DATE_WIDTH + WEATHER_ROW_VERDICT_WIDTH + WEATHER_ROW_GAP;
export const WEATHER_ROW_COLUMNS = `${WEATHER_ROW_DATE_WIDTH}px ${WEATHER_ROW_VERDICT_WIDTH}px minmax(420px, 1fr) ${WEATHER_ROW_SUMMARY_WIDTH}px`;
export const WEATHER_ROW_TABLET_COLUMNS = `${WEATHER_ROW_DATE_WIDTH}px ${WEATHER_ROW_VERDICT_WIDTH}px minmax(0, 1fr)`;

export function formatNightDate(date: string): string {
  return new Intl.DateTimeFormat(undefined, {
    weekday: "short",
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  }).format(new Date(`${date}T12:00:00Z`));
}

function minutesFromNoon(time: string): number {
  const hour = Number.parseInt(time.slice(0, 2), 10);
  return (hour >= 12 ? hour - 12 : hour + 12) * 60 + Number.parseInt(time.slice(3, 5), 10);
}

/** Preserve UTC order within each local clock-hour, including repeated DST hours. */
export function groupHoursByLocalHour(hours: Hour[]): Map<number, Hour[]> {
  const groups = new Map<number, Hour[]>();
  for (const entry of hours) {
    const hour = Number.parseInt(entry.time.slice(11, 13), 10);
    const group = groups.get(hour);
    if (group) group.push(entry);
    else groups.set(hour, [entry]);
  }
  return groups;
}

export function buildClock(nights: Night[]): ClockColumn[] {
  const wholeHourZone = nights.every((night) =>
    night.hours.every((hour) => hour.time.slice(14, 16) === "00"),
  );
  if (wholeHourZone) {
    if (nights.length === 0) return [];
    let first = 24;
    let last = 0;
    for (const night of nights) {
      const start = Math.floor(minutesFromNoon(night.gear_out_start) / 60);
      let endBase = Math.floor(minutesFromNoon(night.gear_out_end) / 60);
      const endMinutes = Number.parseInt(night.gear_out_end.slice(3, 5), 10);
      if (endBase <= start) endBase += 24;
      first = Math.min(first, start);
      last = Math.max(last, endBase + (endMinutes > 0 ? 1 : 0));
    }
    const length = Math.max(0, last - first);
    return Array.from({ length }, (_, index) => {
      const hour = (first + index + 12) % 24;
      const time = `${String(hour).padStart(2, "0")}:00`;
      const label = String(hour).padStart(2, "0");
      return { hour, time, label: index === 0 || index === length - 1 ? `${label}h` : label };
    });
  }

  const groups = groupHoursByLocalHour(nights.flatMap((night) => night.hours));
  const hours = [...groups.keys()].sort(
    (left, right) => minutesFromNoon(`${String(left).padStart(2, "0")}:00`)
      - minutesFromNoon(`${String(right).padStart(2, "0")}:00`),
  );
  return hours.map((hour, index) => {
    const label = String(hour).padStart(2, "0");
    const edge = index === 0 || index === hours.length - 1;
    const minutes = groups.get(hour)!.map((entry) => entry.time.slice(14, 16));
    const minute = index === 0
      ? minutes.reduce((earliest, value) => value < earliest ? value : earliest)
      : index === hours.length - 1
        ? minutes.reduce((latest, value) => value > latest ? value : latest)
        : "00";
    const time = `${label}:${minute}`;
    // Fred: mark the first and last hour so the axis reads as times.
    return { hour, time, label: edge ? (minute === "00" ? `${label}h` : time) : label };
  });
}

export function cellsFor(night: Night, clock: ClockColumn[]): Hour[][] {
  const groups = groupHoursByLocalHour(night.hours);
  return clock.map(({ hour }) => groups.get(hour) ?? []);
}

function compact(value: number | null, digits = 1): string {
  if (value == null) return "—";
  return Number.isInteger(value) ? String(value) : value.toFixed(digits).replace(/\.0$/, "");
}

const REQUIREMENTS: Record<string, string> = {
  cloud: "Cloud",
  rain: "Precipitation",
  wind: "Wind",
  dew: "Dew",
  moon: "Moon",
  unknown: "Missing forecast data",
};

const MODEL_NAMES: Record<string, string> = {
  ecmwf_ifs025: "ECMWF",
  gfs_seamless: "GFS",
  icon_seamless: "ICON",
  best_match: "Open-Meteo default",
};

const MODEL_STATUS_NAMES = {
  go: "Go",
  no: "No",
  unresolved: "incomplete",
  not_expected: "not expected",
} as const;

function range(start: string | null, end: string | null): string {
  if (start && end) return `${start}–${end}`;
  return start ?? end ?? "—";
}

function layerName(requirement: string | null): string {
  if (!requirement) return "Cloud-layer";
  return `${requirement[0].toUpperCase()}${requirement.slice(1)}-cloud`;
}

export function reasonText(reason: Reason, units: WeatherUnits): string {
  const prefix = reason.bound === "at_most" ? "at most " : reason.bound === "at_least" ? "at least " : "";
  const suffix = reason.bound ? ", even if the missing hours are usable" : "";
  const value = `${prefix}${compact(reason.value)}`;
  const start = reason.start ?? "—";
  const end = reason.end ?? "—";
  const limit = compact(reason.limit);
  switch (reason.code) {
    case "rain": {
      return `Precipitation chance up to ${value}% from ${start} to ${end} — your limit is ${limit}%${suffix}`;
    }
    case "rain_amount": return `Precipitation forecast (${prefix}${formatAmount(reason.value, units)}/h) ${range(reason.start, reason.end)}${suffix}`;
    case "rain_model_amount": return `${modelName(reason.model ?? "")}: ${prefix}${formatAmount(reason.value, units)}/h ${range(reason.start, reason.end)}${suffix}`;
    case "rain_missing": return `${reason.model ? `${modelName(reason.model)} precipitation` : "Precipitation"} not forecast ${range(reason.start, reason.end)}`;
    case "clear_fraction": return `${value}% of dark time usable — you need at least ${limit}%${suffix}`;
    case "min_hours": return `Usable time: ${value} h — you need at least ${limit} h${suffix}`;
    case "gap": return `No usable time for ${value} h from ${start} — longest interruption allowed is ${limit} h${suffix}`;
    case "no_window": return `No usable stretch of ${limit} h — longest is ${value} h${suffix}`;
    case "short_window": return `Usable for your session: ${start}–${end}`;
    case "clear_all_night": return "Usable all night";
    case "clear_with_gaps": return `${REQUIREMENTS[reason.requirement ?? "unknown"] ?? reason.requirement ?? "Not usable"} ${start}–${end}`;
    case "never_dark": return "Never dark enough for your setting";
    case "no_dark_time": return `No dark time before your stop time (${start})`;
    case "models_disagree":
      return `Cloud forecasts give different session results: ${Object.entries(reason.models ?? {}).map(([model, status]) => `${modelName(model)} ${MODEL_STATUS_NAMES[status]}`).join(", ")}`;
    case "forecasts_differ": {
      const total = reason.limit ?? 0;
      return `Cloud forecasts differ on ${compact(reason.value)} of ${compact(total)} ${total === 1 ? "hour" : "hours"} — using the majority`;
    }
    case "missing_data": return `${REQUIREMENTS[reason.requirement ?? "unknown"] ?? reason.requirement ?? "Data"} not forecast from ${start}`;
    case "model_incomplete": {
      const when = reason.start || reason.end
        ? ` ${range(reason.start, reason.end)}`
        : reason.missing_hours != null
          ? ` (${compact(reason.missing_hours)} h missing)`
          : "";
      return `${modelName(reason.model ?? "Forecast")} cloud data missing${when} — refresh later`;
    }
    case "no_shared_window": return `No shared usable stretch of ${limit} h`;
    case "model_not_used": return reason.end
      ? `${modelName(reason.model ?? "Model")} cloud forecast ends at ${reason.end}`
      : `${modelName(reason.model ?? "Model")} cloud forecast does not reach this night`;
    case "fallback": return "Using Open-Meteo’s default cloud forecast where the selected forecasts do not reach";
    case "layer_advisory": return `${layerName(reason.requirement)} estimate up to ${value}%; ${start}–${end} (limit ${limit}%) — not counted toward the verdict`;
    case "stale": return `forecast ${Math.round((reason.value ?? 0) / 60)} h old, refresh failed`;
    case "night_over": return "Night over";
    default: return reason.code.replaceAll("_", " ");
  }
}

export function reasonLine(night: Night, units: WeatherUnits = "metric"): string {
  const precipitation = new Set(["rain", "rain_amount", "rain_model_amount", "rain_missing"]);
  const session = new Set(["clear_fraction", "min_hours", "gap", "no_window"]);
  const models = new Set(["models_disagree", "no_shared_window", "model_incomplete"]);
  const category = (reason: Reason) => {
    if (precipitation.has(reason.code)) return "precipitation";
    if (session.has(reason.code)) return "session";
    if (models.has(reason.code)) return "models";
    return null;
  };
  const headlineCategory = category(night.reason);
  const blocker = night.other_reasons.find((reason) => {
    const otherCategory = category(reason);
    return otherCategory !== null && otherCategory !== headlineCategory;
  });
  const blockerText = blocker == null
    ? null
    : category(blocker) === "session"
      ? `usable time is ${formatHours(night.clear_hours)} of ${formatHours(night.dark_hours)} h`
      : blocker.code === "rain_missing"
        ? "precipitation not forecast for some hours"
        : category(blocker) === "precipitation"
          ? "precipitation also over your limit"
          : blocker.code === "model_incomplete"
            ? `${modelName(blocker.model ?? "Model")} incomplete`
            : "cloud forecasts disagree";
  const qualifier = night.other_reasons.find((reason) =>
    reason.code === "fallback" || reason.code === "model_not_used",
  );
  return [
    reasonText(night.reason, units),
    blockerText,
    qualifier ? reasonText(qualifier, units) : null,
  ].filter((text): text is string => text !== null).join("; ");
}

export function formatTemperature(valueC: number | null, units: WeatherUnits): string {
  if (valueC == null) return "—";
  return units === "imperial" ? `${compact((valueC * 9) / 5 + 32)} °F` : `${compact(valueC)} °C`;
}

export function formatWind(valueKmh: number | null, units: WeatherUnits): string {
  if (valueKmh == null) return "—";
  return units === "imperial" ? `${compact(valueKmh * 0.621371)} mph` : `${compact(valueKmh)} km/h`;
}

export function formatAmount(valueMm: number | null, units: WeatherUnits): string {
  if (valueMm == null) return "—";
  const imperial = units === "imperial";
  const value = imperial ? valueMm / 25.4 : valueMm;
  const digits = imperial ? 2 : 1;
  const smallest = imperial ? 0.01 : 0.1;
  const rounded = Number(value.toFixed(digits));
  if (value > 0 && rounded === 0) return `<${smallest.toFixed(digits)} ${imperial ? "in" : "mm"}`;
  return `${compact(rounded, digits)} ${imperial ? "in" : "mm"}`;
}

export function formatTotal(extremes: NightExtremes, units: WeatherUnits): string {
  const amount = formatAmount(extremes.precip_mm_total, units);
  if (extremes.precip_missing_hours === 0) return amount;
  const hours = extremes.precip_missing_hours;
  return `Forecast-hour sum ≥ ${amount}; ${hours} ${hours === 1 ? "hour" : "hours"} missing`;
}

export function formatDewSpread(valueC: number | null, units: WeatherUnits): string {
  if (valueC == null) return "—";
  return units === "imperial" ? `${compact((valueC * 9) / 5)} °F` : `${compact(valueC)} °C`;
}

export function formatHours(value: number): string {
  return compact(value);
}

export function modelName(model: string): string {
  return MODEL_NAMES[model] ?? model;
}

// Facts from Open-Meteo's model documentation (checked 2026-10-17).
const MODEL_DESCRIPTIONS: Record<string, string> = {
  ecmwf_ifs025:
    "ECMWF IFS — the European Centre for Medium-Range Weather Forecasts' global model, open-data version at 0.25° (~25 km). " +
    "Forecasts 15 days ahead, updated every 6 hours; values every 3 hours, every 6 hours after day 6.",
  gfs_seamless:
    "GFS — NOAA's Global Forecast System (US). Global at ~13 km, 16 days ahead, updated every 6 hours. " +
    "Over the contiguous US, Open-Meteo combines it with NOAA's 3 km HRRR model for the first hours.",
  icon_seamless:
    "ICON — the German Weather Service's (DWD) model. Global at ~11 km, 7.5 days ahead, updated every 6 hours; " +
    "over Europe, Open-Meteo combines it with the finer ICON-EU (~7 km), and over central Europe with ICON-D2 (~2 km).",
  best_match: "Open-Meteo's default blend of the best available models for this location.",
};

export function modelDescription(model: string): string | null {
  return MODEL_DESCRIPTIONS[model] ?? null;
}
