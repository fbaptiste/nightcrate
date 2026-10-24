import { useEffect, useMemo, useRef, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import FormControl from "@mui/material/FormControl";
import FormControlLabel from "@mui/material/FormControlLabel";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import type { Theme } from "@mui/material/styles";
import type {
  CheckState,
  Hour,
  ImagingRules,
  ModelStatus,
  Night,
  NightControls,
} from "@/api/weather";
import type { WeatherUnits } from "@/api/settings";
import {
  cellsFor,
  formatAmount,
  formatDewSpread,
  formatHours,
  formatNightDate,
  formatTotal,
  formatWind,
  modelDescription,
  modelName,
  reasonText,
  WEATHER_DETAIL_LABEL_WIDTH,
  WEATHER_ROW_SUMMARY_WIDTH,
  type ClockColumn,
} from "@/lib/weatherVerdict";
import { cloudHatch, failHatch, weatherPalette } from "@/lib/weatherPalette";
import { monoFontFamily } from "@/theme/theme";
import { DarknessBand } from "./HourStrip";

const DETAIL_COLUMNS = `${WEATHER_DETAIL_LABEL_WIDTH}px minmax(420px, 1fr) ${WEATHER_ROW_SUMMARY_WIDTH}px`;
const DASH = "—";
const HOUR_MS = 60 * 60 * 1000;
const CHANCE_HELP = "An hour fails if its forecast chance is above this. In North America, beyond about 36 hours, one chance covers each 6-hour stretch and repeats in each hour.";
const CLOUD_MODEL_ORDER = ["ecmwf_ifs025", "gfs_seamless", "icon_seamless"] as const;

function number(value: number | null, suffix = ""): string {
  if (value == null) return DASH;
  const text = Number.isInteger(value) ? String(value) : value.toFixed(1).replace(/\.0$/, "");
  return `${text}${suffix}`;
}

function cellNumber(value: number | null, digits = 1): string {
  if (value == null) return DASH;
  return Number.isInteger(value)
    ? String(value)
    : value.toFixed(digits).replace(/\.?0+$/, "");
}

function precipitationCell(valueMm: number | null, units: WeatherUnits): string {
  return formatAmount(valueMm, units).replace(/ (?:mm|in)$/, "");
}

// Whole numbers: wind and gust share one cell in the "not counted" row, and a
// decimal on each overflows the hour column.
function windCell(valueKmh: number | null, units: WeatherUnits): string {
  return cellNumber(
    valueKmh == null ? null : Math.round(units === "imperial" ? valueKmh * 0.621371 : valueKmh),
  );
}

function spreadCell(valueC: number | null, units: WeatherUnits): string {
  return cellNumber(valueC == null ? null : units === "imperial" ? valueC * 9 / 5 : valueC);
}

function temperatureCell(valueC: number | null, units: WeatherUnits): string {
  return cellNumber(valueC == null ? null : units === "imperial" ? valueC * 9 / 5 + 32 : valueC);
}

function visibilityCell(valueM: number | null, units: WeatherUnits): string {
  if (valueM == null) return DASH;
  const value = units === "imperial" ? valueM / 1609.344 : valueM / 1000;
  return cellNumber(value);
}

function transparencyCell(hour: Hour): string {
  if (hour.transparency == null) return DASH;
  if (hour.transparency_tier === "fallback") return `${hour.transparency} — no aerosol data`;
  if (hour.transparency_tier === "degraded") return `${hour.transparency} — humidity-based`;
  return hour.transparency;
}

function timeOptions(night: Night, controls: NightControls): { value: string; label: string }[] {
  const options = night.hours.map((hour) => ({
    value: hour.start_utc,
    label: hour.time.slice(11, 16),
  }));
  const selectedEnds: [string | null, string | null][] = [
    [controls.gear_in, night.gear_out_end],
    [controls.imaging_until, night.evaluated_end ?? night.imaging?.end ?? null],
  ];
  selectedEnds.forEach(([value, label]) => {
    if (value && label && !options.some((option) => option.value === value)) {
      options.push({ value, label });
    }
  });
  return options;
}

function timestamp(value: string | null | undefined, fallback: number): number {
  if (!value) return fallback;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function chanceLimitText(rules: ImagingRules): string {
  return `limit ${number(rules.rain_max_probability_pct, "%")}`;
}

function amountRuleText(thresholdMm: number, units: WeatherUnits): string {
  return thresholdMm === 0
    ? "any amount fails"
    : `fails above ${formatAmount(thresholdMm, units)}/h`;
}

function layerLabel(name: "Low" | "Mid" | "High", estimated: boolean): React.ReactNode {
  const text = `${name} cloud %`;
  if (!estimated) return text;
  return (
    <Tooltip
      title="Open-Meteo estimates ECMWF's layers from humidity; they never count toward the verdict"
      arrow
      placement="top-start"
      enterTouchDelay={0}
    >
      <span>{text} (estimate, not counted)</span>
    </Tooltip>
  );
}

function stateMark(state: CheckState | "info"): string {
  if (state === "pass") return "✓";
  if (state === "fail") return "✕";
  if (state === "unknown") return "?";
  return "–";
}

function ChecklistLine({
  state,
  mark,
  children,
}: {
  state: CheckState | "info";
  mark?: string;
  children: React.ReactNode;
}) {
  return (
    <Box sx={{ display: "flex", gap: 1, alignItems: "baseline" }}>
      <Typography
        component="span"
        aria-hidden="true"
        sx={(theme) => {
          const p = weatherPalette(theme);
          return {
            width: 18,
            flex: "none",
            textAlign: "center",
            fontWeight: 700,
            color: mark ? p.neutralText : state === "fail" ? p.rainDot : state === "pass" ? p.clear : p.neutralText,
          };
        }}
      >
        {mark ?? stateMark(state)}
      </Typography>
      <Typography variant="body2" sx={{ lineHeight: 1.45 }}>{children}</Typography>
    </Box>
  );
}

type CellStatus = CheckState | "context";
type FailurePattern = "cloud" | "orange";

function metricCellSx(
  state: CellStatus,
  failurePattern: FailurePattern,
  outsideNight: boolean,
) {
  return (theme: Theme) => {
    const p = weatherPalette(theme);
    return {
      width: "100%",
      minWidth: 0,
      height: 26,
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      px: "2px",
      boxSizing: "border-box",
      borderRadius: "3px",
      fontFamily: monoFontFamily,
      fontSize: "0.75rem",
      lineHeight: 1,
      whiteSpace: "nowrap",
      overflow: "hidden",
      textOverflow: "ellipsis",
      backgroundColor: p.infoGround,
      color: p.onInfo,
      ...(state === "pass" && { backgroundColor: p.passGround, color: p.onPass }),
      ...(state === "fail" && failurePattern === "orange" && {
        backgroundImage: failHatch(p),
        color: p.onFail,
        fontWeight: 700,
      }),
      ...(state === "fail" && failurePattern === "cloud" && {
        backgroundImage: cloudHatch(p),
        color: p.onFail,
        fontWeight: 700,
      }),
      ...(state === "unknown" && {
        backgroundColor: "transparent",
        border: `1px dashed ${p.unknownBorder}`,
        color: p.neutralText,
      }),
      ...(state === "not_counted" && { backgroundColor: p.dimGround, color: p.onDim }),
      ...(outsideNight && { opacity: 0.55 }),
    };
  };
}

interface GridRowProps {
  night: Night;
  clock: ClockColumn[];
  label: React.ReactNode;
  summary: React.ReactNode;
  value: (hour: Hour) => string;
  /** Each row is judged on its own value against its own limit, never on the
   * hour's combined verdict. */
  status?: (hour: Hour) => CellStatus;
  notExpected?: (hour: Hour) => boolean;
  tooltip?: (hour: Hour) => string | null;
  dimmed?: boolean;
  failurePattern?: FailurePattern;
}

function GridRow({
  night,
  clock,
  label,
  summary,
  value,
  status,
  notExpected,
  tooltip,
  dimmed = false,
  failurePattern = "orange",
}: GridRowProps) {
  const cells = cellsFor(night, clock);
  return (
    <Box sx={{ display: "grid", gridTemplateColumns: DETAIL_COLUMNS, gap: 1.5, alignItems: "center", py: "3px" }}>
      <Typography variant="body2" sx={(theme) => ({ color: dimmed ? weatherPalette(theme).onDim : "text.primary" })}>{label}</Typography>
      <Box sx={{ display: "grid", gridTemplateColumns: `repeat(${Math.max(clock.length, 1)}, minmax(24px, 1fr))`, gap: "3px", minWidth: clock.length * 27 }}>
        {cells.map((hours, columnIndex) => (
          <Box key={`${clock[columnIndex]?.hour ?? columnIndex}-${columnIndex}`} sx={{ display: "flex", gap: "1px" }}>
            {hours.length === 0 ? <Box sx={{ width: "100%", height: 26 }} /> : hours.map((hour) => {
              const beyondCoverage = notExpected?.(hour) ?? false;
              const state: CellStatus = dimmed || beyondCoverage ? "not_counted" : status?.(hour) ?? "context";
              const outsideNight = hour.elapsed || hour.excluded || (hour.dark_minutes === 0 && hour.exposure_minutes === 0);
              return (
                <Box
                  key={hour.start_utc}
                  title={beyondCoverage
                    ? "forecast does not reach this hour — not counted"
                    : tooltip?.(hour) ?? `${hour.time.slice(11, 16)} · ${value(hour)}`}
                  sx={metricCellSx(state, failurePattern, outsideNight)}
                >
                  {value(hour)}
                </Box>
              );
            })}
          </Box>
        ))}
      </Box>
      <Typography variant="caption" sx={(theme) => ({ color: dimmed ? weatherPalette(theme).onDim : "text.secondary" })}>{summary}</Typography>
    </Box>
  );
}

/** Pass/fail of one value against one limit, for hours where it counts. */
function judge(counts: boolean, value: number | null, fails: (value: number) => boolean): CellStatus {
  if (!counts) return "context";
  if (value == null) return "unknown";
  return fails(value) ? "fail" : "pass";
}

function ChanceRow({ night, clock, rules }: { night: Night; clock: ClockColumn[]; rules: ImagingRules }) {
  const rainCounts = (hour: Hour) =>
    rules.rain_policy === "night_off" ? hour.exposure_minutes > 0 : hour.dark_minutes > 0;
  return (
    <GridRow
      night={night}
      clock={clock}
      label={<Tooltip title={CHANCE_HELP} arrow placement="top-start" enterTouchDelay={0}><span>Precipitation chance %</span></Tooltip>}
      summary={chanceLimitText(rules)}
      value={(hour) => cellNumber(hour.precip_probability_pct, 0)}
      status={(hour) => judge(rainCounts(hour), hour.precip_probability_pct, (value) => value > rules.rain_max_probability_pct)}
    />
  );
}

function GroupLabel({ children }: { children: React.ReactNode }) {
  return <Typography variant="overline" color="text.secondary" sx={{ display: "block", mt: 1.5, mb: 0.25, letterSpacing: "0.08em" }}>{children}</Typography>;
}

function TimeControl({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string | null;
  options: { value: string; label: string }[];
  onChange: (value: string | null) => void;
}) {
  return (
    <Stack direction="row" gap={0.75} alignItems="center">
      <Typography variant="body2" sx={{ whiteSpace: "nowrap" }}>{label}</Typography>
      <FormControl size="small" sx={{ minWidth: 105 }}>
        <Select
          displayEmpty
          value={value ?? ""}
          onChange={(event) => onChange(event.target.value || null)}
          inputProps={{ "aria-label": label }}
          renderValue={(selected) => selected === ""
            ? "Natural"
            : options.find((option) => option.value === selected)?.label ?? "Selected time"}
        >
          <MenuItem value="">Natural</MenuItem>
          {options.map((option) => <MenuItem key={option.value} value={option.value}>{option.label}</MenuItem>)}
        </Select>
      </FormControl>
    </Stack>
  );
}

const MODEL_STATUS_LABELS: Record<ModelStatus | "not_used", string> = {
  go: "Go",
  no: "No",
  unresolved: "incomplete",
  not_expected: "not expected",
  not_used: "not used",
};

function coverageText(night: Night): string {
  return night.coverage.map((coverage) => {
    const end = coverage.expected_until ? ` · through ${coverage.expected_until}` : "";
    return `${modelName(coverage.model)} — ${MODEL_STATUS_LABELS[coverage.status]}${end}`;
  }).join("; ");
}

function layerName(requirement: string | null): string {
  if (!requirement) return "Cloud-layer";
  return `${requirement[0].toUpperCase()}${requirement.slice(1)}-cloud`;
}

function advisoryText(night: Night): string | null {
  const advisory = night.advisory;
  if (!advisory || advisory.code !== "layer_advisory") return null;
  const start = advisory.start_utc ? Date.parse(advisory.start_utc) : Number.NaN;
  const end = advisory.end_utc ? Date.parse(advisory.end_utc) : Number.NaN;
  const totals = night.hours.flatMap((hour) => {
    const hourStart = Date.parse(hour.start_utc);
    const value = hour.cloud_pct[night.primary_model];
    return Number.isFinite(start) && Number.isFinite(end) && hourStart < end && hourStart + HOUR_MS > start && value != null
      ? [value]
      : [];
  });
  const totalRange = totals.length === 0
    ? DASH
    : Math.min(...totals) === Math.max(...totals)
      ? number(totals[0], "%")
      : `${number(Math.min(...totals))}–${number(Math.max(...totals), "%")}`;
  return `${layerName(advisory.requirement)} estimate up to ${number(advisory.value, "%")}; total cloud ${totalRange}, ${advisory.start ?? DASH}–${advisory.end ?? DASH} (limit ${number(advisory.limit, "%")}) — not counted toward the verdict`;
}

export default function NightDetailPanel({
  night,
  clock,
  rules,
  units,
  controls,
  onControlsChange,
  onClose,
}: {
  night: Night;
  clock: ClockColumn[];
  rules: ImagingRules;
  units: WeatherUnits;
  controls: NightControls;
  onControlsChange: (controls: NightControls) => void;
  onClose: () => void;
}) {
  const panelRef = useRef<HTMLDivElement>(null);
  const modelVisibilityKey = `${night.date}-${night.verdict}`;
  const [modelVisibility, setModelVisibility] = useState({
    key: modelVisibilityKey,
    show: night.cloud_models.length > 1,
  });
  const [separateImaging, setSeparateImaging] = useState(
    controls.imaging_from !== null || controls.imaging_until !== null,
  );
  const multipleModels = night.cloud_models.length > 1;
  const showModels = multipleModels || (
    modelVisibility.key === modelVisibilityKey ? modelVisibility.show : false
  );
  const allOptions = useMemo(() => timeOptions(night, controls), [controls, night]);
  const nextDate = useMemo(() => {
    const date = new Date(`${night.date}T12:00:00Z`);
    date.setUTCDate(date.getUTCDate() + 1);
    return date.toISOString().slice(0, 10);
  }, [night.date]);
  const selectedModels = useMemo(() => new Set(night.cloud_models), [night.cloud_models]);
  const cloudRows = showModels
    ? CLOUD_MODEL_ORDER
    : CLOUD_MODEL_ORDER.filter((model) => selectedModels.has(model)).slice(0, 1);
  const clearState = night.requirements.clear_time ?? "unknown";
  const primaryModel = night.primary_model;
  const noSharedWindow = [night.reason, ...night.other_reasons].some(
    (reason) => reason.code === "no_shared_window",
  );
  const modelRequirement = night.requirements.models ?? "not_counted";
  const modelMark = noSharedWindow || modelRequirement === "fail" || modelRequirement === "unknown" ? "?" : undefined;
  const usedCloudModels = night.cloud_models_used.map(modelName);
  const singleModel = usedCloudModels.join(" and ");
  const modelText = noSharedWindow
    ? `Cloud forecasts do not share a usable stretch of ${number(rules.short_session_hours)} h`
    : night.single_model
      ? usedCloudModels.length === 0
        ? night.default_cloud_used
          ? "Using Open-Meteo’s default cloud forecast"
          : "Cloud forecast data is incomplete"
        : night.default_cloud_used
          ? `Using ${singleModel} cloud and Open-Meteo’s default cloud forecast`
          : `Using ${singleModel} cloud`
      : modelRequirement === "info"
        ? "Cloud forecasts differ on some hours — using the majority"
        : modelRequirement === "fail"
          ? "Cloud forecasts give different session results"
          : modelRequirement === "unknown"
            ? "Cloud forecast data is incomplete"
            : modelRequirement === "pass"
              ? "Cloud forecasts agree hour by hour"
              : usedCloudModels.length > 0
                ? `Using ${singleModel} cloud`
                : night.default_cloud_used
                  ? "Using Open-Meteo’s default cloud forecast"
                  : "Cloud forecast data is incomplete";
  const rainCounts = (hour: Hour) =>
    rules.rain_policy === "night_off" ? hour.exposure_minutes > 0 : hour.dark_minutes > 0;
  const optionTimes = allOptions.map((option) => Date.parse(option.value)).filter(Number.isFinite);
  const firstOption = optionTimes.length > 0 ? Math.min(...optionTimes) : Number.NEGATIVE_INFINITY;
  const lastOption = optionTimes.length > 0 ? Math.max(...optionTimes) + HOUR_MS : Number.POSITIVE_INFINITY;
  const naturalGearStart = timestamp(night.exposure?.start_utc ?? night.gear_out_start_utc, firstOption);
  const naturalGearEnd = timestamp(night.exposure?.end_utc ?? night.gear_out_end_utc, lastOption);
  const naturalImagingStart = timestamp(
    night.imaging?.start_utc ?? night.dark_intervals[0]?.start_utc,
    naturalGearStart,
  );
  const naturalImagingEnd = timestamp(
    night.imaging?.end_utc ?? night.dark_intervals[night.dark_intervals.length - 1]?.end_utc,
    naturalGearEnd,
  );
  const effectiveGearStart = timestamp(controls.gear_out, naturalGearStart);
  const effectiveGearEnd = timestamp(controls.gear_in, naturalGearEnd);
  const defaultImagingStart = rules.rain_policy === "night_off"
    ? Math.max(naturalImagingStart, effectiveGearStart)
    : naturalImagingStart;
  const defaultImagingEnd = rules.rain_policy === "night_off"
    ? Math.min(naturalImagingEnd, effectiveGearEnd)
    : naturalImagingEnd;
  const effectiveImagingStart = timestamp(controls.imaging_from, defaultImagingStart);
  const effectiveImagingEnd = timestamp(controls.imaging_until, defaultImagingEnd);
  const gearOutOptions = allOptions.filter((option) => Date.parse(option.value) < effectiveGearEnd);
  const gearInOptions = allOptions.filter((option) => Date.parse(option.value) > effectiveGearStart);
  const imagingFromOptions = allOptions.filter((option) => {
    const value = Date.parse(option.value);
    return value < effectiveImagingEnd
      && (rules.rain_policy !== "night_off" || (value >= effectiveGearStart && value < effectiveGearEnd));
  });
  const imagingUntilOptions = allOptions.filter((option) => {
    const value = Date.parse(option.value);
    return value > effectiveImagingStart
      && (rules.rain_policy !== "night_off" || (value > effectiveGearStart && value <= effectiveGearEnd));
  });
  const advisory = advisoryText(night);
  const lastDarkEnd = Math.max(...night.dark_intervals.map((interval) => Date.parse(interval.end_utc)), Number.NEGATIVE_INFINITY);
  const gearIndoors = controls.gear_in !== null && Date.parse(controls.gear_in) < lastDarkEnd;
  const darkHours = night.hours.filter((hour) => hour.dark_minutes > 0);
  const coarseBoundary = night.cloud_coarse_from_utc ? Date.parse(night.cloud_coarse_from_utc) : Number.NaN;
  const coarseHours = darkHours.filter((hour) => Number.isFinite(coarseBoundary) && Date.parse(hour.start_utc) >= coarseBoundary);
  const resolutionText = coarseHours.length === 0
    ? null
    : coarseHours.length === darkHours.length
      ? "Cloud data may be 6-hourly all night"
      : `Cloud data may be 6-hourly from about ${night.cloud_coarse_from}`;
  const updateControl = (field: keyof NightControls, value: string | null) => {
    const next = { ...controls, [field]: value };
    let gearStart = timestamp(next.gear_out, naturalGearStart);
    let gearEnd = timestamp(next.gear_in, naturalGearEnd);
    if (gearStart >= gearEnd) {
      if (field === "gear_out") next.gear_in = null;
      else next.gear_out = null;
      gearStart = timestamp(next.gear_out, naturalGearStart);
      gearEnd = timestamp(next.gear_in, naturalGearEnd);
    }
    if (rules.rain_policy === "night_off") {
      if (next.imaging_from && !(gearStart <= Date.parse(next.imaging_from) && Date.parse(next.imaging_from) < gearEnd)) {
        next.imaging_from = null;
      }
      if (next.imaging_until && !(gearStart < Date.parse(next.imaging_until) && Date.parse(next.imaging_until) <= gearEnd)) {
        next.imaging_until = null;
      }
    }
    const imagingStart = timestamp(
      next.imaging_from,
      rules.rain_policy === "night_off" ? Math.max(naturalImagingStart, gearStart) : naturalImagingStart,
    );
    const imagingEnd = timestamp(
      next.imaging_until,
      rules.rain_policy === "night_off" ? Math.min(naturalImagingEnd, gearEnd) : naturalImagingEnd,
    );
    if (imagingStart >= imagingEnd) {
      if (field === "imaging_from") next.imaging_until = null;
      else if (field === "imaging_until") next.imaging_from = null;
      else {
        next.imaging_from = null;
        next.imaging_until = null;
      }
    }
    onControlsChange(next);
  };

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      panelRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [night.date]);

  return (
    <Paper ref={panelRef} variant="outlined" sx={{ mt: 2, p: 2, overflow: "hidden", scrollMarginTop: 16 }}>
      <Stack direction={{ xs: "column", md: "row" }} gap={1.5} alignItems={{ xs: "stretch", md: "center" }}>
        <Box>
          <Typography variant="h6">Night of {formatNightDate(night.date)} → {formatNightDate(nextDate)}</Typography>
          {night.evaluated_from && <Typography variant="caption" color="text.secondary">Verdict covers from {night.evaluated_from}</Typography>}
        </Box>
        <Stack direction="row" gap={1} alignItems="center" flexWrap="wrap" sx={{ ml: { md: "auto" } }}>
          {rules.rain_policy === "night_off" ? <>
            <TimeControl label="Gear out at" value={controls.gear_out} options={gearOutOptions} onChange={(value) => updateControl("gear_out", value)} />
            <TimeControl label={gearIndoors ? "Gear in at (gear indoors afterward)" : "Gear in at"} value={controls.gear_in} options={gearInOptions} onChange={(value) => updateControl("gear_in", value)} />
            <FormControlLabel
              control={<Checkbox
                checked={separateImaging}
                onChange={(event) => {
                  setSeparateImaging(event.target.checked);
                  if (!event.target.checked) {
                    onControlsChange({ ...controls, imaging_from: null, imaging_until: null });
                  }
                }}
                size="small"
              />}
              label="Imaging times differ from equipment times"
            />
            {separateImaging && <>
              <TimeControl label="Imaging from" value={controls.imaging_from} options={imagingFromOptions} onChange={(value) => updateControl("imaging_from", value)} />
              <TimeControl label="Imaging until" value={controls.imaging_until} options={imagingUntilOptions} onChange={(value) => updateControl("imaging_until", value)} />
            </>}
          </> : <>
            <TimeControl label="Imaging from" value={controls.imaging_from} options={imagingFromOptions} onChange={(value) => updateControl("imaging_from", value)} />
            <TimeControl label="Imaging until" value={controls.imaging_until} options={imagingUntilOptions} onChange={(value) => updateControl("imaging_until", value)} />
          </>}
          <Button variant="outlined" onClick={onClose}>Close</Button>
        </Stack>
      </Stack>

      <Box sx={{ mt: 1.5 }}>
        <Typography variant="subtitle2">Why</Typography>
        <Box component="ul" sx={{ m: 0, pl: 2.5 }}>
          {[night.reason, ...night.other_reasons].map((reason, index) => (
            <Typography component="li" variant="body2" key={`${reason.code}-${index}`}>
              {reasonText(reason, units)}
            </Typography>
          ))}
        </Box>
      </Box>

      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "repeat(2, minmax(0, 1fr))" }, gap: 1, bgcolor: "action.hover", borderRadius: 2, p: 1.5, mt: 1.5 }}>
        <ChecklistLine state={clearState}>
          Usable dark time: {formatHours(night.clear_hours)} of {formatHours(night.dark_hours)} h
          {night.cloud_combination === "uncertain" && (night.verdict === "uncertain" || night.verdict === "not_enough_data") ? ` (${modelName(primaryModel)})` : ""}
          {night.clear_pct != null ? ` · ${number(night.clear_pct, "%")}` : ""} — {rules.session_style === "all_night" ? `required: at least ${number(rules.min_clear_fraction_pct, "%")} and ${number(rules.min_clear_hours)} h` : `required: ${number(rules.short_session_hours)} h in a row`}
        </ChecklistLine>
        <ChecklistLine state={night.requirements.rain ?? "unknown"}>
          {rules.rain_policy === "night_off" ? `Precipitation while gear is out (${night.gear_out_start}–${night.gear_out_end})` : "Precipitation during imaging hours"}: peak reported chance {number(night.extremes.max_precip_probability_pct, "%")}{night.extremes.max_precip_probability_at ? ` at ${night.extremes.max_precip_probability_at}` : ""}; your limit is {number(rules.rain_max_probability_pct, "%")}; {formatTotal(night.extremes, units)}
        </ChecklistLine>
        <ChecklistLine state={modelRequirement} mark={modelRequirement === "info" ? "–" : modelMark}>{modelText}</ChecklistLine>
        <ChecklistLine state={night.requirements.wind ?? "not_counted"}>
          {rules.wind_counted ? `Gusts reach ${formatWind(night.extremes.max_gust_kmh, units)}${night.extremes.max_gust_at ? ` at ${night.extremes.max_gust_at}` : ""} — your limit is ${formatWind(rules.gust_max_kmh, units)}` : `Wind not counted — gusts reach ${formatWind(night.extremes.max_gust_kmh, units)}${night.extremes.max_gust_at ? ` at ${night.extremes.max_gust_at}` : ""}`}
        </ChecklistLine>
        <ChecklistLine state={night.requirements.dew ?? "not_counted"}>
          {rules.dew_counted ? `Temperature above dew point: minimum ${formatDewSpread(night.extremes.min_dew_spread_c, units)} — required ≥ ${formatDewSpread(rules.dew_min_spread_c, units)}` : `Dew limit off — minimum temperature above dew point: ${formatDewSpread(night.extremes.min_dew_spread_c, units)}`}
        </ChecklistLine>
        <ChecklistLine state={night.requirements.moon ?? "not_counted"}>
          Moon {Math.round(night.moon_illumination_pct)}% ({night.moon_phase_name}){night.moonset ? ` · sets ${night.moonset}` : ""}{rules.moon_must_be_down ? " — must be below the horizon" : " — not counted"}
        </ChecklistLine>
        {advisory && <ChecklistLine state="not_counted" mark="–">{advisory}</ChecklistLine>}
      </Box>

      <Box sx={{ overflowX: "auto", mt: 1 }}>
        <Box sx={{ minWidth: 940 }}>
          <Box sx={{ display: "grid", gridTemplateColumns: DETAIL_COLUMNS, gap: 1.5, color: "text.secondary", py: 0.5 }}>
            <span />
            <Box sx={{ display: "grid", gridTemplateColumns: `repeat(${Math.max(clock.length, 1)}, minmax(24px, 1fr))`, gap: "3px", minWidth: clock.length * 27 }}>
              {clock.map((column, index) => <Typography key={`${column.hour}-${index}`} variant="caption">{column.label}</Typography>)}
            </Box>
            <Typography variant="caption">Night summary</Typography>
          </Box>

          <GroupLabel>Counts toward your verdict</GroupLabel>
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
            Each forecast on its own: {coverageText(night)}
          </Typography>
          {cloudRows.map((model) => {
            const selected = selectedModels.has(model);
            const preferred = rules.cloud_preferred_model === model;
            return <GridRow
              key={model}
              dimmed={!selected}
              failurePattern="cloud"
              night={night}
              clock={clock}
              label={<Tooltip title={modelDescription(model) ?? ""} arrow placement="top-start" enterTouchDelay={0}><span>{`${modelName(model)}${preferred ? " (preferred)" : ""} total cloud %`}</span></Tooltip>}
              summary={selected
                ? MODEL_STATUS_LABELS[night.model_statuses[model] ?? night.coverage.find((entry) => entry.model === model)?.status ?? "not_used"]
                : "Not used for the cloud decision"}
              value={(hour) => cellNumber(hour.cloud_pct[model] ?? null, 0)}
              status={selected ? (hour) => judge(hour.dark_minutes > 0, hour.cloud_pct[model] ?? null, (value) => value > rules.cloud_max_pct) : undefined}
              notExpected={selected ? (hour) => hour.expected[model]?.cloud === false : undefined}
              tooltip={(hour) => model === "ecmwf_ifs025" && coarseHours.some((coarse) => coarse.start_utc === hour.start_utc)
                ? "Cloud data may be 6-hourly for this hour"
                : null}
            />;
          })}
          {night.default_cloud_used && <GridRow
            failurePattern="cloud"
            night={night}
            clock={clock}
            label={<Tooltip title={modelDescription("best_match") ?? ""} arrow placement="top-start" enterTouchDelay={0}><span>Open-Meteo default cloud %</span></Tooltip>}
            summary="Used where selected forecasts do not reach"
            value={(hour) => cellNumber(hour.cloud_pct.best_match ?? null, 0)}
            status={(hour) => judge(hour.dark_minutes > 0, hour.cloud_pct.best_match ?? null, (value) => value > rules.cloud_max_pct)}
            notExpected={(hour) => hour.expected.best_match?.cloud === false}
          />}
          {resolutionText && <Typography variant="caption" color="text.secondary" sx={{ display: "block", ml: `${WEATHER_DETAIL_LABEL_WIDTH + 12}px`, mb: 0.5 }}>{resolutionText}</Typography>}
          <ChanceRow night={night} clock={clock} rules={rules} />
          <GridRow
            night={night}
            clock={clock}
            label={`Precipitation amount ${units === "imperial" ? "in" : "mm"}`}
            summary={`${formatTotal(night.extremes, units)} · ${amountRuleText(rules.rain_amount_threshold_mm, units)}`}
            value={(hour) => precipitationCell(hour.precip_mm, units)}
            status={(hour) => judge(rainCounts(hour), hour.precip_mm, (value) => value > rules.rain_amount_threshold_mm)}
          />
          {rules.rain_forecasts === "any_model" && ["ecmwf_ifs025", "gfs_seamless", "icon_seamless"].map((model) => <GridRow
            key={`${model}-precipitation`}
            night={night}
            clock={clock}
            label={`${modelName(model)} precipitation amount ${units === "imperial" ? "in" : "mm"}`}
            summary={amountRuleText(rules.rain_amount_threshold_mm, units)}
            value={(hour) => precipitationCell(hour.model_precip_mm[model] ?? null, units)}
            status={(hour) => judge(rainCounts(hour), hour.model_precip_mm[model] ?? null, (value) => value > rules.rain_amount_threshold_mm)}
            notExpected={(hour) => hour.expected[model]?.amount === false}
          />)}
          <Box sx={{ display: "grid", gridTemplateColumns: DETAIL_COLUMNS, gap: 1.5, alignItems: "center", py: "3px" }}>
            <Typography variant="body2">Darkness</Typography>
            <DarknessBand night={night} clock={clock} height={26} />
            <Typography variant="caption" color="text.secondary">{`you use ${rules.darkness}`}</Typography>
          </Box>
          {rules.wind_counted && <>
            <GridRow night={night} clock={clock} label={`Wind ${units === "imperial" ? "mph" : "km/h"}`} summary={`limit ≤ ${formatWind(rules.wind_max_kmh, units)}`} value={(hour) => windCell(hour.wind_kmh, units)} status={(hour) => judge(hour.dark_minutes > 0, hour.wind_kmh, (value) => value > rules.wind_max_kmh)} />
            <GridRow night={night} clock={clock} label={`Gusts ${units === "imperial" ? "mph" : "km/h"}`} summary={`max ${formatWind(night.extremes.max_gust_kmh, units)} · limit ≤ ${formatWind(rules.gust_max_kmh, units)}`} value={(hour) => windCell(hour.gust_kmh, units)} status={(hour) => judge(hour.dark_minutes > 0, hour.gust_kmh, (value) => value > rules.gust_max_kmh)} />
          </>}
          {rules.dew_counted && <GridRow night={night} clock={clock} label={`Temperature above dew point (${units === "imperial" ? "°F" : "°C"})`} summary={`minimum ${formatDewSpread(night.extremes.min_dew_spread_c, units)} · limit ≥ ${formatDewSpread(rules.dew_min_spread_c, units)}`} value={(hour) => spreadCell(hour.dew_spread_c, units)} status={(hour) => judge(hour.dark_minutes > 0, hour.dew_spread_c, (value) => value < rules.dew_min_spread_c)} />}
          {rules.moon_must_be_down && <GridRow night={night} clock={clock} label="Moon altitude °" summary="must be below 0°" value={(hour) => cellNumber(hour.moon_altitude_deg, 0)} status={(hour) => judge(hour.dark_minutes > 0, hour.moon_altitude_deg, (value) => value >= 0)} />}

          {(!rules.wind_counted || !rules.dew_counted || !rules.moon_must_be_down) && <GroupLabel>Not counted (your rules)</GroupLabel>}
          {!rules.wind_counted && <GridRow dimmed night={night} clock={clock} label={`Wind / gusts ${units === "imperial" ? "mph" : "km/h"}`} summary={`up to ${formatWind(night.extremes.max_gust_kmh, units)}`} value={(hour) => `${windCell(hour.wind_kmh, units)}/${windCell(hour.gust_kmh, units)}`} />}
          {!rules.dew_counted && <GridRow dimmed night={night} clock={clock} label={`Temperature above dew point (${units === "imperial" ? "°F" : "°C"})`} summary={`minimum ${formatDewSpread(night.extremes.min_dew_spread_c, units)}`} value={(hour) => spreadCell(hour.dew_spread_c, units)} />}
          {!rules.moon_must_be_down && <GridRow dimmed night={night} clock={clock} label="Moon altitude °" summary="context only" value={(hour) => cellNumber(hour.moon_altitude_deg, 0)} />}

          <GroupLabel>For information</GroupLabel>
          <GridRow night={night} clock={clock} label={layerLabel("Low", night.layer_model === "ecmwf_ifs025")} summary="layer" value={(hour) => cellNumber(hour.cloud_low_pct, 0)} />
          <GridRow night={night} clock={clock} label={layerLabel("Mid", night.layer_model === "ecmwf_ifs025")} summary="layer" value={(hour) => cellNumber(hour.cloud_mid_pct, 0)} />
          <GridRow night={night} clock={clock} label={layerLabel("High", night.layer_model === "ecmwf_ifs025")} summary="layer" value={(hour) => cellNumber(hour.cloud_high_pct, 0)} />
          <GridRow night={night} clock={clock} label={`Temperature ${units === "imperial" ? "°F" : "°C"}`} summary="context only" value={(hour) => temperatureCell(hour.temperature_c, units)} />
          <GridRow night={night} clock={clock} label={`Visibility ${units === "imperial" ? "mi" : "km"}`} summary="context only" value={(hour) => visibilityCell(hour.visibility_m, units)} />
          <GridRow night={night} clock={clock} label="Seeing (estimate)" summary="context only" value={(hour) => hour.seeing ?? DASH} />
          <GridRow night={night} clock={clock} label="Transparency (estimate)" summary="context only" value={transparencyCell} />
        </Box>
      </Box>
      {!multipleModels && <FormControlLabel
        sx={{ mt: 1 }}
        control={<Checkbox checked={showModels} onChange={(event) => setModelVisibility({ key: modelVisibilityKey, show: event.target.checked })} size="small" />}
        label="Show each model's cloud"
      />}
    </Paper>
  );
}
