import Box from "@mui/material/Box";
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
import { useSettingsStore } from "@/stores/settingsStore";

export function SettingsPage() {
  const { settings, update } = useSettingsStore();

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
      </Box>
    </Box>
  );
}
