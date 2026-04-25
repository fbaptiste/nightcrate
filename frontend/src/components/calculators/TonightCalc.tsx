import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Grid from "@mui/material/Grid";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { fetchTonight, type TonightResponse } from "@/api/calculators";
import { fetchForecast, type ForecastResponse } from "@/api/weather";
import CalculatorAboutSection from "@/components/rigs/CalculatorAboutSection";
import { useCalculatorLocation } from "@/components/calculators/CalculatorLocationBar";
import MoonPhaseIcon from "@/components/weather/MoonPhaseIcon";
import QualityBadge from "@/components/weather/QualityBadge";

const DASH = "—";

/** Concise descriptions of each lunar phase for the moon-phase tooltip.
 *  Keyed lowercase so backend casing variations match. */
const MOON_PHASE_DESCRIPTIONS: Record<string, string> = {
  "new moon":
    "The Moon sits roughly between Earth and the Sun, so its lit side faces away from us — the Moon is not visible.",
  "waxing crescent":
    "Less than half lit and growing — a thin sliver on the right (Northern Hemisphere) heading toward first quarter.",
  "first quarter":
    "Half-lit on the right — the Moon has completed a quarter of its orbit since new moon.",
  "waxing gibbous":
    "More than half lit and growing — between first quarter and full.",
  "full moon":
    "Fully illuminated — Earth sits roughly between the Moon and the Sun.",
  "waning gibbous":
    "More than half lit and shrinking — between full and last quarter.",
  "last quarter":
    "Half-lit on the left — the Moon has completed three-quarters of its orbit since new moon.",
  "third quarter":
    "Half-lit on the left — the Moon has completed three-quarters of its orbit since new moon.",
  "waning crescent":
    "Less than half lit and shrinking — a thin sliver on the left fading toward new moon.",
};

function moonPhaseDescription(name: string | null | undefined): string {
  if (!name) return "";
  return (
    MOON_PHASE_DESCRIPTIONS[name.toLowerCase()] ??
    "Phase of the Moon as seen from Earth — describes how much of the lit hemisphere is currently visible."
  );
}

/** Today's date (YYYY-MM-DD) in the given IANA timezone. */
function todayInTimezone(timezone: string): string {
  try {
    const parts = new Intl.DateTimeFormat("en-CA", {
      timeZone: timezone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).formatToParts(new Date());
    const y = parts.find((p) => p.type === "year")?.value ?? "";
    const m = parts.find((p) => p.type === "month")?.value ?? "";
    const d = parts.find((p) => p.type === "day")?.value ?? "";
    if (y && m && d) return `${y}-${m}-${d}`;
  } catch {
    // fall through
  }
  const now = new Date();
  const pad = (n: number) => (n < 10 ? `0${n}` : String(n));
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

/** Hours (float) → "Nh MM m" rounded to the nearest minute. */
function formatDurationHours(hours: number | null | undefined): string {
  if (hours == null || !isFinite(hours) || hours <= 0) return `0h 0m`;
  const totalMin = Math.round(hours * 60);
  const h = Math.floor(totalMin / 60);
  const m = totalMin - h * 60;
  return `${h}h ${m}m`;
}

/**
 * "Tonight at a glance" — darkness totals, twilight/sunrise transitions,
 * imaging quality, and moon info for the selected location and date.
 */
export default function TonightCalc() {
  const { locationId, location } = useCalculatorLocation();
  const timezone =
    location?.timezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone;
  const [date, setDate] = useState(() => todayInTimezone(timezone));

  // Re-seed the date whenever the location's display timezone changes, so we
  // land on "today" in *that* location by default.
  useEffect(() => {
    setDate(todayInTimezone(timezone));
  }, [timezone]);

  const { data, isLoading, error } = useQuery<TonightResponse>({
    queryKey: ["calc-tonight", locationId, date],
    queryFn: () => fetchTonight(locationId!, date),
    enabled: locationId != null && Boolean(date),
  });

  // Imaging-quality forecast (independent fetch — the weather API runs the
  // full scoring pipeline; we just pluck the matching day's score).
  const { data: forecast } = useQuery<ForecastResponse>({
    queryKey: ["calc-tonight-forecast", locationId],
    queryFn: () => fetchForecast(locationId!, true),
    enabled: locationId != null,
  });

  const tonightForecast = useMemo(
    () => forecast?.days.find((d) => d.date === date),
    [forecast, date],
  );

  const tz = data?.timezone ?? timezone;

  const headlines = useMemo(() => {
    if (!data) {
      return {
        astronomical: DASH,
        moonless: DASH,
      };
    }
    return {
      astronomical: formatDurationHours(data.astronomical_dark_hours),
      moonless: formatDurationHours(data.moonless_dark_hours),
    };
  }, [data]);

  if (locationId == null) {
    return (
      <Typography color="text.secondary">
        Select a location above to see tonight at a glance.
      </Typography>
    );
  }

  return (
    <Stack spacing={3}>
      <Typography variant="h5">Tonight at a Glance</Typography>

      <Stack direction="row" spacing={2} alignItems="center">
        <TextField
          label="Date"
          type="date"
          size="small"
          value={date}
          onChange={(e) => setDate(e.target.value)}
          slotProps={{ inputLabel: { shrink: true } }}
        />
        {location && (
          <Typography variant="body2" color="text.secondary">
            {location.name} &middot; {tz}
          </Typography>
        )}
      </Stack>

      {/* Headline durations — already a 2-col responsive grid. */}
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 6 }}>
          <Paper variant="outlined" sx={{ p: 2.5 }}>
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ textTransform: "uppercase", letterSpacing: 0.5 }}
            >
              Astronomical dark
            </Typography>
            <Typography
              variant="h4"
              sx={{ fontFamily: "monospace", mt: 0.5 }}
            >
              {headlines.astronomical}
            </Typography>
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ display: "block", mt: 0.5 }}
            >
              Sun &gt; 18&deg; below the horizon
            </Typography>
          </Paper>
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <Paper variant="outlined" sx={{ p: 2.5 }}>
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ textTransform: "uppercase", letterSpacing: 0.5 }}
            >
              Dark with moon down
            </Typography>
            <Typography
              variant="h4"
              sx={{ fontFamily: "monospace", mt: 0.5 }}
            >
              {headlines.moonless}
            </Typography>
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ display: "block", mt: 0.5 }}
            >
              Astronomical dark with the moon also below the horizon
            </Typography>
          </Paper>
        </Grid>
      </Grid>

      {/* Detail panels — Evening, Morning, Moon, Imaging quality, all
          half-width on md+, stacked on small screens. */}
      <Grid container spacing={2}>
        {/* Evening transitions */}
        <Grid size={{ xs: 12, md: 6 }}>
          <Paper variant="outlined" sx={{ p: 2.5, height: "100%" }}>
            <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 2 }}>
              Evening
            </Typography>
            <Grid container spacing={2}>
              <TransitionCell label="Sunset" time={data?.sunset ?? DASH} />
              <TransitionCell
                label="Civil twilight end"
                time={data?.civil_twilight_end ?? DASH}
              />
              <TransitionCell
                label="Nautical twilight end"
                time={data?.nautical_twilight_end ?? DASH}
              />
              <TransitionCell
                label="Astronomical twilight end"
                time={data?.astronomical_twilight_end ?? DASH}
              />
            </Grid>
          </Paper>
        </Grid>

        {/* Morning transitions */}
        <Grid size={{ xs: 12, md: 6 }}>
          <Paper variant="outlined" sx={{ p: 2.5, height: "100%" }}>
            <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 2 }}>
              Morning
            </Typography>
            <Grid container spacing={2}>
              <TransitionCell
                label="Astronomical twilight start"
                time={data?.astronomical_twilight_start ?? DASH}
              />
              <TransitionCell
                label="Nautical twilight start"
                time={data?.nautical_twilight_start ?? DASH}
              />
              <TransitionCell
                label="Civil twilight start"
                time={data?.civil_twilight_start ?? DASH}
              />
              <TransitionCell label="Sunrise" time={data?.sunrise ?? DASH} />
            </Grid>
          </Paper>
        </Grid>

        {/* Moon */}
        <Grid size={{ xs: 12, md: 6 }}>
          <Paper variant="outlined" sx={{ p: 2.5, height: "100%" }}>
            <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 2 }}>
              Moon
            </Typography>
            <Stack
              direction={{ xs: "column", sm: "row" }}
              spacing={3}
              alignItems={{ xs: "flex-start", sm: "center" }}
            >
              <Stack direction="row" spacing={2} alignItems="center">
                <MoonPhaseIcon
                  phaseName={data?.moon_phase_name ?? "new"}
                  illuminationPct={data?.moon_illumination_pct ?? 0}
                  sx={{ fontSize: 56 }}
                />
                <Box>
                  <Typography
                    variant="h6"
                    sx={{ fontFamily: "monospace", lineHeight: 1.2 }}
                  >
                    {data ? `${Math.round(data.moon_illumination_pct)}%` : DASH}
                  </Typography>
                  <Tooltip
                    title={moonPhaseDescription(data?.moon_phase_name)}
                    placement="bottom-start"
                    arrow
                  >
                    <Typography
                      variant="body2"
                      color="text.secondary"
                      sx={{ cursor: "help", display: "inline-block" }}
                    >
                      {data?.moon_phase_name ?? DASH}
                    </Typography>
                  </Tooltip>
                </Box>
              </Stack>

              <Box sx={{ display: "flex", gap: 4 }}>
                <Box>
                  <Typography variant="caption" color="text.secondary">
                    Moonrise
                  </Typography>
                  <Typography variant="h6" sx={{ fontFamily: "monospace" }}>
                    {data?.moonrise ?? DASH}
                  </Typography>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">
                    Moonset
                  </Typography>
                  <Typography variant="h6" sx={{ fontFamily: "monospace" }}>
                    {data?.moonset ?? DASH}
                  </Typography>
                </Box>
              </Box>
            </Stack>
          </Paper>
        </Grid>

        {/* Imaging quality (forecast-derived) */}
        <Grid size={{ xs: 12, md: 6 }}>
          <Paper variant="outlined" sx={{ p: 2.5, height: "100%" }}>
            <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 2 }}>
              Imaging quality
            </Typography>
            {tonightForecast ? (
              tonightForecast.no_imaging_window ? (
                <Typography variant="body2" color="text.secondary">
                  No imaging window for this date.
                </Typography>
              ) : (
                <Stack direction="row" spacing={3} alignItems="center">
                  <QualityBadge
                    score={tonightForecast.imaging_quality}
                    label={tonightForecast.imaging_quality_label}
                    size="large"
                    showLabel
                  />
                  <Typography variant="body2" color="text.secondary">
                    Composite of sky clarity, transparency, seeing, moon, and
                    wind for {tonightForecast.date} at {location?.name ?? "this location"}.
                  </Typography>
                </Stack>
              )
            ) : forecast ? (
              <Typography variant="body2" color="text.secondary">
                No forecast data for this date — outside the 7-day window.
              </Typography>
            ) : (
              <Typography variant="body2" color="text.secondary">
                Loading forecast&hellip;
              </Typography>
            )}
          </Paper>
        </Grid>
      </Grid>

      {isLoading && (
        <Typography variant="body2" color="text.secondary">
          Loading&hellip;
        </Typography>
      )}
      {error && (
        <Typography variant="body2" color="warning.main">
          {error instanceof Error ? error.message : "Failed to load tonight data"}
        </Typography>
      )}

      <CalculatorAboutSection>
        <p>
          Sunset/sunrise, twilight, moonrise, and moonset events are computed by{" "}
          <code>astropy</code> with atmospheric refraction disabled, then
          rendered in the selected location&rsquo;s timezone.
        </p>
        <p>
          <strong>Astronomical dark</strong> = total time the sun is more than
          18&deg; below the horizon during the 24-hour window.
        </p>
        <p>
          <strong>Moonless dark</strong> = astronomical dark with the moon
          additionally below the horizon &mdash; a good proxy for narrowband
          imaging time when moon illumination is high.
        </p>
        <p>
          <strong>Imaging quality</strong> reuses the same composite score the
          Weather page reports for this date &mdash; sky clarity (cloud
          layers), transparency, seeing, moon, and wind blended into a single
          0&ndash;100 number with the same colour palette.
        </p>
        <p>
          At polar latitudes any individual event (e.g. sunset) may be{" "}
          <code>null</code> if it doesn&rsquo;t occur on this date; the headline
          durations still reflect the actual amount of darkness in the window.
        </p>
      </CalculatorAboutSection>
    </Stack>
  );
}

function TransitionCell({ label, time }: { label: string; time: string }) {
  return (
    <Grid size={{ xs: 6, sm: 3 }}>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      <Typography
        variant="h6"
        sx={{ fontFamily: "monospace", lineHeight: 1.2 }}
      >
        {time}
      </Typography>
    </Grid>
  );
}
