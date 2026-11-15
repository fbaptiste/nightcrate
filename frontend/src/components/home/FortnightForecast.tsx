import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { useQueries } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Skeleton from "@mui/material/Skeleton";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { Link } from "react-router-dom";
import { fetchFortnight, type ForecastLocation, type FortnightNight } from "@/api/home";
import type { Verdict } from "@/api/weather";
import {
  fortnightDates,
  forecastCellLabel,
  formatDate,
  rowEnabled,
  VERDICT_LABELS,
  type ForecastRowStatus,
} from "@/lib/home";
import { weatherPalette } from "@/lib/weatherPalette";

const MARKS: Record<Verdict, string> = {
  go: "✓",
  uncertain: "?",
  no: "✕",
  not_enough_data: "–",
  night_over: "–",
};

function formatTime(value: string): string {
  return new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(
    new Date(value),
  );
}

function VerdictMark({ verdict, small = false }: { verdict: Verdict; small?: boolean }) {
  const size = small ? 16 : 20;
  return (
    <Box
      component="span"
      aria-hidden="true"
      sx={(theme) => {
        const palette = weatherPalette(theme);
        const neutral = verdict === "not_enough_data" || verdict === "night_over";
        return {
          width: size,
          height: size,
          borderRadius: "50%",
          display: "grid",
          placeItems: "center",
          flex: "0 0 auto",
          fontSize: small ? 10 : 12,
          lineHeight: 1,
          fontWeight: 700,
          ...(verdict === "go" && { bgcolor: palette.clearCell, color: palette.onClearCell }),
          ...(verdict === "uncertain" && { border: `2px solid ${palette.uncertain}`, color: palette.uncertain }),
          ...(verdict === "no" && { bgcolor: palette.noGround, color: palette.onNo }),
          ...(neutral && { border: `2px dashed ${palette.neutralText}`, color: palette.neutralText }),
        };
      }}
    >
      {MARKS[verdict]}
    </Box>
  );
}

function locationNote(location: ForecastLocation): string | null {
  if (location.note === "default") return "Default location";
  if (location.note === "used") {
    return `Used by ${location.active_projects} active ${location.active_projects === 1 ? "project" : "projects"}`;
  }
  return null;
}

function ForecastCell({ location, night }: { location: ForecastLocation; night: FortnightNight }) {
  const label = forecastCellLabel(
    location.name,
    night.date,
    night.verdict,
    night.moonless_dark_hours,
  );
  return (
    <Tooltip title={label} arrow>
      <Box
        component={Link}
        to={`/weather?location=${location.location_id}&date=${night.date}`}
        aria-label={label}
        sx={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "3px", color: "text.secondary", textDecoration: "none", fontSize: 11, py: "2px" }}
      >
        <VerdictMark verdict={night.verdict} />
        <Box sx={{ width: 14, height: 30, display: "flex", alignItems: "flex-end" }}>
          <Box
            sx={(theme) => ({
              width: "100%",
              height: `${Math.min(30, (night.moonless_dark_hours / 11) * 30)}px`,
              bgcolor: theme.palette.mode === "dark" ? "#6c7ea3" : "#5a6c8f",
              borderRadius: "2px 2px 0 0",
            })}
          />
        </Box>
        {night.moonless_dark_hours.toFixed(1)} h
      </Box>
    </Tooltip>
  );
}

export function FortnightForecast({ locations }: { locations: ForecastLocation[] }) {
  const dates = useMemo(() => fortnightDates(new Date()), []);
  const [enabledThrough, setEnabledThrough] = useState(0);
  const forecasts = useQueries({
    queries: locations.map((location, index) => ({
      queryKey: ["home-fortnight", location.location_id],
      queryFn: () => fetchFortnight(location.location_id),
      enabled: index <= enabledThrough,
      staleTime: 5 * 60_000,
      retry: 1,
      refetchOnWindowFocus: false,
    })),
  });
  const statuses = forecasts.map((forecast): ForecastRowStatus =>
    forecast.isFetching ? "pending" : forecast.status,
  );
  let nextEnabledThrough = enabledThrough;
  while (
    nextEnabledThrough + 1 < locations.length &&
    rowEnabled(nextEnabledThrough + 1, statuses)
  ) {
    nextEnabledThrough += 1;
  }
  useEffect(() => {
    if (nextEnabledThrough <= enabledThrough) return;
    const timer = window.setTimeout(() => setEnabledThrough(nextEnabledThrough), 0);
    return () => window.clearTimeout(timer);
  }, [enabledThrough, nextEnabledThrough]);

  const anyFetching = forecasts.some((forecast) => forecast.isFetching);
  const refreshSequentially = useCallback(async () => {
    for (const forecast of forecasts) {
      await forecast.refetch({ cancelRefetch: false });
    }
  }, [forecasts]);
  useEffect(() => {
    const handleFocus = () => {
      if (!forecasts.some((forecast) => forecast.isFetching)) {
        void refreshSequentially();
      }
    };
    window.addEventListener("focus", handleFocus);
    return () => window.removeEventListener("focus", handleFocus);
  }, [forecasts, refreshSequentially]);
  const evaluated = forecasts
    .map((forecast) => forecast.data?.evaluated_at)
    .filter((value): value is string => Boolean(value));
  const oldestEvaluation = evaluated.length
    ? evaluated.reduce((oldest, value) =>
        new Date(value).getTime() < new Date(oldest).getTime() ? value : oldest,
      )
    : null;

  return (
    <Box component="section" sx={{ mt: "34px" }}>
      <Typography component="h2" sx={{ fontSize: 16, fontWeight: 600 }}>
        The next two weeks
      </Typography>
      {locations.length === 0 ? (
        <Box sx={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: 2, mt: "12px", p: "16px 18px", border: "1px dashed", borderColor: "divider", borderRadius: "10px", color: "text.secondary", fontSize: 14 }}>
          Add a location to see its weather for the next two weeks.
          <Button component={Link} to="/locations" variant="outlined" size="small">
            Add a location
          </Button>
        </Box>
      ) : (
        <>
          <Box sx={{ overflowX: "auto" }}>
            <Box sx={{ minWidth: 900, display: "grid", gridTemplateColumns: "170px repeat(14, minmax(0, 1fr))", gap: "6px 4px", alignItems: "center", mt: "12px" }}>
              <Box />
              {dates.map((date, index) => (
                <Box key={date} sx={{ textAlign: "center", color: "text.secondary", fontSize: 12 }}>
                  {formatDate(date, { weekday: "short" })}
                  <Typography component="strong" sx={{ display: "block", color: index === 0 ? "primary.main" : "text.primary", fontSize: 13, fontWeight: 600 }}>
                    {formatDate(date, { day: "numeric" })}
                  </Typography>
                </Box>
              ))}
              {locations.map((location, rowIndex) => {
                const forecast = forecasts[rowIndex];
                const nights = new Map(forecast.data?.nights.map((night) => [night.date, night]));
                const note = locationNote(location);
                return (
                  <Fragment key={location.location_id}>
                    <Box sx={{ alignSelf: "stretch", pt: 1, borderTop: 1, borderColor: "divider", fontSize: 13 }}>
                      {location.name}
                      {note && <Typography sx={{ color: "text.secondary", fontSize: 12 }}>{note}</Typography>}
                      {forecast.data?.stale_since && (
                        <Typography sx={{ color: "text.secondary", fontSize: 12 }}>
                          Forecast from {formatTime(forecast.data.stale_since)}
                        </Typography>
                      )}
                    </Box>
                    {forecast.isError ? (
                      <Box sx={{ gridColumn: "span 14", borderTop: 1, borderColor: "divider", py: 1, color: "text.secondary", fontSize: 13 }}>
                        Couldn't load the forecast for {location.name}.{" "}
                        <Button
                          size="small"
                          variant="text"
                          disabled={anyFetching}
                          onClick={() => void forecast.refetch({ cancelRefetch: false })}
                        >
                          Try again
                        </Button>
                      </Box>
                    ) : forecast.isPending ? (
                      dates.map((date) => (
                        <Box key={date} sx={{ borderTop: 1, borderColor: "divider", pt: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: "3px" }}>
                          <Skeleton variant="circular" width={20} height={20} />
                          <Skeleton variant="rounded" width={14} height={30} />
                        </Box>
                      ))
                    ) : (
                      dates.map((date) => {
                        const night = nights.get(date);
                        return (
                          <Box key={date} sx={{ borderTop: 1, borderColor: "divider", pt: 1 }}>
                            {night ? (
                              <ForecastCell location={location} night={night} />
                            ) : (
                              <Tooltip title="No forecast for this night" arrow>
                                <Box aria-label="No forecast for this night" sx={{ height: 70, display: "grid", placeItems: "start center", pt: "2px", color: "text.secondary", fontSize: 13 }}>
                                  –
                                </Box>
                              </Tooltip>
                            )}
                          </Box>
                        );
                      })
                    )}
                  </Fragment>
                );
              })}
            </Box>
          </Box>
          <Box sx={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: "6px 18px", mt: "10px", color: "text.secondary", fontSize: "12.5px" }}>
            {(["go", "uncertain", "no"] as Verdict[]).map((verdict) => (
              <Box key={verdict} sx={{ display: "inline-flex", alignItems: "center", gap: "6px" }}>
                <VerdictMark verdict={verdict} small /> {VERDICT_LABELS[verdict]}
              </Box>
            ))}
            <Box>Dark hours with the Moon down, for each location</Box>
            <Box sx={{ ml: "auto", display: "flex", alignItems: "center", gap: 1 }}>
              {oldestEvaluation && <>Updated {formatTime(oldestEvaluation)}</>}
              <Button
                size="small"
                variant="text"
                disabled={anyFetching}
                onClick={() => void refreshSequentially()}
              >
                Refresh
              </Button>
            </Box>
          </Box>
        </>
      )}
    </Box>
  );
}
