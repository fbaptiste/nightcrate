import Box from "@mui/material/Box";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Slider from "@mui/material/Slider";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import type { AberrationMetric, StarFilters } from "@/api/aberration";
import { monoFontFamily } from "@/theme/theme";

const METRIC_OPTIONS: { value: AberrationMetric; label: string }[] = [
  { value: "eccentricity", label: "Eccentricity" },
  { value: "fwhm", label: "FWHM" },
  { value: "hfr", label: "HFR" },
];

function FilterSlider({ label, value, min, max, step, tooltip, onChange }: {
  label: string; value: number; min: number; max: number; step: number;
  tooltip?: string; onChange: (v: number) => void;
}) {
  const labelEl = (
    <Typography sx={{ fontSize: "0.6rem", color: "text.secondary", whiteSpace: "nowrap", cursor: tooltip ? "help" : "default" }}>
      {label}
    </Typography>
  );
  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 1, minWidth: 130 }}>
      {tooltip ? <Tooltip title={tooltip} arrow><span>{labelEl}</span></Tooltip> : labelEl}
      <Slider
        min={min} max={max} step={step}
        value={value}
        onChange={(_, v) => onChange(v as number)}
        size="small"
        valueLabelDisplay="off"
        sx={{ flex: 1 }}
      />
      <Typography sx={{ fontSize: "0.6rem", fontFamily: monoFontFamily, minWidth: 20, textAlign: "right" }}>
        {value}
      </Typography>
    </Box>
  );
}

interface Props {
  samplesAcross: number;
  onSamplesChange: (n: number) => void;
  metric: AberrationMetric;
  onMetricChange: (m: AberrationMetric) => void;
  filters: StarFilters;
  onFiltersChange: (f: StarFilters) => void;
  analyzing: boolean;
}

export function AberrationToolbar({
  samplesAcross, onSamplesChange, metric, onMetricChange, filters, onFiltersChange, analyzing,
}: Props) {
  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 2, px: 2, py: 1, borderBottom: 1, borderColor: "divider", flexWrap: "wrap" }}>
      {/* Samples slider */}
      <FilterSlider
        label="Samples" value={samplesAcross} min={3} max={9} step={1}
        onChange={onSamplesChange}
      />

      {/* Metric selector */}
      <FormControl size="small" sx={{ minWidth: 120 }}>
        <InputLabel sx={{ fontSize: "0.75rem" }}>Metric</InputLabel>
        <Select
          label="Metric"
          value={metric}
          onChange={(e) => onMetricChange(e.target.value as AberrationMetric)}
          sx={{ fontSize: "0.75rem" }}
        >
          {METRIC_OPTIONS.map((opt) => (
            <MenuItem key={opt.value} value={opt.value} sx={{ fontSize: "0.75rem" }}>
              {opt.label}
            </MenuItem>
          ))}
        </Select>
      </FormControl>

      {/* Star filter sliders */}
      <FilterSlider
        label="Min SNR" value={filters.minSnr} min={3} max={500} step={5}
        tooltip="Minimum signal-to-noise ratio — higher values keep only brighter, more reliable stars"
        onChange={(v) => onFiltersChange({ ...filters, minSnr: v })}
      />
      <FilterSlider
        label="Min FWHM" value={filters.minFwhm} min={1} max={10} step={0.5}
        tooltip="Minimum star width in pixels — raise to filter out hot pixels and noise spikes"
        onChange={(v) => onFiltersChange({ ...filters, minFwhm: v })}
      />
      <FilterSlider
        label="Max FWHM" value={filters.maxFwhm} min={10} max={50} step={1}
        tooltip="Maximum star width in pixels — lower to exclude extended objects and large defocused stars"
        onChange={(v) => onFiltersChange({ ...filters, maxFwhm: v })}
      />

      {analyzing && (
        <Box sx={{ fontSize: "0.65rem", color: "text.secondary" }}>Analyzing…</Box>
      )}
    </Box>
  );
}
