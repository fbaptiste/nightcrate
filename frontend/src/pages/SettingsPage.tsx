import Box from "@mui/material/Box";
import Divider from "@mui/material/Divider";
import FormControl from "@mui/material/FormControl";
import FormControlLabel from "@mui/material/FormControlLabel";
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
    <Box sx={{ p: 4, maxWidth: 480 }}>
      <Typography variant="h5" fontWeight={600} gutterBottom>Settings</Typography>
      <Divider sx={{ mb: 3 }} />

      {/* Theme */}
      <FormControl fullWidth size="small" sx={{ mb: 3 }}>
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

      <Divider sx={{ mb: 3 }} />

      {/* GPU acceleration */}
      <Box sx={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", mb: 3 }}>
        <Box>
          <Typography variant="body1">GPU Acceleration</Typography>
          <Typography variant="body2" color="text.secondary">
            Use GPU acceleration (Apple Metal / NVIDIA CUDA) when available
          </Typography>
        </Box>
        <FormControlLabel
          control={
            <Switch
              checked={settings.gpu_acceleration}
              onChange={(e) => update({ gpu_acceleration: e.target.checked })}
            />
          }
          label=""
        />
      </Box>

      <Divider sx={{ mb: 3 }} />

      {/* Worker cores */}
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
    </Box>
  );
}
