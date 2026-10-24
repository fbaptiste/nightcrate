import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import type { Night } from "@/api/weather";
import type { WeatherUnits } from "@/api/settings";
import {
  formatHours,
  reasonLine,
  WEATHER_ROW_COLUMNS,
  WEATHER_ROW_TABLET_COLUMNS,
  GO_MARK,
  type ClockColumn,
} from "@/lib/weatherVerdict";
import CallSplitIcon from "@mui/icons-material/CallSplit";
import { weatherPalette } from "@/lib/weatherPalette";
import HourStrip, { CONDITION_ICONS, HourAxis, hourCellStyles, type ConditionKey, type HourCellKind } from "./HourStrip";
import VerdictPill from "./VerdictPill";

function dateLabel(date: string): { main: string; sub: string } {
  const parsed = new Date(`${date}T12:00:00Z`);
  return {
    main: new Intl.DateTimeFormat(undefined, { weekday: "short", timeZone: "UTC" }).format(parsed),
    sub: new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", timeZone: "UTC" }).format(parsed),
  };
}

export default function WeekList({
  nights,
  clock,
  selectedDate,
  onSelect,
  units,
  notCurrent = false,
}: {
  nights: Night[];
  clock: ClockColumn[];
  selectedDate: string | null;
  onSelect: (date: string) => void;
  units: WeatherUnits;
  notCurrent?: boolean;
}) {
  return (
    <>
      <Box sx={{ maxWidth: "100%", border: 1, borderColor: "divider", borderRadius: 2, bgcolor: "background.paper" }}>
        <Box sx={{ minWidth: 0, px: 1.5, py: 0.75, "@media (min-width: 1101px)": { minWidth: 1040 } }}>
          <Box sx={{ display: "grid", gridTemplateColumns: WEATHER_ROW_COLUMNS, gap: 1.5, px: 0.5, pb: 0.5, color: "text.secondary", "@media (max-width: 1100px)": { gridTemplateColumns: WEATHER_ROW_TABLET_COLUMNS } }}>
            <span />
            <span />
            <Box sx={{ minWidth: 0, overflowX: "auto" }}>
              <HourAxis clock={clock} />
            </Box>
            <Box component="span" sx={{ "@media (max-width: 1100px)": { display: "none" } }} />
          </Box>
          {nights.map((night) => {
            const label = dateLabel(night.date);
            const selected = night.date === selectedDate;
            const darkHours = night.hours.filter((hour) => hour.dark_minutes > 0);
            const coarseBoundary = night.cloud_coarse_from_utc ? Date.parse(night.cloud_coarse_from_utc) : Number.NaN;
            const coarseHours = darkHours.filter((hour) =>
              Number.isFinite(coarseBoundary) && Date.parse(hour.start_utc) >= coarseBoundary,
            );
            const resolutionText = coarseHours.length === 0
              ? null
              : coarseHours.length === darkHours.length
                ? "6-hourly cloud all night"
                : `6-hourly cloud from ~${night.cloud_coarse_from}`;
            const evaluation = [
              night.evaluated_from ? `from ${night.evaluated_from}` : null,
              night.controls.imaging_until && night.evaluated_end ? `until ${night.evaluated_end}` : null,
            ].filter(Boolean).join(" · ");
            return (
              <Box
                component="button"
                type="button"
                key={night.date}
                onClick={() => onSelect(night.date)}
                aria-pressed={selected}
                sx={{
                  appearance: "none",
                  width: "100%",
                  border: 0,
                  borderBottom: 1,
                  borderColor: "divider",
                  bgcolor: "transparent",
                  color: "text.primary",
                  font: "inherit",
                  textAlign: "left",
                  display: "grid",
                  gridTemplateColumns: WEATHER_ROW_COLUMNS,
                  alignItems: "center",
                  gap: 1.5,
                  px: 0.5,
                  py: 1,
                  cursor: "pointer",
                  outline: selected ? 2 : 0,
                  outlineColor: "primary.main",
                  outlineOffset: -2,
                  borderRadius: selected ? 1 : 0,
                  "&:hover": { bgcolor: "action.hover" },
                  "&:focus-visible": { outline: 2, outlineColor: "primary.main", outlineOffset: -2 },
                  "&:last-of-type": { borderBottom: 0 },
                  "@media (max-width: 1100px)": {
                    gridTemplateColumns: WEATHER_ROW_TABLET_COLUMNS,
                    alignItems: "start",
                  },
                }}
              >
                <Box>
                  <Typography fontWeight={600}>{label.main}</Typography>
                  <Typography variant="caption" color="text.secondary">{label.sub}</Typography>
                </Box>
                <VerdictPill verdict={night.verdict} notCurrent={notCurrent} />
                <Box sx={{ minWidth: 0, overflowX: "auto", "@media (max-width: 1100px)": { gridColumn: 3, gridRow: 1 } }}>
                  <HourStrip night={night} clock={clock} />
                </Box>
                <Box sx={{ minWidth: 0, "@media (max-width: 1100px)": { gridColumn: 3, gridRow: 2, mt: 0.5 } }}>
                  <Typography variant="body2" sx={{ lineHeight: 1.35 }}>{reasonLine(night, units)}</Typography>
                  {resolutionText && (
                    <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.25 }}>
                      {resolutionText}
                    </Typography>
                  )}
                  <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.25 }}>
                    {formatHours(night.clear_hours)} of {formatHours(night.dark_hours)} h usable
                    {night.window_start && night.window_end ? ` · ${night.window_start}–${night.window_end}` : ""}
                    {evaluation ? ` · ${evaluation}` : ""}
                    {` · ${night.moon_phase_name} ${Math.round(night.moon_illumination_pct)}%`}
                    {night.moonset ? ` · sets ${night.moonset}` : ""}
                  </Typography>
                </Box>
              </Box>
            );
          })}
        </Box>
      </Box>
      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 2, mt: 1.25, color: "text.secondary" }}>
        {([
          ["clear", "Usable"],
          ["limit", "Over a limit (icons show which)"],
          ["models", "Cloud forecasts disagree"],
          ["unknown", "Missing forecast data"],
          ["dim", "Twilight / elapsed / outside imaging times"],
        ] as [HourCellKind, string][]).map(([kind, label]) => (
          <Box key={label} sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
            <Box sx={(theme) => ({ ...hourCellStyles(kind, theme), width: 24, height: 16, display: "flex", alignItems: "center", justifyContent: "center" })}>
              {kind === "models" && <CallSplitIcon sx={(theme) => ({ fontSize: 12, color: weatherPalette(theme).neutralText })} />}
              {kind === "clear" && <Box component="span" sx={(theme) => ({ fontSize: 12, fontWeight: 700, lineHeight: 1, color: weatherPalette(theme).onClearCell })}>{GO_MARK}</Box>}
            </Box>
            <Typography variant="caption">{label}</Typography>
          </Box>
        ))}
        {(Object.keys(CONDITION_ICONS) as ConditionKey[]).map((key) => {
          const { Icon, label } = CONDITION_ICONS[key];
          return (
            <Box key={key} sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
              <Icon sx={(theme) => ({ fontSize: 15, color: weatherPalette(theme).iconLit })} />
              <Typography variant="caption">{label}</Typography>
            </Box>
          );
        })}
      </Box>
    </>
  );
}
