import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Typography from "@mui/material/Typography";
import type { WeatherUnits } from "@/api/settings";
import type { CloudModel, ImagingRules } from "@/api/weather";

const KMH_PER_MPH = 1.609344;
const MM_PER_INCH = 25.4;
const MODEL_NAMES: Record<CloudModel, string> = {
  ecmwf_ifs025: "ECMWF",
  gfs_seamless: "GFS",
  icon_seamless: "ICON",
};

function compact(value: number): string {
  return Number(value.toPrecision(6)).toString();
}

function windLimit(valueKmh: number, units: WeatherUnits): string {
  return units === "imperial"
    ? `${Math.round(valueKmh / KMH_PER_MPH)} mph`
    : `${valueKmh} km/h`;
}

function dewLimit(valueC: number, units: WeatherUnits): string {
  return units === "imperial"
    ? `${(Math.round(valueC * 18) / 10).toFixed(1)} °F`
    : `${valueC} °C`;
}

function rainAmountLimit(valueMm: number, units: WeatherUnits): string {
  return units === "imperial"
    ? `${compact(valueMm / MM_PER_INCH)} in/h`
    : `${compact(valueMm)} mm/h`;
}

function selectedModels(rules: ImagingRules): CloudModel[] {
  return [
    ...(rules.cloud_use_ecmwf ? ["ecmwf_ifs025" as const] : []),
    ...(rules.cloud_use_gfs ? ["gfs_seamless" as const] : []),
    ...(rules.cloud_use_icon ? ["icon_seamless" as const] : []),
  ];
}

function cloudForecasts(rules: ImagingRules): string {
  const selected = selectedModels(rules);
  if (selected.length === 1) return `${MODEL_NAMES[selected[0]]} only`;
  const combination = rules.cloud_combination === "majority"
    ? "Majority for each hour"
    : "Show Uncertain";
  return `${selected.map((model) => MODEL_NAMES[model]).join(", ")}; ${combination}; preferred ${MODEL_NAMES[rules.cloud_preferred_model]}`;
}

function SummaryItem({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Typography variant="body2" color="text.secondary">
      {label}: <Box component="span" sx={{ color: "text.primary" }}>{children}</Box>
    </Typography>
  );
}

export default function RulesBar({
  locationName,
  rules,
  units,
  onEdit,
  editing,
}: {
  locationName: string;
  rules: ImagingRules;
  units: WeatherUnits;
  onEdit: () => void;
  editing: boolean;
}) {
  const session = rules.session_style === "all_night"
    ? `All night; usable ≥ ${rules.min_clear_fraction_pct}% and ≥ ${rules.min_clear_hours} h; longest interruption ${rules.max_cloudy_gap_hours == null ? "no limit" : `≤ ${rules.max_cloudy_gap_hours} h`}`
    : `≥ ${rules.short_session_hours} h usable in a row`;
  const amount = rules.rain_amount_threshold_mm > 0
    ? `≤ ${rainAmountLimit(rules.rain_amount_threshold_mm, units)}`
    : "none allowed";
  return (
    <Box sx={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "6px 14px", border: 1, borderColor: "divider", borderRadius: 2, bgcolor: "background.paper", px: 1.5, py: 1, mb: 1.5 }}>
      <Typography variant="body2" fontWeight={600}>Your rules · {locationName}</Typography>
      <SummaryItem label="Session">{session}</SummaryItem>
      <SummaryItem label="Cloud">≤ {rules.cloud_max_pct}%</SummaryItem>
      <SummaryItem label="Cloud forecasts">{cloudForecasts(rules)}</SummaryItem>
      <SummaryItem label="Precipitation">chance ≤ {rules.rain_max_probability_pct}%; amount {amount}</SummaryItem>
      <SummaryItem label="Amount forecasts">{rules.rain_forecasts === "main" ? "Main forecast" : "Main + ECMWF, GFS and ICON"}</SummaryItem>
      <SummaryItem label="If exceeded">{rules.rain_policy === "night_off" ? "Whole night off" : "Affected hours lost"}</SummaryItem>
      {rules.rain_policy === "night_off" && <SummaryItem label="Gear defaults">{rules.gear_out_before_sunset_min} min before sunset to {rules.gear_out_after_sunrise_min} min after sunrise</SummaryItem>}
      <SummaryItem label="Wind">{rules.wind_counted ? `≤ ${windLimit(rules.wind_max_kmh, units)}; gusts ≤ ${windLimit(rules.gust_max_kmh, units)}` : "off"}</SummaryItem>
      <SummaryItem label="Dew">{rules.dew_counted ? `≥ ${dewLimit(rules.dew_min_spread_c, units)} above dew point` : "off"}</SummaryItem>
      <SummaryItem label="Moon">{rules.moon_must_be_down ? "Must be below horizon" : "off"}</SummaryItem>
      <SummaryItem label="Darkness">{rules.darkness[0].toUpperCase() + rules.darkness.slice(1)}</SummaryItem>
      {!editing && <Button size="small" variant="outlined" onClick={onEdit} sx={{ ml: "auto" }}>Edit rules</Button>}
    </Box>
  );
}
