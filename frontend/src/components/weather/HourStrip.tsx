import type { ComponentType } from "react";
import Box from "@mui/material/Box";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import type { SvgIconProps } from "@mui/material/SvgIcon";
import type { CSSObject, Theme } from "@mui/material/styles";
import { createSvgIcon } from "@mui/material/utils";
import AirIcon from "@mui/icons-material/Air";
import CallSplitIcon from "@mui/icons-material/CallSplit";
import CloudIcon from "@mui/icons-material/Cloud";
import DarkModeIcon from "@mui/icons-material/DarkMode";
import WaterDropIcon from "@mui/icons-material/WaterDrop";
import type { Hour, Night } from "@/api/weather";
import { cellsFor, GO_MARK, type ClockColumn } from "@/lib/weatherVerdict";
import { weatherPalette, type DarknessLevel } from "@/lib/weatherPalette";

export type HourCellKind = "dim" | "clear" | "limit" | "models" | "unknown";

// Slanted streaks read as precipitation even at 8 px, where the stock
// umbrella icon blurs into an unrecognisable shape (Fred's pick, 2026-10-17).
const PrecipitationIcon = createSvgIcon(
  <path d="M8 3 5 10M14 3l-3 7M20 3l-3 7M11 13l-3 7M17 13l-3 7" fill="none" stroke="currentColor" strokeWidth={2.8} strokeLinecap="round" />,
  "Precipitation",
);
export type ConditionKey = "cloud" | "rain" | "wind" | "dew" | "moon";

// Fred chose icons over colour codes: a cell shows only the conditions that
// are over the limit for that hour, so no legend lookup is needed.
// eslint-disable-next-line react-refresh/only-export-components
export const CONDITION_ICONS: Record<ConditionKey, { Icon: ComponentType<SvgIconProps>; label: string }> = {
  cloud: { Icon: CloudIcon, label: "cloud" },
  rain: { Icon: PrecipitationIcon, label: "precipitation" },
  wind: { Icon: AirIcon, label: "wind" },
  dew: { Icon: WaterDropIcon, label: "dew" },
  moon: { Icon: DarkModeIcon, label: "Moon up" },
};
const CONDITION_ORDER: ConditionKey[] = ["cloud", "rain", "wind", "dew", "moon"];

// The strip and its hour axis share one column layout so labels line up.
function stripColumns(count: number, compact: boolean) {
  return {
    display: "grid",
    gridTemplateColumns: `repeat(${Math.max(count, 1)}, minmax(${compact ? 16 : 24}px, 1fr))`,
    gap: compact ? "2px" : "3px",
    minWidth: count * (compact ? 18 : 27),
  };
}

const ICON_GAP_PX = 1;
const ICON_INSET_PX = 2;

// Largest icon size for `count` icons in this cell: try every column count,
// take the size that fits both width and height, and keep the best. Sized in
// container units, so it follows each cell's actual width and height.
function iconSize(count: number): string {
  const fits: string[] = [];
  for (let columns = 1; columns <= count; columns += 1) {
    const rows = Math.ceil(count / columns);
    const width = `(100cqw - ${2 * ICON_INSET_PX + (columns - 1) * ICON_GAP_PX}px) / ${columns}`;
    const height = `(100cqh - ${2 * ICON_INSET_PX + (rows - 1) * ICON_GAP_PX}px) / ${rows}`;
    fits.push(`min(${width}, ${height})`);
  }
  return fits.length > 1 ? `max(${fits.join(", ")})` : fits[0];
}

function iconSx(count: number) {
  const size = iconSize(count);
  return { width: size, height: size };
}

// Shared with the legend so its swatches exactly match forecast cells.
// eslint-disable-next-line react-refresh/only-export-components
export function hourCellStyles(kind: HourCellKind, theme: Theme): CSSObject {
  const p = weatherPalette(theme);
  const base: CSSObject = { borderRadius: "3px" };
  switch (kind) {
    case "clear":
      return { ...base, backgroundColor: p.clearCell };
    case "limit":
      return { ...base, backgroundColor: p.limitCell };
    case "models":
      return { ...base, backgroundColor: p.modelsCell };
    case "unknown":
      return { ...base, backgroundColor: "transparent", border: `1px dashed ${p.unknownBorder}` };
    default:
      return { ...base, backgroundColor: p.twilightGround, border: `1px solid ${p.twilightBorder}` };
  }
}

// Icons follow `conditions` (every rule judged for every hour), so twilight and
// outside-imaging hours show the whole forecast picture; the cell ground still
// marks them as outside imaging time. Elapsed hours stay blank.
function failedConditions(hour: Hour): ConditionKey[] {
  return hour.elapsed ? [] : CONDITION_ORDER.filter((key) => hour.conditions[key] === "fail");
}

function cellKind(hour: Hour, night: Night): HourCellKind {
  if (hour.elapsed || hour.excluded || hour.state === "outside") return "dim";
  if (night.verdict === "uncertain" && hour.disagrees) return "models";
  if (hour.state === "unknown") return "unknown";
  return hour.state === "clear" ? "clear" : "limit";
}

export function HourAxis({ clock, compact = false }: { clock: ClockColumn[]; compact?: boolean }) {
  return (
    <Box sx={stripColumns(clock.length, compact)}>
      {clock.map((column, index) => (
        <Typography
          key={`${column.time}-${index}`}
          variant="caption"
          color="text.secondary"
          sx={{ whiteSpace: "nowrap", ...(compact && { fontSize: "0.6875rem", lineHeight: 1.3 }) }}
        >
          {column.label}
        </Typography>
      ))}
    </Box>
  );
}

const DARKNESS: { level: DarknessLevel; key: "astronomical" | "nautical" | "civil" | null; name: string; labels: string[] }[] = [
  { level: "astro", key: "astronomical", name: "Astronomical darkness (sun below −18°)", labels: ["astronomical", "astro", "A"] },
  { level: "nautical", key: "nautical", name: "Nautical darkness (sun below −12°)", labels: ["nautical", "naut", "N"] },
  { level: "civil", key: "civil", name: "Civil darkness (sun below −6°)", labels: ["civil", "civ", "C"] },
  { level: "day", key: null, name: "Sun above −6°", labels: ["day"] },
];

function nextClockTime(time: string): string {
  const hour = (Number.parseInt(time.slice(0, 2), 10) + 1) % 24;
  return `${String(hour).padStart(2, "0")}:${time.slice(3, 5)}`;
}

/**
 * Darkness levels drawn at the actual times the sun crosses −6°, −12° and
 * −18°, placed on the strip's own column geometry. Hourly labels would hide
 * the half-hour twilight stretches (Fred, 2026-10-17).
 */
export function DarknessBand({
  night,
  clock,
  compact = false,
  height = 16,
}: {
  night: Night;
  clock: ClockColumn[];
  compact?: boolean;
  height?: number;
}) {
  const columns = clock.length;
  if (columns === 0) return null;
  const gapPx = compact ? 2 : 3;
  const columnPx = compact ? 22 : 30;
  const cells = cellsFor(night, clock);
  const ranges = Object.fromEntries(
    (["astronomical", "nautical", "civil"] as const).map((key) => [
      key,
      night.darkness_intervals[key].map(({ start_utc, end_utc }) =>
        [Date.parse(start_utc), Date.parse(end_utc)] as const),
    ]),
  ) as Record<"astronomical" | "nautical" | "civil", (readonly [number, number])[]>;
  const levelAt = (timestamp: number) =>
    DARKNESS.find(({ key }) => key == null || ranges[key].some(([from, to]) => timestamp >= from && timestamp < to))!;
  const x = (column: number, subcell: number, subcells: number, fraction: number) => {
    const outerGaps = (columns - 1) * gapPx;
    const innerGaps = subcells - 1;
    const withinColumn = (subcell + fraction) / subcells;
    const fractionAcrossStrip = (column + withinColumn) / columns;
    const pixelOffset = column * gapPx + subcell - fractionAcrossStrip * outerGaps - withinColumn * innerGaps;
    return `(${fractionAcrossStrip * 100}% + ${pixelOffset}px)`;
  };
  const locate = (timestamp: number) => {
    for (let column = 0; column < cells.length; column += 1) {
      const hours = cells[column];
      for (let subcell = 0; subcell < hours.length; subcell += 1) {
        const start = Date.parse(hours[subcell].start_utc);
        const end = start + 60 * 60 * 1000;
        if (timestamp >= start && timestamp < end) {
          const fraction = (timestamp - start) / (end - start);
          return {
            position: column + (subcell + fraction) / hours.length,
            x: x(column, subcell, hours.length, fraction),
          };
        }
      }
    }
    const lastColumn = cells.findLastIndex((hours) => hours.length > 0);
    if (lastColumn >= 0) {
      const hours = cells[lastColumn];
      const last = hours.at(-1)!;
      if (timestamp === Date.parse(last.start_utc) + 60 * 60 * 1000) {
        return { position: lastColumn + 1, x: x(lastColumn, hours.length - 1, hours.length, 1) };
      }
    }
    return null;
  };
  type BandPoint = { position: number; x: string; time: string; timestamp: number | null };
  const points: BandPoint[] = [
    { position: 0, x: "(0px)", time: clock[0].time, timestamp: null },
    { position: columns, x: "(100%)", time: nextClockTime(clock.at(-1)!.time), timestamp: null },
  ];
  for (const intervals of Object.values(night.darkness_intervals)) {
    for (const interval of intervals) {
      for (const [timestamp, time] of [
        [Date.parse(interval.start_utc), interval.start],
        [Date.parse(interval.end_utc), interval.end],
      ] as const) {
        const location = locate(timestamp);
        if (location && location.position > 0 && location.position < columns) {
          points.push({ ...location, time, timestamp });
        }
      }
    }
  }
  points.sort((left, right) => left.position - right.position);
  const cuts = points.filter((point, index) => index === 0 || point.position !== points[index - 1].position);
  const firstHour = night.hours[0] ? Date.parse(night.hours[0].start_utc) : 0;
  const lastHour = night.hours.at(-1) ? Date.parse(night.hours.at(-1)!.start_utc) + 60 * 60 * 1000 : firstHour;
  const segments: { level: (typeof DARKNESS)[number]; from: BandPoint; to: BandPoint }[] = [];
  for (let index = 0; index < cuts.length - 1; index += 1) {
    const from = cuts[index];
    const to = cuts[index + 1];
    const sampleFrom = from.timestamp ?? firstHour;
    const sampleTo = to.timestamp ?? lastHour;
    const level = levelAt((sampleFrom + sampleTo) / 2);
    const last = segments.at(-1);
    if (last && last.level === level) last.to = to;
    else segments.push({ level, from, to });
  }
  return (
    <Box sx={{ position: "relative", height, minWidth: columns * (compact ? 18 : 27) }}>
      {segments.map(({ level, from, to }) => {
        const widthPx = (to.position - from.position) * columnPx;
        const label = level.labels.find((text) => text.length * 6 <= widthPx - 3) ?? "";
        return (
          <Tooltip key={`${from.position}-${to.position}`} enterTouchDelay={0} arrow title={`${level.name} · ${from.time}–${to.time}`}>
            <Box
              role="img"
              aria-label={`${level.name}, ${from.time} to ${to.time}`}
              sx={(theme) => {
                const colours = weatherPalette(theme).darkness[level.level];
                return {
                  position: "absolute",
                  top: 0,
                  bottom: 0,
                  left: `calc${from.x}`,
                  width: `calc(${to.x} - ${from.x} - 1px)`,
                  borderRadius: "3px",
                  bgcolor: colours.ground,
                  color: colours.text,
                  border: colours.border ? `1px solid ${colours.border}` : "none",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  overflow: "hidden",
                  fontSize: compact ? "0.625rem" : "0.6875rem",
                  lineHeight: 1,
                  whiteSpace: "nowrap",
                };
              }}
            >
              {label}
            </Box>
          </Tooltip>
        );
      })}
    </Box>
  );
}

export default function HourStrip({
  night,
  clock,
  height = 34,
  compact = false,
}: {
  night: Night;
  clock: ClockColumn[];
  height?: number;
  /** Narrower columns for the Tonight card; the week view keeps 24 px. */
  compact?: boolean;
}) {
  const cells = cellsFor(night, clock);
  const repeatedTimes = new Set(
    night.hours
      .filter((hour, index, hours) => hours.findIndex((candidate) => candidate.time === hour.time) !== index)
      .map((hour) => hour.time),
  );
  return (
    <Box sx={stripColumns(clock.length, compact)}>
      {cells.map((hours, columnIndex) => (
        <Box key={`${clock[columnIndex]?.time ?? columnIndex}-${columnIndex}`} sx={{ display: "flex", gap: "1px" }}>
          {hours.length === 0 ? (
            <Box
              aria-label={`${clock[columnIndex]?.label}: no clock hour`}
              sx={{ width: "100%", height, borderRadius: "3px", bgcolor: "action.hover", opacity: 0.35 }}
            />
          ) : (
            hours.map((hour) => {
              const kind = cellKind(hour, night);
              const failures = failedConditions(hour);
              const icon = iconSx(failures.length + (kind === "models" ? 1 : 0));
              const status = hour.excluded
                ? "outside your imaging times"
                : kind === "dim"
                  ? "twilight"
                  : kind === "models"
                    ? "cloud forecasts disagree"
                    : kind === "unknown"
                      ? "missing forecast data"
                      : null;
              const overLimit = failures.map((key) => `${CONDITION_ICONS[key].label} over your limit`).join(", ");
              const details = hour.elapsed
                ? "elapsed"
                : [status, overLimit].filter(Boolean).join(" · ") || "usable · every rule passes";
              const localTime = hour.time.slice(11, 16);
              const offsetMinutes = Math.round(
                (Date.parse(`${hour.time}:00Z`) - Date.parse(hour.start_utc)) / 60_000,
              );
              const offset = `${offsetMinutes >= 0 ? "+" : "-"}${String(Math.floor(Math.abs(offsetMinutes) / 60)).padStart(2, "0")}:${String(Math.abs(offsetMinutes) % 60).padStart(2, "0")}`;
              const timeLabel = repeatedTimes.has(hour.time) ? `${localTime} ${offset}` : localTime;
              return (
                <Tooltip key={hour.start_utc} enterTouchDelay={0} title={`${timeLabel} · ${details}`} arrow>
                  <Box
                    role="img"
                    aria-label={`${timeLabel}: ${details}`}
                    sx={(theme) => ({
                      ...hourCellStyles(kind, theme),
                      width: "100%",
                      minWidth: 0,
                      height,
                      outline: "none",
                      display: "flex",
                      flexWrap: "wrap",
                      alignContent: "center",
                      justifyContent: "center",
                      gap: `${ICON_GAP_PX}px`,
                      containerType: "size",
                      overflow: "hidden",
                      color: weatherPalette(theme).iconLit,
                    })}
                  >
                    {kind === "clear" && failures.length === 0 && (
                      // The Go pill's mark: every rule passes this hour.
                      <Box
                        component="span"
                        aria-hidden
                        sx={(theme) => ({
                          fontSize: `calc(${iconSize(1)} * 0.75)`,
                          lineHeight: 1,
                          fontWeight: 700,
                          color: weatherPalette(theme).onClearCell,
                        })}
                      >
                        {GO_MARK}
                      </Box>
                    )}
                    {kind === "models" && (
                      <CallSplitIcon
                        aria-hidden
                        sx={(theme) => ({ ...icon, color: weatherPalette(theme).neutralText })}
                      />
                    )}
                    {failures.map((key) => {
                      const { Icon } = CONDITION_ICONS[key];
                      return <Icon key={key} aria-hidden sx={icon} />;
                    })}
                  </Box>
                </Tooltip>
              );
            })
          )}
        </Box>
      ))}
    </Box>
  );
}
