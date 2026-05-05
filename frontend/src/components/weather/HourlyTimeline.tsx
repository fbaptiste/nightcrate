import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import * as d3 from "d3";
import { useEffect, useRef, useState } from "react";

import type { HourlyWeather, MoonPolylinePoint, TwilightTimes } from "../../api/weather";
import type { WeatherUnits } from "../../api/settings";
import { cToF, kmhToMph } from "../../lib/unitConversion";
import { scoreToBackground, scoreToTextColor } from "../../lib/weatherColors";

interface HourlyTimelineProps {
  hours: HourlyWeather[];
  sunset: string | null;
  sunrise: string | null;
  twilight: TwilightTimes;
  moonPolyline: MoonPolylinePoint[];
  timezone: string;
  moonIncluded: boolean;
  units: WeatherUnits;
}

/**
 * Extract hours and minutes from an ISO-like local time string (e.g. "2026-04-15T21:00").
 * Parses directly from the string — no Date object, no browser timezone dependency.
 */
function localTimeToMinutes(isoLocal: string): number {
  const timePart = isoLocal.includes("T") ? isoLocal.split("T")[1] : isoLocal;
  const [hh, mm] = timePart.split(":").map(Number);
  return hh * 60 + (mm || 0);
}

/**
 * Convert a UTC ISO string to minutes-of-day in a specific IANA timezone.
 * Uses Intl.DateTimeFormat to get the location-local hour and minute.
 */
function utcToLocalMinutes(isoUtc: string, timezone: string): number {
  const dt = new Date(isoUtc);
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: timezone,
    hour: "numeric",
    minute: "numeric",
    hour12: false,
  }).formatToParts(dt);
  let hh = 0, mm = 0;
  for (const p of parts) {
    if (p.type === "hour") hh = Number(p.value);
    if (p.type === "minute") mm = Number(p.value);
  }
  // Intl hour12:false returns 24 for midnight in some browsers — normalize
  if (hh === 24) hh = 0;
  return hh * 60 + mm;
}

const LABEL_WIDTH = 130;
const ROW_HEIGHT = 34;
const QUALITY_ROW_HEIGHT = 42;
const GROUP_GAP = 14;
const GROUP_HEADER_HEIGHT = 22;
const DARKNESS_BAR_HEIGHT = 30;
const COMPOSITE_HEIGHT = DARKNESS_BAR_HEIGHT;

// ── Darkness colors ─────────────────────────────────────────────────────────

const DARKNESS_COLORS: Record<string, string> = {
  daylight: "hsl(215, 15%, 60%)",
  civil_twilight: "hsl(215, 30%, 45%)",
  nautical_twilight: "hsl(215, 35%, 30%)",
  astronomical_twilight: "hsl(215, 40%, 18%)",
  night: "hsl(215, 45%, 8%)",
};

// ── Dew risk colors (colorblind-safe sequential blue) ─────────────────────

const DEW_RISK_COLORS: Record<string, string> = {
  low: "hsl(215, 20%, 75%)",
  moderate: "hsl(215, 35%, 55%)",
  high: "hsl(215, 50%, 38%)",
  critical: "hsl(215, 65%, 22%)",
};

function dewRiskTextColor(risk: string): string {
  return risk === "low" ? "#1a1c20" : "#e2e0dd";
}

function dewRiskLabel(risk: string): string {
  return risk.charAt(0).toUpperCase() + risk.slice(1);
}

// ── Score / color helpers ───────────────────────────────────────────────────

const scoreToCellColor = scoreToBackground;
const cellTextColor = scoreToTextColor;

function moonScore(altDeg: number | null): number {
  if (altDeg === null) return 100;
  if (altDeg <= 0) return 100;
  return Math.max(0, Math.round(100 - (altDeg / 90) * 100));
}

function cloudScore(pct: number): number {
  return Math.round(100 - pct);
}

function precipScore(mm: number | null): number {
  if (mm === null || mm <= 0) return 100;
  if (mm < 0.5) return 70;
  if (mm < 2) return 30;
  return 0;
}

// ── Row definitions ─────────────────────────────────────────────────────────

interface RowDef {
  label: string;
  key: string;
  scoreFromHour: (h: HourlyWeather) => number | null;
  textFromHour: (h: HourlyWeather) => string | null;
  type: "quality" | "score" | "neutral" | "dew_risk";
  height?: number;
  isDaylight?: boolean;
}

const QUALITY_ROW: RowDef = {
  label: "Imaging Quality",
  key: "imaging_quality",
  scoreFromHour: (h) => h.imaging_quality,
  textFromHour: (h) => String(Math.round(h.imaging_quality)),
  type: "quality",
  height: QUALITY_ROW_HEIGHT,
};

const QUALITY_FACTOR_ROWS: RowDef[] = [
  {
    label: "Sky Clarity",
    key: "sky_clarity",
    scoreFromHour: (h) => h.sky_clarity,
    textFromHour: (h) => String(Math.round(h.sky_clarity)),
    type: "score",
  },
  {
    label: "Transparency",
    key: "transparency_score",
    scoreFromHour: (h) => h.transparency_score,
    textFromHour: (h) => String(Math.round(h.transparency_score)),
    type: "score",
  },
  {
    label: "Seeing",
    key: "seeing_score",
    scoreFromHour: (h) => h.seeing_score,
    textFromHour: (h) => String(Math.round(h.seeing_score)),
    type: "score",
  },
  {
    label: "Moon Quality",
    key: "moon_score",
    scoreFromHour: (h) => h.moon_score,
    textFromHour: (h) => String(Math.round(h.moon_score)),
    type: "score",
  },
  {
    label: "Wind Calm",
    key: "wind_calm",
    scoreFromHour: (h) => h.wind_calm,
    textFromHour: (h) => String(Math.round(h.wind_calm)),
    type: "score",
  },
];

function buildDetailRows(units: WeatherUnits): RowDef[] {
  const isImperial = units === "imperial";
  return [
    {
      label: "Precip. %",
      key: "precipitation_probability",
      scoreFromHour: (h) => Math.round(100 - (h.precipitation_probability_pct ?? 0)),
      textFromHour: (h) => `${Math.round(h.precipitation_probability_pct ?? 0)}%`,
      type: "score",
    },
    {
      label: "Precip. mm",
      key: "precipitation_mm",
      scoreFromHour: (h) => precipScore(h.precipitation_mm),
      textFromHour: (h) => (h.precipitation_mm !== null ? h.precipitation_mm.toFixed(1) : "0.0"),
      type: "score",
    },
    {
      label: "Cloud (total)",
      key: "cloud_cover_pct",
      scoreFromHour: (h) => cloudScore(h.cloud_cover_pct),
      textFromHour: (h) => `${Math.round(h.cloud_cover_pct)}%`,
      type: "score",
    },
    {
      label: "Cloud (high)",
      key: "cloud_cover_high_pct",
      scoreFromHour: (h) => cloudScore(h.cloud_cover_high_pct),
      textFromHour: (h) => `${Math.round(h.cloud_cover_high_pct)}%`,
      type: "score",
    },
    {
      label: "Cloud (mid)",
      key: "cloud_cover_mid_pct",
      scoreFromHour: (h) => cloudScore(h.cloud_cover_mid_pct),
      textFromHour: (h) => `${Math.round(h.cloud_cover_mid_pct)}%`,
      type: "score",
    },
    {
      label: "Cloud (low)",
      key: "cloud_cover_low_pct",
      scoreFromHour: (h) => cloudScore(h.cloud_cover_low_pct),
      textFromHour: (h) => `${Math.round(h.cloud_cover_low_pct)}%`,
      type: "score",
    },
    {
      label: "PWV (mm)",
      key: "pwv_mm",
      scoreFromHour: () => null,
      textFromHour: (h) => (h.pwv_mm !== null ? h.pwv_mm.toFixed(1) : "—"),
      type: "neutral",
    },
    {
      label: "AOD",
      key: "aod",
      scoreFromHour: () => null,
      textFromHour: (h) => (h.aod !== null ? h.aod.toFixed(2) : "—"),
      type: "neutral",
    },
    {
      label: isImperial ? "Temp. (°F)" : "Temp. (°C)",
      key: "temperature_c",
      scoreFromHour: () => null,
      textFromHour: (h) => isImperial
        ? `${Math.round(cToF(h.temperature_c))}`
        : `${Math.round(h.temperature_c)}`,
      type: "neutral",
    },
    {
      label: isImperial ? "Temp. (°C)" : "Temp. (°F)",
      key: "temperature_alt",
      scoreFromHour: () => null,
      textFromHour: (h) => isImperial
        ? `${Math.round(h.temperature_c)}`
        : `${Math.round(cToF(h.temperature_c))}`,
      type: "neutral",
    },
    {
      label: isImperial ? "Dew Pt. (°F)" : "Dew Pt. (°C)",
      key: "dew_point_c",
      scoreFromHour: () => null,
      textFromHour: (h) => isImperial
        ? `${Math.round(cToF(h.dew_point_c))}`
        : `${Math.round(h.dew_point_c)}`,
      type: "neutral",
    },
    {
      label: isImperial ? "Dew Pt. (°C)" : "Dew Pt. (°F)",
      key: "dew_point_alt",
      scoreFromHour: () => null,
      textFromHour: (h) => isImperial
        ? `${Math.round(h.dew_point_c)}`
        : `${Math.round(cToF(h.dew_point_c))}`,
      type: "neutral",
    },
    {
      label: "Humidity",
      key: "humidity_pct",
      scoreFromHour: () => null,
      textFromHour: (h) => `${Math.round(h.humidity_pct)}%`,
      type: "neutral",
    },
    {
      label: isImperial ? "Wind (mph)" : "Wind (km/h)",
      key: "wind_speed_kmh",
      scoreFromHour: () => null,
      textFromHour: (h) => isImperial
        ? `${Math.round(kmhToMph(h.wind_speed_kmh))}`
        : `${Math.round(h.wind_speed_kmh)}`,
      type: "neutral",
    },
    {
      label: isImperial ? "Wind (km/h)" : "Wind (mph)",
      key: "wind_speed_alt",
      scoreFromHour: () => null,
      textFromHour: (h) => isImperial
        ? `${Math.round(h.wind_speed_kmh)}`
        : `${Math.round(kmhToMph(h.wind_speed_kmh))}`,
      type: "neutral",
    },
    {
      label: "Dew Risk",
      key: "dew_risk",
      scoreFromHour: () => null,
      textFromHour: (h) => dewRiskLabel(h.dew_risk),
      type: "dew_risk",
    },
    {
      label: "Moon %",
      key: "moon_illumination",
      scoreFromHour: () => null,
      textFromHour: (h) =>
        h.moon_illumination_pct !== null ? `${Math.round(h.moon_illumination_pct)}%` : "—",
      type: "neutral",
    },
    {
      label: "Moon Alt.",
      key: "moon_altitude_deg",
      scoreFromHour: (h) => moonScore(h.moon_altitude_deg),
      textFromHour: (h) =>
        h.moon_altitude_deg !== null ? `${Math.round(h.moon_altitude_deg)}°` : "—",
      type: "score",
    },
  ];
}

// ── Twilight time helpers ───────────────────────────────────────────────────

/** Parse HH:MM into fractional minutes from midnight, handling overnight wrap. */
function hhmmToMinutes(hhmm: string, windowStartMin: number): number {
  const [hh, mm] = hhmm.split(":").map(Number);
  let mins = hh * 60 + mm;
  // Handle overnight: if time is before the window start, it's the next day
  if (mins < windowStartMin - 12 * 60) {
    mins += 24 * 60;
  }
  return mins;
}

/** Convert fractional minutes to 0–1 position within a min/max range. */
function minutesToFraction(mins: number, minMins: number, maxMins: number): number {
  return Math.max(0, Math.min(1, (mins - minMins) / (maxMins - minMins)));
}

interface GradientStop {
  offset: number; // 0–1
  color: string;
}

function buildDarknessGradientStops(
  twilight: TwilightTimes,
  sunset: string | null,
  sunrise: string | null,
  windowStartMin: number,
  windowEndMin: number,
): GradientStop[] {
  const toFrac = (hhmm: string | null) => {
    if (hhmm === null) return null;
    return minutesToFraction(hhmmToMinutes(hhmm, windowStartMin), windowStartMin, windowEndMin);
  };

  // Build stops from available twilight boundaries
  const stops: GradientStop[] = [
    { offset: 0, color: DARKNESS_COLORS.daylight },
  ];

  const sunsetFrac = toFrac(sunset);
  if (sunsetFrac !== null) stops.push({ offset: sunsetFrac, color: DARKNESS_COLORS.daylight });

  const civilEndFrac = toFrac(twilight.civil_end);
  if (civilEndFrac !== null) stops.push({ offset: civilEndFrac, color: DARKNESS_COLORS.civil_twilight });

  const nauticalEndFrac = toFrac(twilight.nautical_end);
  if (nauticalEndFrac !== null) stops.push({ offset: nauticalEndFrac, color: DARKNESS_COLORS.nautical_twilight });

  const astroStartFrac = toFrac(twilight.astro_start);
  if (astroStartFrac !== null) stops.push({ offset: astroStartFrac, color: DARKNESS_COLORS.night });

  const astroEndFrac = toFrac(twilight.astro_end);
  if (astroEndFrac !== null) stops.push({ offset: astroEndFrac, color: DARKNESS_COLORS.night });

  const nauticalStartFrac = toFrac(twilight.nautical_start);
  if (nauticalStartFrac !== null) stops.push({ offset: nauticalStartFrac, color: DARKNESS_COLORS.nautical_twilight });

  const civilStartFrac = toFrac(twilight.civil_start);
  if (civilStartFrac !== null) stops.push({ offset: civilStartFrac, color: DARKNESS_COLORS.civil_twilight });

  const sunriseFrac = toFrac(sunrise);
  if (sunriseFrac !== null) stops.push({ offset: sunriseFrac, color: DARKNESS_COLORS.daylight });

  stops.push({ offset: 1, color: DARKNESS_COLORS.daylight });

  return stops;
}

/** Format minutes (possibly >1440 for overnight) as HH:MM. */
function minutesToHHMM(mins: number): string {
  const m = ((mins % 1440) + 1440) % 1440;
  const hh = String(Math.floor(m / 60)).padStart(2, "0");
  const mm = String(Math.round(m % 60)).padStart(2, "0");
  return `${hh}:${mm}`;
}

// ── Main component ──────────────────────────────────────────────────────────

export default function HourlyTimeline({
  hours,
  sunset,
  sunrise,
  twilight,
  moonPolyline,
  timezone,
  moonIncluded,
  units,
}: HourlyTimelineProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState(0);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    let timer: ReturnType<typeof setTimeout>;
    const observer = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width ?? 0;
      clearTimeout(timer);
      timer = setTimeout(() => setContainerWidth(w), 150);
    });
    observer.observe(el);
    return () => {
      clearTimeout(timer);
      observer.disconnect();
    };
  }, []);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || hours.length === 0 || containerWidth === 0) return;

    d3.select(container).selectAll("*").remove();

    const detailRows = buildDetailRows(units);

    const MARKER_RIGHT_PAD = 90;
    const cellWidth = Math.max(42, Math.min(56, (containerWidth - LABEL_WIDTH - MARKER_RIGHT_PAD) / hours.length));
    const gridWidth = cellWidth * hours.length;
    const totalWidth = LABEL_WIDTH + gridWidth + MARKER_RIGHT_PAD;

    // Shared time window — used by darkness bar, moon polyline, and all grid rows
    // Parse location-local time directly from the ISO string (no Date/browser TZ)
    const firstHourMin = localTimeToMinutes(hours[0].time);
    const windowStartMin = firstHourMin;
    const windowEndMin = firstHourMin + hours.length * 60;

    // Pre-calculate total height
    const MARKER_PAD = 75;
    const qualityH = QUALITY_ROW_HEIGHT;
    const separatorH = 2; // separator line below quality row
    const factorsH = QUALITY_FACTOR_ROWS.length * ROW_HEIGHT;
    const detailsH = detailRows.length * ROW_HEIGHT;
    const totalHeight =
      MARKER_PAD +
      COMPOSITE_HEIGHT + 4 +
      ROW_HEIGHT + // time axis
      qualityH + separatorH +
      GROUP_GAP + GROUP_HEADER_HEIGHT + factorsH +
      GROUP_GAP + GROUP_HEADER_HEIGHT + detailsH;

    const svg = d3
      .select(container)
      .append("svg")
      .attr("width", totalWidth)
      .attr("height", totalHeight)
      .style("display", "block");

    const g = svg.append("g").attr("transform", `translate(0, ${MARKER_PAD})`);

    // ── Helper: check if hour is daylight padding ──────────────────────
    function isDaylightHour(hour: HourlyWeather): boolean {
      return hour.darkness_category === "daylight";
    }

    // ── Helper: render a row of cells ─────────────────────────────────
    function renderRow(row: RowDef, y: number, h: number, grayDaylight: boolean = false, opacity: number = 1) {
      const rowG = opacity < 1 ? g.append("g").style("opacity", opacity) : g;
      const labelWeight = row.type === "quality" ? "600" : "400";
      const labelSize = row.type === "quality" ? "14px" : "12px";
      rowG.append("text")
        .attr("x", LABEL_WIDTH - 8)
        .attr("y", y + h / 2 + 1)
        .attr("text-anchor", "end")
        .attr("dominant-baseline", "middle")
        .attr("font-size", labelSize)
        .attr("font-weight", labelWeight)
        .attr("fill", row.type === "quality" ? "#d4993f" : "#a0a0a8")
        .attr("font-family", "sans-serif")
        .text(row.label);

      hours.forEach((hour, colIdx) => {
        const x = LABEL_WIDTH + colIdx * cellWidth;
        const daylight = isDaylightHour(hour);

        // Gray out daylight padding hours for score rows
        if (grayDaylight && daylight) {
          rowG.append("rect")
            .attr("x", x + 1).attr("y", y + 1)
            .attr("width", cellWidth - 2).attr("height", h - 2)
            .attr("rx", 2).attr("fill", "rgba(128, 128, 140, 0.12)");
          rowG.append("text")
            .attr("x", x + cellWidth / 2).attr("y", y + h / 2 + 1)
            .attr("text-anchor", "middle").attr("dominant-baseline", "middle")
            .attr("font-size", "12px").attr("fill", "rgba(128, 128, 140, 0.4)")
            .attr("font-family", "sans-serif").text("—");
          return;
        }

        if (row.type === "dew_risk") {
          const riskLevel = hour.dew_risk;
          const bgColor = DEW_RISK_COLORS[riskLevel] ?? DEW_RISK_COLORS.low;
          const txtColor = dewRiskTextColor(riskLevel);
          const text = row.textFromHour(hour) ?? "";
          rowG.append("rect")
            .attr("x", x + 1).attr("y", y + 1)
            .attr("width", cellWidth - 2).attr("height", h - 2)
            .attr("rx", 2).attr("fill", bgColor);
          rowG.append("text")
            .attr("x", x + cellWidth / 2).attr("y", y + h / 2 + 1)
            .attr("text-anchor", "middle").attr("dominant-baseline", "middle")
            .attr("font-size", "11px").attr("fill", txtColor)
            .attr("font-family", "sans-serif").text(text);
        } else if (row.type === "neutral") {
          const text = row.textFromHour(hour) ?? "";
          rowG.append("rect")
            .attr("x", x + 1).attr("y", y + 1)
            .attr("width", cellWidth - 2).attr("height", h - 2)
            .attr("rx", 2).attr("fill", "rgba(128, 128, 140, 0.15)");
          rowG.append("text")
            .attr("x", x + cellWidth / 2).attr("y", y + h / 2 + 1)
            .attr("text-anchor", "middle").attr("dominant-baseline", "middle")
            .attr("font-size", "12px").attr("fill", "#a0a0a8")
            .attr("font-family", "sans-serif").text(text);
        } else {
          const score = row.scoreFromHour(hour) ?? 0;
          const text = row.textFromHour(hour) ?? "";
          const fillColor = scoreToCellColor(score);
          const textColor = cellTextColor(score);
          const fontSize = row.type === "quality" ? "14px" : "12px";
          const fontWeight = row.type === "quality" ? "700" : "400";

          rowG.append("rect")
            .attr("x", x + 1).attr("y", y + 1)
            .attr("width", cellWidth - 2).attr("height", h - 2)
            .attr("rx", 2).attr("fill", fillColor);
          rowG.append("text")
            .attr("x", x + cellWidth / 2).attr("y", y + h / 2 + 1)
            .attr("text-anchor", "middle").attr("dominant-baseline", "middle")
            .attr("font-size", fontSize).attr("font-weight", fontWeight)
            .attr("fill", textColor).attr("font-family", "sans-serif")
            .text(text);
        }
      });
    }

    function renderGroupHeader(label: string, y: number) {
      g.append("text")
        .attr("x", 4)
        .attr("y", y + GROUP_HEADER_HEIGHT / 2 + 1)
        .attr("dominant-baseline", "middle")
        .attr("font-size", "12px")
        .attr("font-weight", "600")
        .attr("fill", "#8e8c88")
        .attr("font-family", "sans-serif")
        .text(label);
      g.append("line")
        .attr("x1", LABEL_WIDTH).attr("y1", y)
        .attr("x2", totalWidth).attr("y2", y)
        .attr("stroke", "rgba(128,128,128,0.25)").attr("stroke-width", 1);
    }

    let curY = 0;

    // ── Composite: Moon area + Darkness bar ───────────────────────────
    // Moon polyline is rendered inside the darkness bar itself.
    // Altitude 0° = bottom of bar, 90° = top of bar.
    const darknessBarY = curY;

    g.append("text")
      .attr("x", LABEL_WIDTH - 8)
      .attr("y", darknessBarY + DARKNESS_BAR_HEIGHT / 2 + 1)
      .attr("text-anchor", "end")
      .attr("dominant-baseline", "middle")
      .attr("font-size", "13px")
      .attr("fill", "#a0a0a8")
      .attr("font-family", "sans-serif")
      .text("Darkness");

    // Darkness gradient
    const gradId = "darkness-gradient";
    const defs = svg.append("defs");
    const grad = defs.append("linearGradient")
      .attr("id", gradId)
      .attr("x1", "0%").attr("y1", "0%")
      .attr("x2", "100%").attr("y2", "0%");

    const stops = buildDarknessGradientStops(twilight, sunset, sunrise, windowStartMin, windowEndMin);
    for (const s of stops) {
      grad.append("stop")
        .attr("offset", `${(s.offset * 100).toFixed(2)}%`)
        .attr("stop-color", s.color);
    }

    const clipId = "darkness-clip";
    defs.append("clipPath").attr("id", clipId)
      .append("rect")
      .attr("x", LABEL_WIDTH).attr("y", darknessBarY)
      .attr("width", gridWidth).attr("height", DARKNESS_BAR_HEIGHT)
      .attr("rx", 4);

    g.append("rect")
      .attr("x", LABEL_WIDTH)
      .attr("y", darknessBarY)
      .attr("width", gridWidth)
      .attr("height", DARKNESS_BAR_HEIGHT)
      .attr("fill", `url(#${gradId})`)
      .attr("clip-path", `url(#${clipId})`);

    g.append("rect")
      .attr("x", LABEL_WIDTH)
      .attr("y", darknessBarY)
      .attr("width", gridWidth)
      .attr("height", DARKNESS_BAR_HEIGHT)
      .attr("rx", 4)
      .attr("fill", "none")
      .attr("stroke", "rgba(128,128,128,0.2)")
      .attr("stroke-width", 1);

    // ── Moon altitude polyline ──────────────────────────────────────
    // Snapshot timezone for D3 closures (CLAUDE.md: JS closure pitfall)
    const capturedTimezone = timezone;
    if (moonPolyline.length > 0) {
      // Compute x position from UTC timestamp, converted to location-local time
      const polylineToX = (isoUtc: string): number => {
        const localMins = utcToLocalMinutes(isoUtc, capturedTimezone);
        let adjustedMins = localMins;
        if (adjustedMins < windowStartMin - 12 * 60) {
          adjustedMins += 24 * 60;
        }
        const frac = (adjustedMins - windowStartMin) / (windowEndMin - windowStartMin);
        return LABEL_WIDTH + frac * gridWidth;
      };

      // Scale to actual max altitude so the peak sits near the top of the bar
      const maxAlt = Math.max(...moonPolyline.map((p) => p.altitude_deg), 1);
      const horizonY = darknessBarY + DARKNESS_BAR_HEIGHT;
      const topPad = 2; // small pad so peak doesn't clip the bar edge
      const altToY = (alt: number): number => {
        const clampedAlt = Math.max(0, Math.min(maxAlt, alt));
        return horizonY - (clampedAlt / maxAlt) * (DARKNESS_BAR_HEIGHT - topPad);
      };

      // Build line segments, only drawing when altitude > 0 (above horizon)
      // Split polyline into segments above horizon
      const segments: Array<Array<{ x: number; y: number }>> = [];
      let currentSegment: Array<{ x: number; y: number }> = [];

      for (const point of moonPolyline) {
        const x = polylineToX(point.time_utc);
        if (x < LABEL_WIDTH || x > LABEL_WIDTH + gridWidth) continue;

        if (point.altitude_deg > 0) {
          currentSegment.push({ x, y: altToY(point.altitude_deg) });
        } else {
          if (currentSegment.length > 0) {
            // Add horizon crossing point
            currentSegment.push({ x, y: horizonY });
            segments.push(currentSegment);
            currentSegment = [];
          }
        }
      }
      if (currentSegment.length > 0) {
        segments.push(currentSegment);
      }

      // Draw each segment as a polyline
      const moonClipId = "moon-polyline-clip";
      defs.append("clipPath").attr("id", moonClipId)
        .append("rect")
        .attr("x", LABEL_WIDTH).attr("y", darknessBarY)
        .attr("width", gridWidth).attr("height", COMPOSITE_HEIGHT);

      for (const seg of segments) {
        if (seg.length < 2) continue;
        const lineGen = d3.line<{ x: number; y: number }>()
          .x((d) => d.x)
          .y((d) => d.y)
          .curve(d3.curveMonotoneX);

        g.append("path")
          .attr("d", lineGen(seg))
          .attr("fill", "none")
          .attr("stroke", "#d4993f")
          .attr("stroke-width", 2)
          .attr("stroke-opacity", 0.85)
          .attr("clip-path", `url(#${moonClipId})`);
      }
    }

    // ── Twilight marker lines with labels ───────────────────────────
    const toX = (hhmm: string) => {
      const mins = hhmmToMinutes(hhmm, windowStartMin);
      const frac = (mins - windowStartMin) / (windowEndMin - windowStartMin);
      return LABEL_WIDTH + frac * gridWidth;
    };

    const markerLineColor = "rgba(200, 200, 210, 0.4)";
    const markerTextColor = "#c4985a";

    interface Marker { label: string; time: string; side: "left" | "right"; tier: number }
    const uniqueMarkers: Marker[] = [];
    if (sunset) uniqueMarkers.push({ label: "Sunset", time: sunset, side: "left", tier: 3 });
    if (twilight.civil_end) uniqueMarkers.push({ label: "Civil Dark", time: twilight.civil_end, side: "left", tier: 2 });
    if (twilight.nautical_end) uniqueMarkers.push({ label: "Nautical Dark", time: twilight.nautical_end, side: "left", tier: 1 });
    if (twilight.astro_start) uniqueMarkers.push({ label: "Astro Dark", time: twilight.astro_start, side: "left", tier: 0 });
    if (twilight.astro_end) uniqueMarkers.push({ label: "Astro Dark", time: twilight.astro_end, side: "right", tier: 0 });
    if (twilight.nautical_start) uniqueMarkers.push({ label: "Nautical Dark", time: twilight.nautical_start, side: "right", tier: 1 });
    if (twilight.civil_start) uniqueMarkers.push({ label: "Civil Dark", time: twilight.civil_start, side: "right", tier: 2 });
    if (sunrise) uniqueMarkers.push({ label: "Sunrise", time: sunrise, side: "right", tier: 3 });

    const TIER_HEIGHT = 14;
    const LABEL_BAR_GAP = 8;
    const maxTier = uniqueMarkers.length > 0 ? Math.max(...uniqueMarkers.map((m) => m.tier)) : 0;
    const labelsTopOffset = (maxTier + 1) * TIER_HEIGHT + LABEL_BAR_GAP;

    // Draw vertical lines
    const markersByTime = new Map<string, Marker[]>();
    for (const m of uniqueMarkers) {
      const existing = markersByTime.get(m.time) ?? [];
      existing.push(m);
      markersByTime.set(m.time, existing);
    }
    for (const [time, group] of markersByTime) {
      const mx = toX(time);
      const minTier = Math.min(...group.map((m) => m.tier));
      const lineTop = darknessBarY - labelsTopOffset + minTier * TIER_HEIGHT;
      g.append("line")
        .attr("x1", mx).attr("x2", mx)
        .attr("y1", lineTop).attr("y2", darknessBarY + DARKNESS_BAR_HEIGHT)
        .attr("stroke", markerLineColor).attr("stroke-width", 1)
        .attr("stroke-dasharray", "2,2");
    }

    // Draw labels
    const markerTimeColor = "#d0ccc4";
    for (const m of uniqueMarkers) {
      const mx = toX(m.time);
      const labelY = darknessBarY - labelsTopOffset + m.tier * TIER_HEIGHT + TIER_HEIGHT - 3;
      const textX = m.side === "left" ? mx - 4 : mx + 4;
      const anchor = m.side === "left" ? "end" : "start";
      const text = g.append("text")
        .attr("x", textX)
        .attr("y", labelY)
        .attr("text-anchor", anchor)
        .attr("font-size", "11px")
        .attr("font-family", "sans-serif");
      text.append("tspan").attr("fill", markerTextColor).text(`${m.label} `);
      text.append("tspan").attr("fill", markerTimeColor).text(m.time);
    }

    // ── Hover interaction on composite (darkness bar + moon area) ────
    const compositeY = curY;

    const hoverOverlay = g.append("rect")
      .attr("x", LABEL_WIDTH).attr("y", compositeY)
      .attr("width", gridWidth).attr("height", COMPOSITE_HEIGHT)
      .attr("fill", "transparent")
      .style("cursor", "crosshair");

    const hoverVisuals = svg.append("g")
      .attr("transform", `translate(0, ${MARKER_PAD})`)
      .attr("pointer-events", "none");

    const hoverLine = hoverVisuals.append("line")
      .attr("y1", compositeY).attr("y2", compositeY + COMPOSITE_HEIGHT)
      .attr("stroke", "#ffffff").attr("stroke-width", 1.5)
      .style("opacity", 0);

    // Tooltip group
    const tooltipG = hoverVisuals.append("g").style("opacity", 0);
    const tooltipBg = tooltipG.append("rect")
      .attr("rx", 3).attr("fill", "rgba(0,0,0,0.75)");
    const tooltipTime = tooltipG.append("text")
      .attr("font-size", "12px").attr("font-weight", "600")
      .attr("fill", "#ffffff").attr("font-family", "sans-serif");
    const tooltipMoon = tooltipG.append("text")
      .attr("font-size", "11px").attr("fill", "#d4993f")
      .attr("font-family", "sans-serif");

    // Snapshot values for closure
    const capturedWindowStartMin = windowStartMin;
    const capturedWindowEndMin = windowEndMin;

    function handleHover(event: MouseEvent | TouchEvent) {
      const [mx] = d3.pointer(event, g.node());
      const frac = (mx - LABEL_WIDTH) / gridWidth;
      if (frac < 0 || frac > 1) return;

      const mins = capturedWindowStartMin + frac * (capturedWindowEndMin - capturedWindowStartMin);
      const timeStr = minutesToHHMM(mins);

      hoverLine.attr("x1", mx).attr("x2", mx).style("opacity", 1);

      let moonAltText = "";
      if (moonPolyline.length > 0) {
        let closestAlt: number | null = null;
        let closestDist = Infinity;
        for (const p of moonPolyline) {
          const pMins = utcToLocalMinutes(p.time_utc, capturedTimezone);
          let adjPMins = pMins;
          if (adjPMins < capturedWindowStartMin - 12 * 60) adjPMins += 24 * 60;
          const dist = Math.abs(adjPMins - mins);
          if (dist < closestDist) {
            closestDist = dist;
            closestAlt = p.altitude_deg;
          }
        }
        if (closestAlt !== null && closestAlt > 0) {
          moonAltText = `Moon: ${Math.round(closestAlt)}°`;
        }
      }

      tooltipTime.text(timeStr);
      tooltipMoon.text(moonAltText);

      const tooltipX = mx;
      const tooltipY = darknessBarY - 6;
      const timeWidth = 35;
      const moonWidth = moonAltText ? moonAltText.length * 6 : 0;
      const bgWidth = Math.max(timeWidth, moonWidth) + 12;
      const bgHeight = moonAltText ? 30 : 18;

      tooltipBg
        .attr("x", tooltipX - bgWidth / 2)
        .attr("y", tooltipY - bgHeight)
        .attr("width", bgWidth)
        .attr("height", bgHeight);
      tooltipTime
        .attr("x", tooltipX)
        .attr("y", tooltipY - bgHeight + 13)
        .attr("text-anchor", "middle");
      tooltipMoon
        .attr("x", tooltipX)
        .attr("y", tooltipY - bgHeight + 25)
        .attr("text-anchor", "middle");

      tooltipG.style("opacity", 1);
    }

    function hideHover() {
      hoverLine.style("opacity", 0);
      tooltipG.style("opacity", 0);
    }

    hoverOverlay
      .on("mousemove", handleHover)
      .on("mouseleave", hideHover)
      .on("touchstart", (event: TouchEvent) => { event.preventDefault(); handleHover(event); }, { passive: false })
      .on("touchmove", (event: TouchEvent) => { event.preventDefault(); handleHover(event); }, { passive: false })
      .on("touchend", hideHover);

    curY += COMPOSITE_HEIGHT + 4;

    // ── Time axis labels ──────────────────────────────────────────────
    hours.forEach((hour, colIdx) => {
      const mins = localTimeToMinutes(hour.time);
      const hh = Math.floor(mins / 60) % 24;
      const mm = mins % 60;
      if (mm === 0 && hh % 2 === 0) {
        const label = `${String(hh).padStart(2, "0")}:00`;
        g.append("text")
          .attr("x", LABEL_WIDTH + colIdx * cellWidth + 2)
          .attr("y", curY + ROW_HEIGHT / 2)
          .attr("text-anchor", "start").attr("dominant-baseline", "middle")
          .attr("font-size", "12px").attr("fill", "#a0a0a8")
          .attr("font-family", "sans-serif").text(label);
      }
    });
    curY += ROW_HEIGHT;

    // ── Quality row (prominent, with separator) ─────────────────────
    renderRow(QUALITY_ROW, curY, QUALITY_ROW_HEIGHT, true);
    curY += QUALITY_ROW_HEIGHT;

    // Separator line below Imaging Quality row
    g.append("line")
      .attr("x1", LABEL_WIDTH).attr("y1", curY)
      .attr("x2", LABEL_WIDTH + gridWidth).attr("y2", curY)
      .attr("stroke", "rgba(212, 153, 63, 0.3)").attr("stroke-width", 1.5);
    curY += 2;

    // ── Score Factors ───────────────────────────────────────────────
    curY += GROUP_GAP;
    renderGroupHeader("SCORE FACTORS", curY);
    curY += GROUP_HEADER_HEIGHT;
    for (const row of QUALITY_FACTOR_ROWS) {
      const rowOpacity = row.key === "moon_score" && !moonIncluded ? 0.35 : 1;
      renderRow(row, curY, ROW_HEIGHT, true, rowOpacity);
      curY += ROW_HEIGHT;
    }

    // ── Weather Details ─────────────────────────────────────────────
    curY += GROUP_GAP;
    renderGroupHeader("WEATHER & MOON DETAILS", curY);
    curY += GROUP_HEADER_HEIGHT;
    for (const row of detailRows) {
      renderRow(row, curY, ROW_HEIGHT, false);
      curY += ROW_HEIGHT;
    }

    svg.attr("height", MARKER_PAD + curY);
  }, [hours, containerWidth, twilight, sunset, sunrise, moonPolyline, timezone, moonIncluded, units]);

  if (hours.length === 0) {
    return (
      <Typography variant="body2" sx={{ color: "text.secondary", py: 2 }}>
        Select a day to see hourly details.
      </Typography>
    );
  }

  return (
    <Box ref={containerRef} sx={{ overflowX: "auto" }} />
  );
}
