import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Checkbox from "@mui/material/Checkbox";
import CircularProgress from "@mui/material/CircularProgress";
import FormControlLabel from "@mui/material/FormControlLabel";
import Typography from "@mui/material/Typography";
import { fetchLocations, type Location } from "../api/locations";
import { fetchSettings, type WeatherUnits } from "../api/settings";
import { fetchForecast, fetchHourlyDetail } from "../api/weather";
import LocationSelector from "../components/weather/LocationSelector";
import DailyCard from "../components/weather/DailyCard";
import HourlyTimeline from "../components/weather/HourlyTimeline";
import MethodologyInfo from "../components/weather/MethodologyInfo";
import { EasterEggWand } from "../components/EasterEggWand";

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
  "Cloud sensor reading: YES",
  "Tonight's imaging target: the inside of a cloud deck",
  "Humidity: 97%. Dew point: right now. Tears: also right now.",
  "The weatherman and I are no longer on speaking terms",
  "Object altitude: 72 degrees. Cloud altitude: all of them.",
  "Satellite trail count: still less than my regrets",
  "I name this cloud formation: 'The Horsehead of Disappointment'",
  "Breaking: local man yells at cloud. Cloud does not move.",
  "N.I.N.A. sequence: 200 subs planned, 0 completed, status: 'waiting for sky'",
  "FITS header: WEATHER = 'WHY DO I LIVE HERE'",
];

export default function WeatherPage() {
  const [locationId, setLocationId] = useState<number | null>(null);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [includeMoon, setIncludeMoon] = useState<boolean | null>(null);

  const { data: settings } = useQuery({
    queryKey: ["settings"],
    queryFn: fetchSettings,
  });

  const units: WeatherUnits = settings?.weather_units ?? "metric";

  // Initialize from saved setting once loaded; user can override per-session
  useEffect(() => {
    if (settings && includeMoon === null) {
      setIncludeMoon(settings.weather_moon_penalty);
    }
  }, [settings, includeMoon]);

  const { data: locations = [] } = useQuery<Location[]>({
    queryKey: ["locations"],
    queryFn: fetchLocations,
  });
  const defaultLocation = locations.find((l) => l.is_default) ?? locations[0] ?? null;

  const {
    data: forecast,
    isLoading: forecastLoading,
    error: forecastError,
  } = useQuery({
    queryKey: ["weather-forecast", locationId, includeMoon],
    queryFn: () => fetchForecast(locationId!, includeMoon!),
    enabled: locationId !== null && includeMoon !== null,
  });

  const { data: hourlyDetail, isLoading: hourlyLoading } = useQuery({
    queryKey: ["weather-hourly", locationId, selectedDate, includeMoon],
    queryFn: () => fetchHourlyDetail(locationId!, selectedDate!, includeMoon!),
    enabled: locationId !== null && selectedDate !== null && includeMoon !== null,
  });

  // Auto-select default location when loaded
  useEffect(() => {
    if (defaultLocation && locationId === null) {
      setLocationId(defaultLocation.id);
    }
  }, [defaultLocation, locationId]);

  // Reset selectedDate when location changes
  const handleLocationChange = (id: number) => {
    setLocationId(id);
    setSelectedDate(null);
  };

  return (
    <Box sx={{ p: 3, maxWidth: 1200 }}>
      {/* Header */}
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 2 }}>
        <Typography variant="h5">Weather Forecast</Typography>
        <EasterEggWand lines={WEATHER_INCANTATIONS} tooltip="Cast a clear sky incantation" />
      </Box>

      {/* Controls bar */}
      <Box sx={{ display: "flex", alignItems: "center", gap: 3, mb: 3, flexWrap: "wrap" }}>
        <LocationSelector
          selectedId={locationId}
          onChange={handleLocationChange}
        />
        <FormControlLabel
          control={
            <Checkbox
              checked={includeMoon ?? true}
              onChange={(e) => setIncludeMoon(e.target.checked)}
              size="small"
            />
          }
          label="Include moon in quality score"
        />
      </Box>

      {/* Error state */}
      {forecastError && (
        <Typography color="error" sx={{ mb: 2 }}>
          {forecastError instanceof Error ? forecastError.message : "Failed to load forecast."}
        </Typography>
      )}

      {/* Loading state */}
      {forecastLoading && (
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 2 }}>
          <CircularProgress size={16} />
          <Typography color="text.secondary">Loading forecast...</Typography>
        </Box>
      )}

      {/* 7-day cards */}
      {forecast && !selectedDate && (
        <Typography variant="caption" color="text.secondary" sx={{ mb: 0.5, display: "block" }}>
          Click a day to see hourly details
        </Typography>
      )}
      {forecast && (
        <Box
          sx={{
            display: "flex",
            flexDirection: "row",
            gap: 1.5,
            overflowX: "auto",
            pb: 1,
            mb: 3,
          }}
        >
          {forecast.days.map((day) => (
            <DailyCard
              key={day.date}
              day={day}
              selected={selectedDate === day.date}
              moonIncluded={includeMoon ?? true}
              units={units}
              onClick={() => setSelectedDate(day.date)}
            />
          ))}
        </Box>
      )}

      {/* Hourly detail section */}
      {selectedDate && (
        <Box sx={{ mb: 3 }}>
          <Typography variant="h6" sx={{ mb: 0.5 }}>
            Hourly Detail — {selectedDate}
          </Typography>
          {hourlyLoading ? (
            <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
              <CircularProgress size={16} />
              <Typography color="text.secondary">Loading hourly detail...</Typography>
            </Box>
          ) : (
            hourlyDetail && (
            <HourlyTimeline
              hours={hourlyDetail.hours}
              sunset={hourlyDetail.sunset}
              sunrise={hourlyDetail.sunrise}
              twilight={hourlyDetail.twilight}
              moonPolyline={hourlyDetail.moon_polyline}
              timezone={hourlyDetail.timezone}
              units={units}
            />
          )
          )}
        </Box>
      )}

      {/* Methodology */}
      <MethodologyInfo />
    </Box>
  );
}
