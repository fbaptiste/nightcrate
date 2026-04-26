import { useCallback, useEffect, useState } from "react";
import Accordion from "@mui/material/Accordion";
import AccordionDetails from "@mui/material/AccordionDetails";
import AccordionSummary from "@mui/material/AccordionSummary";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import FormControl from "@mui/material/FormControl";
import FormHelperText from "@mui/material/FormHelperText";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Slider from "@mui/material/Slider";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import ErrorIcon from "@mui/icons-material/Error";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import FolderOpenIcon from "@mui/icons-material/FolderOpen";
import { useSettingsStore } from "@/stores/settingsStore";
import { PlannerScoringSection } from "@/components/settings/PlannerScoringSection";
import { FileBrowser } from "@/components/fits/FileBrowser";
import { validateAstapPath } from "@/api/plateSolve";
import { monoFontFamily } from "@/theme/theme";

const sectionHeaderSx = {
  textTransform: "uppercase",
  letterSpacing: "0.05em",
  fontSize: "0.7rem",
  fontWeight: 500,
} as const;

export function SettingsPage() {
  const { settings, update } = useSettingsStore();

  if (!settings) {
    return <Typography sx={{ p: 3 }} color="text.secondary">Loading…</Typography>;
  }

  return (
    <Box sx={{ flex: 1, minHeight: 0, overflow: "auto", p: 4 }}>
      <Box sx={{ maxWidth: 960 }}>
        <Typography variant="h5" sx={{ mb: 2 }}>Settings</Typography>
      <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems="flex-start">
        {/* Left column */}
        <Stack spacing={1} sx={{ flex: 1, minWidth: 0 }}>
          {/* Appearance */}
          <Accordion variant="outlined" disableGutters defaultExpanded={false}>
            <AccordionSummary expandIcon={<ExpandMoreIcon />}>
              <Typography variant="body2" color="text.secondary" sx={sectionHeaderSx}>
                Appearance
              </Typography>
            </AccordionSummary>
            <AccordionDetails>
              <Stack direction="row" spacing={2} alignItems="center">
                <Typography variant="body1">Theme</Typography>
                <FormControl size="small">
                  <Select
                    value={settings.theme}
                    onChange={(e) => update({ theme: e.target.value as "light" | "dark" | "browser" })}
                    sx={{ minWidth: 180 }}
                  >
                    <MenuItem value="light">Light</MenuItem>
                    <MenuItem value="dark">Dark</MenuItem>
                    <MenuItem value="browser">Browser (auto)</MenuItem>
                  </Select>
                </FormControl>
              </Stack>
            </AccordionDetails>
          </Accordion>

          {/* Weather */}
          <Accordion variant="outlined" disableGutters defaultExpanded={false}>
            <AccordionSummary expandIcon={<ExpandMoreIcon />}>
              <Typography variant="body2" color="text.secondary" sx={sectionHeaderSx}>
                Weather
              </Typography>
            </AccordionSummary>
            <AccordionDetails>
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
            </AccordionDetails>
          </Accordion>

          <PlannerScoringSection settings={settings} />
        </Stack>

        {/* Right column */}
        <Stack spacing={1} sx={{ flex: 1, minWidth: 0 }}>
          {/* Performance */}
          <Accordion variant="outlined" disableGutters defaultExpanded={false}>
            <AccordionSummary expandIcon={<ExpandMoreIcon />}>
              <Typography variant="body2" color="text.secondary" sx={sectionHeaderSx}>
                Performance
              </Typography>
            </AccordionSummary>
            <AccordionDetails>
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
            </AccordionDetails>
          </Accordion>

          {/* Plate Solving */}
          <AstapPathSection />

          {/* Target Planner */}
          <Accordion variant="outlined" disableGutters defaultExpanded={false}>
            <AccordionSummary expandIcon={<ExpandMoreIcon />}>
              <Typography variant="body2" color="text.secondary" sx={sectionHeaderSx}>
                Target Planner
              </Typography>
            </AccordionSummary>
            <AccordionDetails>
              <Box sx={{ mb: 2 }}>
                <Typography variant="body1" gutterBottom>Default minimum hours visible</Typography>
                <TextField
                  type="number"
                  size="small"
                  value={settings.planner_min_visibility_hours}
                  onChange={(e) => {
                    const n = parseFloat(e.target.value);
                    if (!isNaN(n) && n >= 0 && n <= 12) update({ planner_min_visibility_hours: n });
                  }}
                  inputProps={{ min: 0, max: 12, step: 0.5 }}
                  sx={{ width: 120 }}
                />
              </Box>

              <Box sx={{ mb: 2 }}>
                <Typography variant="body1" gutterBottom>Default maximum magnitude</Typography>
                <TextField
                  type="number"
                  size="small"
                  value={settings.planner_max_magnitude}
                  onChange={(e) => {
                    const n = parseFloat(e.target.value);
                    if (!isNaN(n) && n >= 5 && n <= 18) update({ planner_max_magnitude: n });
                  }}
                  inputProps={{ min: 5, max: 18, step: 0.5 }}
                  sx={{ width: 120 }}
                />
              </Box>

              <Box sx={{ mb: 3 }}>
                <Typography variant="body1" gutterBottom>Default minimum size (arcmin)</Typography>
                <TextField
                  type="number"
                  size="small"
                  value={settings.planner_min_size_arcmin}
                  onChange={(e) => {
                    const n = parseFloat(e.target.value);
                    if (!isNaN(n) && n >= 0 && n <= 60) update({ planner_min_size_arcmin: n });
                  }}
                  inputProps={{ min: 0, max: 60, step: 1 }}
                  sx={{ width: 120 }}
                />
              </Box>

              <Box sx={{ mb: 3 }}>
                <Typography variant="body1" gutterBottom>
                  Default Size in Frame range: {settings.planner_frames_well_min_pct}% – {settings.planner_frames_well_max_pct}%
                </Typography>
                <Slider
                  size="small"
                  value={[
                    settings.planner_frames_well_min_pct,
                    settings.planner_frames_well_max_pct,
                  ]}
                  min={0}
                  max={200}
                  step={5}
                  disableSwap
                  onChange={(_, v) => {
                    const [lo, hi] = v as [number, number];
                    update({
                      planner_frames_well_min_pct: lo,
                      planner_frames_well_max_pct: hi,
                    });
                  }}
                  sx={{ maxWidth: 360 }}
                />
                <FormHelperText>
                  Initial Size in Frame band on the planner (0–200% = no filter).
                </FormHelperText>
              </Box>

              <Box sx={{ mb: 2 }}>
                <Typography variant="body1" gutterBottom>
                  Default moon separation (Best time of year chart)
                </Typography>
                <Stack direction="row" spacing={1} alignItems="center">
                  <FormControl size="small" sx={{ minWidth: 160 }}>
                    <Select
                      value={settings.planner_moon_sep_deg}
                      onChange={(e) =>
                        update({ planner_moon_sep_deg: Number(e.target.value) })
                      }
                    >
                      <MenuItem value={0}>Ignore moon</MenuItem>
                      {[15, 30, 45, 60, 75, 90].map((deg) => (
                        <MenuItem key={deg} value={deg}>
                          Moon &gt; {deg}&deg;
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                </Stack>
                <FormHelperText>
                  Initial moon-separation filter when the Best time of year chart opens.
                </FormHelperText>
              </Box>
            </AccordionDetails>
          </Accordion>
        </Stack>
      </Stack>
      </Box>
    </Box>
  );
}


function AstapPathSection() {
  const { settings, update } = useSettingsStore();
  const [browserOpen, setBrowserOpen] = useState(false);
  const [validation, setValidation] = useState<{
    valid: boolean;
    resolved_path: string | null;
    error: string | null;
  } | null>(null);
  const [validating, setValidating] = useState(false);

  const currentPath = settings?.astap_executable_path ?? "";

  const doValidate = useCallback(async (path: string) => {
    if (!path) {
      setValidation(null);
      return;
    }
    setValidating(true);
    try {
      const result = await validateAstapPath(path);
      setValidation(result);
      if (result.valid && result.resolved_path && result.resolved_path !== path) {
        update({ astap_executable_path: result.resolved_path });
      }
    } catch {
      setValidation({ valid: false, resolved_path: null, error: "Validation failed" });
    } finally {
      setValidating(false);
    }
  }, [update]);

  useEffect(() => {
    if (currentPath) doValidate(currentPath);
  }, []);

  const handleBrowseSelect = useCallback(
    (path: string) => {
      update({ astap_executable_path: path });
      doValidate(path);
      setBrowserOpen(false);
    },
    [update, doValidate],
  );

  return (
    <>
      <Accordion variant="outlined" disableGutters defaultExpanded={false}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography variant="body2" color="text.secondary" sx={sectionHeaderSx}>
            Plate Solving
          </Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Typography variant="body1" gutterBottom>ASTAP Executable</Typography>
          <Stack direction="row" spacing={1} alignItems="center">
            <TextField
              size="small"
              fullWidth
              placeholder="Not configured"
              value={currentPath}
              onChange={(e) => {
                update({ astap_executable_path: e.target.value || null });
                setValidation(null);
              }}
              onBlur={() => { if (currentPath) doValidate(currentPath); }}
              inputProps={{ style: { fontFamily: monoFontFamily, fontSize: "0.75rem" } }}
            />
            <Button
              variant="outlined"
              size="small"
              onClick={() => setBrowserOpen(true)}
              startIcon={<FolderOpenIcon sx={{ fontSize: 16 }} />}
              sx={{ height: 32, whiteSpace: "nowrap" }}
            >
              Browse
            </Button>
            {!validating && validation?.valid && (
              <CheckCircleIcon color="primary" fontSize="small" />
            )}
            {!validating && validation && !validation.valid && (
              <ErrorIcon color="warning" fontSize="small" />
            )}
          </Stack>
          {validation && !validation.valid && validation.error && (
            <FormHelperText error>{validation.error}</FormHelperText>
          )}
          <FormHelperText>
            Path to the ASTAP executable. On macOS you can select the .app bundle — the binary
            inside will be resolved automatically.
          </FormHelperText>
        </AccordionDetails>
      </Accordion>

      <FileBrowser
        open={browserOpen}
        onClose={() => setBrowserOpen(false)}
        onSelect={handleBrowseSelect}
        activePath={currentPath || undefined}
        accept={["*"]}
        title="Select ASTAP Executable"
        emptyMessage="No files here"
      />
    </>
  );
}
