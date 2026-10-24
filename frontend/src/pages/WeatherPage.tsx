import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useSearchParams } from "react-router-dom";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Stack from "@mui/material/Stack";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Typography from "@mui/material/Typography";
import { fetchLocations, type Location } from "@/api/locations";
import {
  fetchImagingRules,
  fetchPresets,
  forecastQueryOptions,
  type ImagingRules,
  type NightControls,
} from "@/api/weather";
import type { WeatherUnits } from "@/api/settings";
import { setActivity } from "@/api/client";
import { useSettingsStore } from "@/stores/settingsStore";
import { buildClock, WEEK_NIGHTS } from "@/lib/weatherVerdict";
import LocationSelector from "@/components/weather/LocationSelector";
import MethodologyInfo from "@/components/weather/MethodologyInfo";
import NightDetailPanel from "@/components/weather/NightDetailPanel";
import RulesBar from "@/components/weather/RulesBar";
import RulesEditor from "@/components/weather/RulesEditor";
import WeekList from "@/components/weather/WeekList";
import { EasterEggWand } from "@/components/EasterEggWand";
import { useNow } from "@/hooks/useNow";

const WEATHER_INCANTATIONS = [
  "sudo rm -rf /atmosphere/clouds/*",
  "Have you tried turning the clouds off and on again?",
  "Sacrificing a USB cable to the weather gods...",
  "Dear clouds, I have 10 hours of Ha to capture. Kindly move along.",
  "I promise to finally collimate the SCT if the skies clear",
  "Alexa, set weather to 'photons only'",
  "The seeing will be excellent. I have spoken.",
  "Plot twist: the forecast was wrong. It's clear!",
  "Clear Outside says 0% cloud. Clear Outside has never lied. Right?",
  "I didn't spend $3,000 on narrowband filters to image clouds",
  "The forecast said clear. My roof says otherwise.",
  "Checking Clear Outside for the 47th time today...",
  "Maybe if I set up all my gear the clouds will part out of spite",
  "I'll even image in LRGB if you just stop raining",
  "The clouds are just nature's flats. Very thick flats.",
  "Jet stream forecast: directly over your house, specifically",
  "The sucker hole giveth, and the sucker hole taketh away",
  "Fun fact: my mount tracks perfectly on cloudy nights",
  "The only guaranteed clear night is the one you don't plan for",
  "Error: sky.clear() returned FALSE",
];

const NATURAL_NIGHT_CONTROLS: NightControls = {
  gear_out: null,
  gear_in: null,
  imaging_from: null,
  imaging_until: null,
};

function nightControlError(error: unknown): string | null {
  if (!(error instanceof Error)) return null;
  return /\b(?:gear_out|gear_in|imaging_from|imaging_until|imaging controls)\b/.test(error.message)
    ? error.message
    : null;
}

function fetchedLabel(iso: string, timezone: string): string {
  try {
    return new Intl.DateTimeFormat(undefined, {
      timeZone: timezone,
      hour: "numeric",
      minute: "2-digit",
      month: "short",
      day: "numeric",
    }).format(new Date(iso));
  } catch {
    return new Date(iso).toLocaleString();
  }
}

function evaluatedLabel(iso: string, timezone: string): string {
  try {
    return new Intl.DateTimeFormat(undefined, {
      timeZone: timezone,
      hour: "numeric",
      minute: "2-digit",
    }).format(new Date(iso));
  } catch {
    return new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  }
}

export default function WeatherPage() {
  const queryClient = useQueryClient();
  const [locationId, setLocationId] = useState<number | null>(null);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  // Fred: the 7-day forecast and the outlook are tabs; the forecast opens first.
  const [tab, setTab] = useState<"week" | "outlook">("week");
  const [pendingDate, setPendingDate] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [draftRules, setDraftRules] = useState<ImagingRules | null>(null);
  const [nightControls, setNightControls] = useState<Record<string, NightControls>>({});
  const [controlNotice, setControlNotice] = useState<string | null>(null);
  const handledControlError = useRef<unknown>(null);
  const [searchParams, setSearchParams] = useSearchParams();
  const { pathname } = useLocation();
  const now = useNow(15_000);
  const routeActive = pathname === "/weather";
  const settings = useSettingsStore((state) => state.settings);
  const units: WeatherUnits = settings?.weather_units ?? "metric";

  const { data: locations = [] } = useQuery<Location[]>({
    queryKey: ["locations"],
    queryFn: fetchLocations,
  });
  const defaultLocation = locations.find((location) => location.is_default) ?? locations[0] ?? null;
  const selectedLocation = locations.find((location) => location.id === locationId) ?? null;

  const rulesQuery = useQuery({
    queryKey: ["imaging-rules", locationId],
    queryFn: () => fetchImagingRules(locationId!),
    enabled: locationId != null,
  });
  const presetsQuery = useQuery({
    queryKey: ["imaging-rule-presets"],
    queryFn: fetchPresets,
    staleTime: Infinity,
  });
  const forecastQuery = useQuery({
    ...forecastQueryOptions(locationId ?? 0, draftRules ?? undefined, nightControls),
    enabled: routeActive && locationId != null,
    refetchInterval: routeActive && locationId != null ? 60_000 : false,
    placeholderData: keepPreviousData,
  });
  const forecast = forecastQuery.data?.location_id === locationId
    ? forecastQuery.data
    : undefined;

  useEffect(() => {
    if (!defaultLocation || locationId !== null) return;
    const timer = window.setTimeout(
      () => setLocationId((current) => current ?? defaultLocation.id),
      0,
    );
    return () => window.clearTimeout(timer);
  }, [defaultLocation, locationId]);

  useEffect(() => {
    if (pathname !== "/weather") return;
    const locParam = searchParams.get("location");
    const dateParam = searchParams.get("date");
    if (locParam === null && dateParam === null) return;
    const id = locParam !== null ? Number.parseInt(locParam, 10) : Number.NaN;
    queueMicrotask(() => {
      if (Number.isFinite(id) && id !== locationId) {
        setLocationId(id);
        setSelectedDate(null);
        setEditing(false);
        setDraftRules(null);
        setNightControls({});
        setControlNotice(null);
        const location = locations.find((entry) => entry.id === id);
        if (location) setActivity(`Weather — ${location.name}`);
      }
      if (dateParam !== null) setPendingDate(dateParam);
    });
    setSearchParams({}, { replace: true });
  }, [locationId, locations, pathname, searchParams, setSearchParams]);

  useEffect(() => {
    if (pendingDate === null || !forecast || forecast.location_id !== locationId) return;
    const timer = window.setTimeout(() => {
      const index = forecast.nights.findIndex((night) => night.date === pendingDate);
      if (index >= 0) {
        setActivity(`Weather — Night ${pendingDate}`);
        setSelectedDate(pendingDate);
        setTab(index >= WEEK_NIGHTS ? "outlook" : "week");
      }
      setPendingDate(null);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [forecast, locationId, pendingDate]);

  useEffect(() => {
    if (!forecast) return;
    const validDates = new Set(forecast.nights.map((night) => night.date));
    const ignored = new Set(forecast.ignored_controls);
    const rainPolicy = draftRules?.rain_policy ?? rulesQuery.data?.rules.rain_policy ?? forecast.rules.rain_policy;
    const timer = window.setTimeout(() => {
      setNightControls((current) => {
        const next = Object.fromEntries(Object.entries(current).flatMap(([date, controls]) => {
          if (!validDates.has(date)) return [];
          if (!ignored.has(date) || rainPolicy === "night_off") return [[date, controls]];
          const applicable = { ...controls, gear_out: null, gear_in: null };
          return applicable.imaging_from || applicable.imaging_until ? [[date, applicable]] : [];
        }));
        return JSON.stringify(next) === JSON.stringify(current) ? current : next;
      });
      if (selectedDate && !validDates.has(selectedDate)) setSelectedDate(null);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [draftRules?.rain_policy, forecast, rulesQuery.data?.rules.rain_policy, selectedDate]);

  const clock = useMemo(() => buildClock(forecast?.nights ?? []), [forecast?.nights]);
  const selectedNight = forecast?.nights.find((night) => night.date === selectedDate) ?? null;
  const effectiveRules = draftRules ?? rulesQuery.data?.rules ?? forecast?.rules ?? null;
  const saved = rulesQuery.data?.saved ?? forecast?.rules_saved ?? false;
  const weekNights = useMemo(() => forecast?.nights.slice(0, WEEK_NIGHTS) ?? [], [forecast?.nights]);
  const outlookNights = useMemo(() => forecast?.nights.slice(WEEK_NIGHTS) ?? [], [forecast?.nights]);
  // The editor's "this week" summary counts the first seven nights only.
  const previewCounts = useMemo(() => ({
    go: weekNights.filter((night) => night.verdict === "go").length,
    uncertain: weekNights.filter((night) => night.verdict === "uncertain").length,
    no: weekNights.filter((night) => night.verdict === "no").length,
    notEnough: weekNights.filter((night) => night.verdict === "not_enough_data").length,
  }), [weekNights]);
  const handleDraftChange = useCallback((rules: ImagingRules | null) => setDraftRules(rules), []);

  useEffect(() => {
    if (!effectiveRules) return;
    const timer = window.setTimeout(() => {
      setNightControls((current) => {
        if (effectiveRules.rain_policy === "night_off") return current;
        let changed = false;
        const next = Object.fromEntries(Object.entries(current).flatMap(([date, controls]) => {
          if (controls.gear_out === null && controls.gear_in === null) return [[date, controls]];
          changed = true;
          const applicable = { ...controls, gear_out: null, gear_in: null };
          return applicable.imaging_from || applicable.imaging_until ? [[date, applicable]] : [];
        }));
        return changed ? next : current;
      });
    }, 0);
    return () => window.clearTimeout(timer);
  }, [effectiveRules]);

  const controlValidationError = nightControlError(forecastQuery.error);
  useEffect(() => {
    if (!controlValidationError) {
      handledControlError.current = null;
      return;
    }
    if (handledControlError.current === forecastQuery.error) return;
    if (Object.keys(nightControls).length === 0) return;
    handledControlError.current = forecastQuery.error;
    const affectedDates = Object.keys(nightControls).filter((date) => controlValidationError.includes(date));
    const timer = window.setTimeout(() => {
      setNightControls((current) => {
        if (affectedDates.length === 0) return {};
        const next = { ...current };
        affectedDates.forEach((date) => delete next[date]);
        return next;
      });
      setControlNotice("That time combination isn't valid — reset");
    }, 0);
    return () => window.clearTimeout(timer);
  }, [controlValidationError, forecastQuery.error, nightControls]);

  const handleLocationChange = (id: number) => {
    const location = locations.find((entry) => entry.id === id);
    if (location) setActivity(`Weather — ${location.name}`);
    setLocationId(id);
    setSelectedDate(null);
    setPendingDate(null);
    setEditing(false);
    setDraftRules(null);
    setNightControls({});
    setControlNotice(null);
  };

  const staleMinutes = forecast
    ? Math.max(forecast.stale_sources.forecast ?? 0, forecast.stale_sources.cloud_models ?? 0)
    : 0;
  const notCurrent = Boolean(
    forecast
      && (now - Date.parse(forecast.evaluated_at) > 3 * 60_000 || forecastQuery.isRefetchError),
  );

  const selectNight = (date: string) => { setActivity(`Weather — Night ${date}`); setSelectedDate(date); };
  const detail = selectedNight && effectiveRules && (
    <NightDetailPanel
      key={`${selectedNight.date}-${effectiveRules.rain_policy}`}
      night={selectedNight}
      clock={clock}
      rules={effectiveRules}
      units={units}
      controls={nightControls[selectedNight.date] ?? NATURAL_NIGHT_CONTROLS}
      onControlsChange={(controls) => {
        setControlNotice(null);
        setNightControls((current) => {
          const next = { ...current };
          if (Object.values(controls).some((value) => value !== null)) next[selectedNight.date] = controls;
          else delete next[selectedNight.date];
          return next;
        });
      }}
      onClose={() => setSelectedDate(null)}
    />
  );
  const activeTab = outlookNights.length > 0 ? tab : "week";

  return (
    <Box sx={{ p: { xs: 2, md: 3 }, maxWidth: 1400, width: "100%", overflowX: "hidden" }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 2 }}>
        <Typography variant="h5">Weather Forecast</Typography>
        <EasterEggWand lines={WEATHER_INCANTATIONS} tooltip="Cast a clear sky incantation" />
      </Box>

      <Stack direction={{ xs: "column", sm: "row" }} gap={2} alignItems={{ sm: "center" }} sx={{ mb: 2 }}>
        <LocationSelector selectedId={locationId} onChange={handleLocationChange} />
        {forecast && <Typography variant="caption" color="text.secondary" sx={{ ml: { sm: "auto" } }}>Forecast fetched {fetchedLabel(forecast.fetched_at, forecast.timezone)}</Typography>}
        <Button size="small" variant="outlined" disabled={!locationId || forecastQuery.isFetching} onClick={() => void queryClient.invalidateQueries({ queryKey: ["weather-forecast", locationId] })}>
          {forecastQuery.isFetching && forecast ? "Refreshing…" : "Refresh"}
        </Button>
      </Stack>

      {forecast && forecast.geo_timezone && forecast.timezone !== forecast.geo_timezone && (
        <Typography variant="caption" color="text.secondary" sx={{ mb: 1, display: "block" }}>Times shown in {forecast.timezone} (location is in {forecast.geo_timezone})</Typography>
      )}
      {staleMinutes > 0 && <Typography variant="caption" color="primary.main" sx={{ mb: 1, display: "block" }}>Showing a forecast {Math.round(staleMinutes / 60)} h old — Open-Meteo could not be reached</Typography>}
      {forecast?.nights.some((night) => night.default_cloud_used) && <Typography variant="caption" color="text.secondary" sx={{ mb: 1, display: "block" }}>Some hours use Open-Meteo&apos;s default cloud forecast — your selected forecasts don&apos;t reach them</Typography>}

      {effectiveRules && selectedLocation && (
        <RulesBar locationName={selectedLocation.name} rules={effectiveRules} units={units} onEdit={() => setEditing(true)} editing={editing} />
      )}
      {!saved && !editing && selectedLocation && effectiveRules && (
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1.5 }}>
          <Typography variant="body2" color="text.secondary">These are default rules — set your own for {selectedLocation.name}</Typography>
          <Button size="small" onClick={() => setEditing(true)}>Edit rules</Button>
        </Box>
      )}
      {editing && selectedLocation && effectiveRules && (
        <RulesEditor
          key={selectedLocation.id}
          locationId={selectedLocation.id}
          locationName={selectedLocation.name}
          saved={saved}
          rules={effectiveRules}
          units={units}
          presets={presetsQuery.data ?? []}
          otherLocations={locations.filter((location) => location.id !== selectedLocation.id)}
          onDraftChange={handleDraftChange}
          onCancel={() => setEditing(false)}
          onSaved={() => { setEditing(false); setDraftRules(null); }}
          previewCounts={previewCounts}
          updating={forecastQuery.isFetching}
        />
      )}

      {controlNotice && <Typography color="warning.main" sx={{ mb: 2 }}>{controlNotice}</Typography>}
      {forecastQuery.error && !controlValidationError && <Typography color="warning.main" sx={{ mb: 2 }}>{forecastQuery.error instanceof Error ? forecastQuery.error.message : "Failed to load forecast."}</Typography>}
      {forecastQuery.isLoading && <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 2 }}><CircularProgress size={16} /><Typography color="text.secondary">Loading forecast…</Typography></Box>}

      {forecast && (
        <>
          <Tabs
            value={activeTab}
            onChange={(_, value: "week" | "outlook") => { setTab(value); setSelectedDate(null); }}
            sx={{ mb: 1.5, borderBottom: 1, borderColor: "divider", minHeight: 40 }}
          >
            <Tab value="week" label="7-day forecast" sx={{ minHeight: 40 }} />
            {outlookNights.length > 0 && (
              <Tab value="outlook" label={`Outlook · days ${WEEK_NIGHTS + 1}–${WEEK_NIGHTS + outlookNights.length}`} sx={{ minHeight: 40 }} />
            )}
          </Tabs>
          {activeTab === "outlook" && (
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
              Hourly cloud forecasts this far ahead change a lot between updates. Use these nights for planning, not for deciding to put gear out.
            </Typography>
          )}
          {notCurrent && (
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
              Not current — last evaluated {evaluatedLabel(forecast.evaluated_at, forecast.timezone)}
            </Typography>
          )}
          <WeekList
            key={activeTab}
            nights={activeTab === "week" ? weekNights : outlookNights}
            clock={clock}
            selectedDate={selectedDate}
            onSelect={selectNight}
            units={units}
            notCurrent={notCurrent}
          />
          {detail}
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 2 }}>
            Weather data by <a href="https://open-meteo.com/" target="_blank" rel="noopener noreferrer" style={{ color: "inherit" }}>Open-Meteo.com</a>
          </Typography>
        </>
      )}
      <MethodologyInfo />
    </Box>
  );
}
