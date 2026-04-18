import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Grid from "@mui/material/Grid";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { fetchTonight, type TonightResponse } from "@/api/calculators";
import CalculatorAboutSection from "@/components/rigs/CalculatorAboutSection";
import { useCalculatorLocation } from "@/components/calculators/CalculatorLocationBar";
import MoonPhaseIcon from "@/components/weather/MoonPhaseIcon";

const DASH = "\u2014";

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

/** Render a UTC ISO timestamp as HH:MM in the given IANA timezone. */
function formatClockInTz(isoUtc: string | null, timezone: string): string {
  if (!isoUtc) return DASH;
  try {
    const dt = new Date(isoUtc);
    if (isNaN(dt.getTime())) return DASH;
    return new Intl.DateTimeFormat("en-GB", {
      timeZone: timezone,
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(dt);
  } catch {
    return DASH;
  }
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
 * "Tonight at a glance" — darkness totals, twilight/sunrise transitions, and
 * moon info for the selected location and date.
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

      {/* Headline durations */}
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

      {/* Evening transitions */}
      <Paper variant="outlined" sx={{ p: 2.5 }}>
        <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 2 }}>
          Evening
        </Typography>
        <Grid container spacing={2}>
          <TransitionCell
            label="Sunset"
            time={formatClockInTz(data?.sunset ?? null, tz)}
          />
          <TransitionCell
            label="Civil twilight end"
            time={formatClockInTz(data?.civil_twilight_end ?? null, tz)}
          />
          <TransitionCell
            label="Nautical twilight end"
            time={formatClockInTz(data?.nautical_twilight_end ?? null, tz)}
          />
          <TransitionCell
            label="Astronomical twilight end"
            time={formatClockInTz(data?.astronomical_twilight_end ?? null, tz)}
          />
        </Grid>
      </Paper>

      {/* Morning transitions */}
      <Paper variant="outlined" sx={{ p: 2.5 }}>
        <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 2 }}>
          Morning
        </Typography>
        <Grid container spacing={2}>
          <TransitionCell
            label="Astronomical twilight start"
            time={formatClockInTz(data?.astronomical_twilight_start ?? null, tz)}
          />
          <TransitionCell
            label="Nautical twilight start"
            time={formatClockInTz(data?.nautical_twilight_start ?? null, tz)}
          />
          <TransitionCell
            label="Civil twilight start"
            time={formatClockInTz(data?.civil_twilight_start ?? null, tz)}
          />
          <TransitionCell
            label="Sunrise"
            time={formatClockInTz(data?.sunrise ?? null, tz)}
          />
        </Grid>
      </Paper>

      {/* Moon */}
      <Paper variant="outlined" sx={{ p: 2.5 }}>
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
              <Typography variant="body2" color="text.secondary">
                {data?.moon_phase_name ?? DASH}
              </Typography>
            </Box>
          </Stack>

          <Box sx={{ display: "flex", gap: 4 }}>
            <Box>
              <Typography variant="caption" color="text.secondary">
                Moonrise
              </Typography>
              <Typography variant="h6" sx={{ fontFamily: "monospace" }}>
                {formatClockInTz(data?.moonrise ?? null, tz)}
              </Typography>
            </Box>
            <Box>
              <Typography variant="caption" color="text.secondary">
                Moonset
              </Typography>
              <Typography variant="h6" sx={{ fontFamily: "monospace" }}>
                {formatClockInTz(data?.moonset ?? null, tz)}
              </Typography>
            </Box>
          </Box>
        </Stack>
      </Paper>

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
