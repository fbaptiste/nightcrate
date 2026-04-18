import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import FormControl from "@mui/material/FormControl";
import FormHelperText from "@mui/material/FormHelperText";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchCacheSize, clearCache } from "@/api/aberration";
import { clearWeatherCache, fetchWeatherCacheStats } from "@/api/weather";
import { useSettingsStore } from "@/stores/settingsStore";

export function SettingsPage() {
  const { settings, update } = useSettingsStore();
  const queryClient = useQueryClient();
  const cacheQuery = useQuery({
    queryKey: ["aberration-cache-size"],
    queryFn: fetchCacheSize,
  });
  const cacheMB = cacheQuery.data ? (cacheQuery.data.bytes / (1024 * 1024)).toFixed(2) : "…";

  const weatherCacheQuery = useQuery({
    queryKey: ["weather-cache-stats"],
    queryFn: fetchWeatherCacheStats,
  });
  const weatherCacheKB = weatherCacheQuery.data
    ? (weatherCacheQuery.data.bytes / 1024).toFixed(1)
    : "…";
  const weatherCacheRows = weatherCacheQuery.data?.rows ?? 0;

  if (!settings) {
    return <Typography sx={{ p: 3 }} color="text.secondary">Loading…</Typography>;
  }

  return (
    <Box sx={{ display: "flex", justifyContent: "center", p: 4, overflow: "auto" }}>
      <Box sx={{ width: "100%", maxWidth: 560, display: "flex", flexDirection: "column", gap: 3 }}>
        <Typography variant="h5">Settings</Typography>

        {/* Appearance */}
        <Card variant="outlined">
          <CardContent>
            <Typography variant="body2" color="text.secondary" fontWeight={500} sx={{ mb: 2, textTransform: "uppercase", letterSpacing: "0.05em", fontSize: "0.7rem" }}>
              Appearance
            </Typography>
            <FormControl fullWidth size="small">
              <InputLabel id="theme-label">Theme</InputLabel>
              <Select
                labelId="theme-label"
                label="Theme"
                value={settings.theme}
                onChange={(e) => update({ theme: e.target.value as "light" | "dark" | "browser" })}
                sx={{ maxWidth: 220 }}
              >
                <MenuItem value="light">Light</MenuItem>
                <MenuItem value="dark">Dark</MenuItem>
                <MenuItem value="browser">Browser (auto)</MenuItem>
              </Select>
            </FormControl>
          </CardContent>
        </Card>

        {/* Performance */}
        <Card variant="outlined">
          <CardContent>
            <Typography variant="body2" color="text.secondary" fontWeight={500} sx={{ mb: 2, textTransform: "uppercase", letterSpacing: "0.05em", fontSize: "0.7rem" }}>
              Performance
            </Typography>

            <Box sx={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", mb: 3 }}>
              <Box>
                <Typography variant="body1">GPU Acceleration</Typography>
                <Typography variant="body2" color="text.secondary">
                  Use GPU acceleration (Apple Metal / NVIDIA CUDA) when available
                </Typography>
              </Box>
              <Switch
                checked={settings.gpu_acceleration}
                onChange={(e) => update({ gpu_acceleration: e.target.checked })}
              />
            </Box>

            <Box>
              <Typography variant="body1" gutterBottom>Max Worker Cores</Typography>
              <TextField
                type="number"
                size="small"
                placeholder="auto"
                value={settings.max_worker_cores ?? ""}
                onChange={(e) => {
                  const val = e.target.value;
                  const n = parseInt(val, 10);
                  update({ max_worker_cores: val === "" || isNaN(n) ? null : n });
                }}
                inputProps={{ min: 1 }}
                sx={{ width: 120 }}
              />
              <FormHelperText>
                Limit parallel processing cores. Leave blank to use all available cores minus one.
              </FormHelperText>
            </Box>
          </CardContent>
        </Card>

        {/* Aberration Cache */}
        <Card variant="outlined">
          <CardContent>
            <Typography variant="body2" color="text.secondary" fontWeight={500} sx={{ mb: 2, textTransform: "uppercase", letterSpacing: "0.05em", fontSize: "0.7rem" }}>
              Aberration Cache
            </Typography>
            <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <Box>
                <Typography variant="body1">Cache Size</Typography>
                <Typography variant="body2" color="text.secondary">
                  {cacheMB} MB used by cached star detection results
                </Typography>
              </Box>
              <Button
                variant="outlined"
                size="small"
                onClick={async () => {
                  await clearCache();
                  queryClient.invalidateQueries({ queryKey: ["aberration-cache-size"] });
                }}
              >
                Clear All
              </Button>
            </Box>
          </CardContent>
        </Card>

        {/* Weather */}
        <Card variant="outlined">
          <CardContent>
            <Typography variant="body2" color="text.secondary" fontWeight={500} sx={{ mb: 2, textTransform: "uppercase", letterSpacing: "0.05em", fontSize: "0.7rem" }}>
              Weather
            </Typography>

            <Box sx={{ mb: 3 }}>
              <Typography variant="body1" gutterBottom>Weather forecast cache duration (hours)</Typography>
              <TextField
                type="number"
                size="small"
                value={settings.weather_cache_ttl_hours}
                onChange={(e) => {
                  const val = e.target.value;
                  const n = parseInt(val, 10);
                  if (!isNaN(n) && n >= 1 && n <= 24) {
                    update({ weather_cache_ttl_hours: n });
                  }
                }}
                inputProps={{ min: 1, max: 24 }}
                sx={{ width: 120 }}
              />
              <FormHelperText>
                How long to reuse cached forecast data before fetching fresh data (1–24 hours).
              </FormHelperText>
            </Box>

            <Box sx={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
              <Typography variant="body1">Include moon in quality score by default</Typography>
              <Switch
                checked={settings.weather_moon_penalty}
                onChange={(e) => update({ weather_moon_penalty: e.target.checked })}
              />
            </Box>

            <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mt: 2 }}>
              <Box>
                <Typography variant="body1">Temperature &amp; wind units</Typography>
                <Typography variant="body2" color="text.secondary">
                  Both units are always shown; this controls which is primary
                </Typography>
              </Box>
              <FormControl size="small" sx={{ minWidth: 120 }}>
                <Select
                  value={settings.weather_units}
                  onChange={(e) => update({ weather_units: e.target.value as "metric" | "imperial" })}
                >
                  <MenuItem value="metric">Metric</MenuItem>
                  <MenuItem value="imperial">Imperial</MenuItem>
                </Select>
              </FormControl>
            </Box>

            <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mt: 3 }}>
              <Box>
                <Typography variant="body1">Forecast cache</Typography>
                <Typography variant="body2" color="text.secondary">
                  {weatherCacheRows} {weatherCacheRows === 1 ? "entry" : "entries"} · {weatherCacheKB} KB
                  {" "}(weather, PWV, AOD for all locations)
                </Typography>
              </Box>
              <Button
                variant="outlined"
                size="small"
                disabled={weatherCacheRows === 0}
                onClick={async () => {
                  await clearWeatherCache();
                  queryClient.invalidateQueries({ queryKey: ["weather-cache-stats"] });
                }}
              >
                Clear All
              </Button>
            </Box>
          </CardContent>
        </Card>
      </Box>
    </Box>
  );
}
