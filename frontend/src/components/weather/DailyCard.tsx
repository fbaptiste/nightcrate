import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import CardActionArea from "@mui/material/CardActionArea";
import CardContent from "@mui/material/CardContent";
import Divider from "@mui/material/Divider";
import Typography from "@mui/material/Typography";
import ThermostatIcon from "@mui/icons-material/Thermostat";
import WaterDropIcon from "@mui/icons-material/WaterDrop";

import type { DailySummary } from "../../api/weather";
import type { WeatherUnits } from "../../api/settings";
import { cToF } from "../../lib/unitConversion";
import MoonPhaseIcon from "./MoonPhaseIcon";
import QualityBadge from "./QualityBadge";

interface DailyCardProps {
  day: DailySummary;
  selected: boolean;
  moonIncluded: boolean;
  units: WeatherUnits;
  onClick: () => void;
}

// ── Sub-score bar ──────────────────────────────────────────────────────────

interface ScoreBarProps {
  label: string;
  value: number;
  grayed?: boolean;
}

function ScoreBar({ label, value, grayed = false }: ScoreBarProps) {
  const barWidth = `${Math.max(0, Math.min(100, value))}%`;
  const opacity = grayed ? 0.35 : 1;

  return (
    <Box sx={{ mb: 1.5, opacity }}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <Typography
          variant="caption"
          sx={{ fontSize: "0.65rem", color: "text.secondary", lineHeight: 1.3 }}
        >
          {label}
        </Typography>
        <Typography
          variant="caption"
          sx={{ fontSize: "0.6rem", color: "text.secondary", lineHeight: 1.3, ml: 0.5 }}
        >
          {Math.round(value)}
        </Typography>
      </Box>
      <Box sx={{ ml: 1, mt: 0.25 }}>
        <Box
          sx={{
            width: "100%",
            height: 4,
            borderRadius: 2,
            bgcolor: "action.hover",
          }}
        >
          <Box
            sx={{
              width: barWidth,
              height: "100%",
              borderRadius: 2,
              bgcolor: grayed ? "text.disabled" : "#d4993f",
              transition: "width 0.3s ease",
            }}
          />
        </Box>
      </Box>
    </Box>
  );
}

// ── Dew-safe formatter ─────────────────────────────────────────────────────

function formatDewSafe(dew: DailySummary["dew_safe_window"]): string {
  switch (dew.label) {
    case "all_night":
      return "Dew-safe: all night";
    case "until":
      return `Dew-safe: until ${dew.until_time}`;
    case "after":
      return `Dew-safe: after ${dew.after_time}`;
    default:
      return "Dew risk: all night";
  }
}

// ── Temperature formatters ─────────────────────────────────────────────────

function formatTempLine1(minC: number, maxC: number, units: WeatherUnits): string {
  if (units === "imperial") {
    return `${Math.round(cToF(minC))}\u2013${Math.round(cToF(maxC))}\u00b0F`;
  }
  return `${Math.round(minC)}\u2013${Math.round(maxC)}\u00b0C`;
}

function formatTempLine2(minC: number, maxC: number, units: WeatherUnits): string {
  if (units === "imperial") {
    return `${Math.round(minC)}\u2013${Math.round(maxC)}\u00b0C`;
  }
  return `${Math.round(cToF(minC))}\u2013${Math.round(cToF(maxC))}\u00b0F`;
}

// ── Main component ─────────────────────────────────────────────────────────

export default function DailyCard({ day, selected, moonIncluded, units, onClick }: DailyCardProps) {
  // Parse date with T12:00:00 to avoid timezone shift
  const dateObj = new Date(`${day.date}T12:00:00`);
  const dayName = dateObj.toLocaleDateString("en-US", { weekday: "short" });
  const monthDay = dateObj.toLocaleDateString("en-US", { month: "short", day: "numeric" });

  const infoTextSx = { fontSize: "0.65rem", color: "text.secondary", lineHeight: 1.6 };
  const precipPct = Math.round(day.max_precipitation_probability_pct);

  return (
    <Card
      sx={{
        minWidth: 150,
        maxWidth: 170,
        elevation: selected ? 4 : 1,
        border: selected ? 2 : 1,
        borderColor: selected ? "primary.main" : "divider",
        flexShrink: 0,
      }}
      elevation={selected ? 4 : 1}
    >
      <CardActionArea onClick={onClick} sx={{ height: "100%" }}>
        <CardContent sx={{ p: 1.25, "&:last-child": { pb: 1.25 } }}>
          {/* Date header */}
          <Box sx={{ textAlign: "center", mb: 1 }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 700, lineHeight: 1.2 }}>
              {dayName}
            </Typography>
            <Typography variant="caption" sx={{ color: "text.secondary", fontSize: "0.7rem" }}>
              {monthDay}
            </Typography>
          </Box>

          {/* Main quality badge */}
          <Box sx={{ display: "flex", justifyContent: "center", mb: 0.75 }}>
            {day.no_imaging_window ? (
              <Typography
                variant="body2"
                sx={{ color: "text.secondary", textAlign: "center", fontSize: "0.8rem" }}
              >
                —
              </Typography>
            ) : (
              <QualityBadge
                score={day.imaging_quality}
                label={day.imaging_quality_label}
                size="large"
                showLabel
              />
            )}
          </Box>

          {/* Temp & Precip row — between badge and sub-scores */}
          {!day.no_imaging_window && (
            <Box
              sx={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                px: 0.25,
                mb: 0.5,
              }}
            >
              {/* Temperature */}
              <Box sx={{ display: "flex", alignItems: "center", gap: 0.25 }}>
                <ThermostatIcon sx={{ fontSize: 14, color: "#d4993f" }} />
                <Box>
                  <Typography sx={{ fontSize: "0.6rem", color: "text.primary", lineHeight: 1.3, fontWeight: 500 }}>
                    {formatTempLine1(day.temp_min_c, day.temp_max_c, units)}
                  </Typography>
                  <Typography sx={{ fontSize: "0.6rem", color: "text.primary", lineHeight: 1.3, fontWeight: 500 }}>
                    {formatTempLine2(day.temp_min_c, day.temp_max_c, units)}
                  </Typography>
                </Box>
              </Box>

              {/* Precipitation */}
              <Box sx={{ display: "flex", alignItems: "center", gap: 0.25 }}>
                <WaterDropIcon
                  sx={{
                    fontSize: 14,
                    color: precipPct > 50 ? "#3a8fd4" : precipPct > 20 ? "#5b9bd5" : precipPct > 0 ? "#7cb8d9" : "#9ac4de",
                  }}
                />
                <Typography
                  sx={{
                    fontSize: "0.65rem",
                    lineHeight: 1.3,
                    fontWeight: 500,
                    color: precipPct > 30 ? "#5b9bd5" : "text.primary",
                  }}
                >
                  {precipPct}%
                </Typography>
              </Box>
            </Box>
          )}

          <Divider sx={{ my: 0.75 }} />

          {/* Sub-score bars */}
          {day.no_imaging_window ? (
            <Typography
              variant="caption"
              display="block"
              sx={{ ...infoTextSx, textAlign: "center", py: 1 }}
            >
              No imaging window tonight
            </Typography>
          ) : (
            <Box sx={{ px: 0.25 }}>
              <ScoreBar label="Sky Clarity" value={day.sky_clarity} />
              <ScoreBar label="Transparency" value={day.transparency_score} />
              <ScoreBar label="Seeing" value={day.seeing_score} />
              <ScoreBar label="Moon Quality" value={day.moon_score} grayed={!moonIncluded} />
              <ScoreBar label="Wind Calm" value={day.wind_calm} />
            </Box>
          )}

          <Divider sx={{ my: 0.75 }} />

          {/* Moon info */}
          <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, mb: 0.25 }}>
            <MoonPhaseIcon
              phaseName={day.moon_phase_name}
              illuminationPct={day.moon_illumination_pct}
              sx={{ fontSize: 18 }}
            />
            <Typography variant="caption" sx={{ fontSize: "0.7rem", color: "text.secondary" }}>
              {Math.round(day.moon_illumination_pct)}%
            </Typography>
          </Box>

          {/* Phase name */}
          <Typography variant="caption" display="block" sx={infoTextSx}>
            {day.moon_phase_name}
          </Typography>

          {/* Darkness details */}
          <Typography variant="caption" display="block" sx={infoTextSx}>
            Moonless: {day.moonless_dark_hours.toFixed(1)}h
          </Typography>
          <Typography variant="caption" display="block" sx={infoTextSx}>
            Dark: {day.darkness_hours.toFixed(1)}h
          </Typography>
          <Typography variant="caption" display="block" sx={infoTextSx}>
            Sun: {day.sunset ?? "\u2014"} / {day.sunrise ?? "\u2014"}
          </Typography>
          <Typography variant="caption" display="block" sx={infoTextSx}>
            {day.deepest_darkness_reached === "astro"
              ? `Astro: ${day.astro_dark_start ?? "\u2014"} / ${day.astro_dark_end ?? "\u2014"}`
              : day.deepest_darkness_reached === "nautical"
                ? "Nautical: yes"
                : "Astro: \u2014"}
          </Typography>
          <Typography variant="caption" display="block" sx={infoTextSx}>
            {formatDewSafe(day.dew_safe_window)}
          </Typography>
        </CardContent>
      </CardActionArea>
    </Card>
  );
}
