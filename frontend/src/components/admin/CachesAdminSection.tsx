/**
 * Admin → Caches section.
 *
 * Consolidates operational controls for every NightCrate cache in one
 * place:
 *
 *   - Thumbnail + sky-tile cache (shared ``thumbnail_cache_max_mb`` budget)
 *   - Aberration cache (per-image star detection results)
 *   - Weather cache (forecast / PWV / AOD; also hosts the
 *     ``weather_cache_ttl_hours`` setting)
 *
 * Prior to v0.18.1 these lived on the Settings page, which was
 * muddling user preferences (theme, units, planner defaults) with
 * operational state (clear cache, re-fetch budgets). Settings now
 * keeps only preferences; cache operations live here next to the
 * database + catalog controls.
 */
import { useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import FormControl from "@mui/material/FormControl";
import FormHelperText from "@mui/material/FormHelperText";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Select from "@mui/material/Select";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { clearCache, fetchCacheSize } from "@/api/aberration";
import { clearThumbnailCache, fetchThumbnailCacheStats } from "@/api/planner";
import { clearWeatherCache, fetchWeatherCacheStats } from "@/api/weather";
import { useSettingsStore } from "@/stores/settingsStore";
import { useThumbnailCacheStore } from "@/stores/thumbnailCacheStore";

export default function CachesAdminSection() {
  const { settings, update } = useSettingsStore();
  const queryClient = useQueryClient();

  const aberrationQuery = useQuery({
    queryKey: ["aberration-cache-size"],
    queryFn: fetchCacheSize,
  });
  const weatherQuery = useQuery({
    queryKey: ["weather-cache-stats"],
    queryFn: fetchWeatherCacheStats,
  });
  const thumbnailQuery = useQuery({
    queryKey: ["thumbnail-cache-stats"],
    queryFn: fetchThumbnailCacheStats,
  });

  // Bump the cache-buster store when the generation changes (e.g.
  // after a user clicks "Clear All" below) so every ThumbnailCell
  // re-renders with a fresh ``&_g=N`` URL suffix — defeats any stale
  // 200s the browser's HTTP cache is still holding from before the
  // clear.
  const setGeneration = useThumbnailCacheStore((s) => s.setGeneration);
  useEffect(() => {
    if (thumbnailQuery.data?.generation != null) {
      setGeneration(thumbnailQuery.data.generation);
    }
  }, [thumbnailQuery.data?.generation, setGeneration]);

  const aberrationMB = aberrationQuery.data
    ? (aberrationQuery.data.bytes / (1024 * 1024)).toFixed(2)
    : "…";

  const weatherKB = weatherQuery.data
    ? (weatherQuery.data.bytes / 1024).toFixed(1)
    : "…";
  const weatherRows = weatherQuery.data?.rows ?? 0;

  const thumbnailMB = thumbnailQuery.data
    ? (thumbnailQuery.data.total_bytes / (1024 * 1024)).toFixed(2)
    : "…";
  const thumbnailMaxMB = thumbnailQuery.data
    ? Math.round(thumbnailQuery.data.max_bytes / (1024 * 1024))
    : 500;
  const thumbnailRows = thumbnailQuery.data?.row_count ?? 0;

  if (!settings) return null;

  return (
    <>
      <Typography variant="h6" sx={{ mb: 1, mt: 3 }}>
        Caches
      </Typography>
      <Paper sx={{ p: 2 }}>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Operational controls for NightCrate's on-disk caches.
          Clearing a cache never deletes source data — only forces the
          affected subsystem to re-fetch or re-compute on next request.
        </Typography>

        {/* Thumbnail + sky-tile cache */}
        <Box
          sx={{
            py: 1.5,
            borderBottom: 1,
            borderColor: "divider",
          }}
        >
          <Box
            sx={{
              display: "flex",
              flexDirection: { xs: "column", sm: "row" },
              alignItems: { sm: "center" },
              gap: 2,
            }}
          >
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Typography variant="body2" fontWeight={600}>
                Thumbnail + sky-tile cache
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {thumbnailRows} {thumbnailRows === 1 ? "image" : "images"}
                {" · "}
                {thumbnailMB} MB of {thumbnailMaxMB} MB · shared budget
                covers ``APP_DIR/thumbnails`` (per-DSO) and
                ``APP_DIR/sky_tiles`` (HEALPix-regional composite cells)
              </Typography>
            </Box>
            <FormControl size="small" sx={{ minWidth: 120 }}>
              <Select
                value={settings.thumbnail_cache_max_mb}
                onChange={(e) =>
                  update({ thumbnail_cache_max_mb: Number(e.target.value) })
                }
              >
                {[50, 200, 500, 1000, 2000, 5000].map((mb) => (
                  <MenuItem key={mb} value={mb}>
                    {mb} MB
                  </MenuItem>
                ))}
              </Select>
              <FormHelperText>Budget</FormHelperText>
            </FormControl>
            <Button
              variant="outlined"
              size="small"
              disabled={thumbnailRows === 0}
              onClick={async () => {
                await clearThumbnailCache();
                queryClient.invalidateQueries({
                  queryKey: ["thumbnail-cache-stats"],
                });
              }}
            >
              Clear All
            </Button>
          </Box>
        </Box>

        {/* Aberration cache */}
        <Box
          sx={{
            py: 1.5,
            borderBottom: 1,
            borderColor: "divider",
            display: "flex",
            flexDirection: { xs: "column", sm: "row" },
            alignItems: { sm: "center" },
            gap: 2,
          }}
        >
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography variant="body2" fontWeight={600}>
              Aberration cache
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {aberrationMB} MB of cached star-detection results
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

        {/* Weather cache + TTL knob */}
        <Box
          sx={{
            py: 1.5,
            display: "flex",
            flexDirection: { xs: "column", sm: "row" },
            alignItems: { sm: "center" },
            gap: 2,
          }}
        >
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography variant="body2" fontWeight={600}>
              Weather forecast cache
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {weatherRows} {weatherRows === 1 ? "entry" : "entries"} ·{" "}
              {weatherKB} KB (forecast, PWV, AOD across all locations)
            </Typography>
          </Box>
          <TextField
            type="number"
            size="small"
            label="TTL (hours)"
            value={settings.weather_cache_ttl_hours}
            onChange={(e) => {
              const n = parseInt(e.target.value, 10);
              if (!isNaN(n) && n >= 1 && n <= 24) {
                update({ weather_cache_ttl_hours: n });
              }
            }}
            inputProps={{ min: 1, max: 24 }}
            sx={{ width: 120 }}
          />
          <Button
            variant="outlined"
            size="small"
            disabled={weatherRows === 0}
            onClick={async () => {
              await clearWeatherCache();
              queryClient.invalidateQueries({ queryKey: ["weather-cache-stats"] });
            }}
          >
            Clear All
          </Button>
        </Box>
      </Paper>
    </>
  );
}
