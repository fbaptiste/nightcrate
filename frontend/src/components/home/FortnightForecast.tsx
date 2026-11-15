import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { useQueries } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Skeleton from "@mui/material/Skeleton";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { alpha, type Theme } from "@mui/material/styles";
import { Link } from "react-router-dom";
import { fetchFortnight, type ForecastLocation, type FortnightNight } from "@/api/home";
import type { Verdict } from "@/api/weather";
import {
  darknessFigure,
  darknessLine,
  fortnightDates,
  forecastCellLabel,
  formatDate,
  rowEnabled,
  VERDICT_LABELS,
  type ForecastRowStatus,
} from "@/lib/home";
import { weatherPalette } from "@/lib/weatherPalette";

/** The darkness line's colours: solid where the Moon is down, quiet stripes where it is up. */
function darknessColors(theme: Theme) {
  const dark = theme.palette.mode === "dark";
  return {
    moonDown: dark ? "#6c7ea3" : "#5a6c8f",
    moonUpFill: dark ? "#30353f" : "#e4e7ed",
    moonUpLine: dark ? "#4c5465" : "#b9c0cd",
    midnight: dark ? alpha(theme.palette.common.white, 0.5) : alpha(theme.palette.common.black, 0.45),
  };
}

function runBackground(theme: Theme, moonUp: boolean): string {
  const colors = darknessColors(theme);
  return moonUp
    ? `repeating-linear-gradient(135deg, ${colors.moonUpLine} 0 1px, transparent 1px 4px), ${colors.moonUpFill}`
    : colors.moonDown;
}

const SHALLOW_OUTLINE = { outline: "1px dashed", outlineColor: "text.secondary", outlineOffset: "1px" } as const;

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

/** One night's darkness, start on the left and end on the right. */
function DarknessLineBar({ night }: { night: FortnightNight }) {
  const line = darknessLine(night);
  if (!line) return null;
  return (
    <Box sx={{ position: "relative", height: 9, mt: "2px" }}>
      <Box
        sx={{
          position: "absolute",
          inset: 0,
          borderRadius: "3px",
          overflow: "hidden",
          ...(night.darkness !== "astronomical" && SHALLOW_OUTLINE),
        }}
      >
        {line.segments.map((segment) => (
          <Box
            key={segment.left}
            sx={(theme) => ({
              position: "absolute",
              top: 0,
              bottom: 0,
              left: `${segment.left}%`,
              width: `${segment.width}%`,
              background: runBackground(theme, segment.moonUp),
            })}
          />
        ))}
      </Box>
      {line.midnight !== null && (
        <Box
          sx={(theme) => ({
            position: "absolute",
            top: -3,
            bottom: -3,
            left: `${line.midnight}%`,
            width: "1px",
            bgcolor: darknessColors(theme).midnight,
          })}
        />
      )}
    </Box>
  );
}

function ForecastCell({ location, night }: { location: ForecastLocation; night: FortnightNight }) {
  const label = forecastCellLabel(location.name, night);
  const hasDarkness = night.darkness !== "none" && night.runs.length > 0;
  return (
    <Tooltip title={label} arrow>
      <Box
        component={Link}
        to={`/weather?location=${location.location_id}&date=${night.date}`}
        aria-label={label}
        sx={{ display: "flex", flexDirection: "column", alignItems: "stretch", gap: "5px", color: "text.secondary", textDecoration: "none", fontSize: 11, lineHeight: 1.2, textAlign: "center", whiteSpace: "nowrap", px: "4px", py: "2px" }}
      >
        <Box sx={{ alignSelf: "center" }}>
          <VerdictMark verdict={night.verdict} />
        </Box>
        {hasDarkness ? (
          <>
            <DarknessLineBar night={night} />
            <Box>
              <Box sx={{ color: "text.primary", fontWeight: 500, fontSize: "11.5px" }}>
                {night.moonless_dark_hours.toFixed(1)} h
              </Box>
              {darknessFigure(night)}
            </Box>
          </>
        ) : (
          <Box sx={{ fontSize: "11.5px", pt: "2px" }}>0 h</Box>
        )}
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
  const anyShallow = forecasts.some((forecast) =>
    forecast.data?.nights.some(
      (night) => dates.includes(night.date) && (night.darkness === "nautical" || night.darkness === "civil"),
    ),
  );
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
            <Box sx={{ display: "grid", gridTemplateColumns: "fit-content(240px) repeat(14, minmax(max-content, 1fr))", gap: "6px 4px", alignItems: "center", mt: "12px" }}>
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
                        <Box key={date} sx={{ alignSelf: "stretch", borderTop: 1, borderColor: "divider", pt: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: "3px" }}>
                          <Skeleton variant="circular" width={20} height={20} />
                          <Skeleton variant="rounded" width="100%" height={9} />
                          <Skeleton variant="rounded" width={34} height={26} />
                        </Box>
                      ))
                    ) : (
                      dates.map((date) => {
                        const night = nights.get(date);
                        return (
                          <Box key={date} sx={{ alignSelf: "stretch", borderTop: 1, borderColor: "divider", pt: 1 }}>
                            {night ? (
                              <ForecastCell location={location} night={night} />
                            ) : (
                              <Tooltip title="No forecast for this night" arrow>
                                <Box aria-label="No forecast for this night" sx={{ height: 68, display: "grid", placeItems: "start center", pt: "2px", color: "text.secondary", fontSize: 13 }}>
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
            <Box sx={{ display: "inline-flex", alignItems: "center", gap: "6px" }}>
              <Box aria-hidden sx={(theme) => ({ width: 16, height: 9, borderRadius: "2px", background: runBackground(theme, false) })} />
              Dark, Moon down
            </Box>
            <Box sx={{ display: "inline-flex", alignItems: "center", gap: "6px" }}>
              <Box aria-hidden sx={(theme) => ({ width: 16, height: 9, borderRadius: "2px", background: runBackground(theme, true) })} />
              Dark, Moon up
            </Box>
            <Box sx={{ display: "inline-flex", alignItems: "center", gap: "6px" }}>
              <Box aria-hidden sx={(theme) => ({ width: "1px", height: 15, bgcolor: darknessColors(theme).midnight })} />
              Midnight
            </Box>
            {anyShallow && (
              <Box sx={{ display: "inline-flex", alignItems: "center", gap: "6px" }}>
                <Box aria-hidden sx={{ width: 10, height: 12, mx: "2px", borderRadius: "2px", ...SHALLOW_OUTLINE }} />
                The Sun never gets 18° down: nautical or civil darkness
              </Box>
            )}
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
