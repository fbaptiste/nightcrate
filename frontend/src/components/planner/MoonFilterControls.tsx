import Checkbox from "@mui/material/Checkbox";
import FormControl from "@mui/material/FormControl";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";

interface Props {
  enabled: boolean;
  onEnabledChange: (v: boolean) => void;
  maxIllumination: number;
  onMaxIlluminationChange: (v: number) => void;
  minSeparation: number;
  onMinSeparationChange: (v: number) => void;
  moonCombine: "and" | "or";
  onMoonCombineChange: (v: "and" | "or") => void;
}

const selectSx = { fontSize: "0.8rem", mt: "-1px" };

export default function MoonFilterControls({
  enabled,
  onEnabledChange,
  maxIllumination,
  onMaxIlluminationChange,
  minSeparation,
  onMinSeparationChange,
  moonCombine,
  onMoonCombineChange,
}: Props) {
  const color = enabled ? "text.primary" : "text.disabled";
  return (
    <Stack
      direction="row"
      alignItems="center"
      gap={1.5}
      flexWrap="wrap"
      sx={{ mt: 1 }}
    >
      <Stack direction="row" alignItems="center" gap={0.5}>
        <Checkbox
          size="small"
          checked={enabled}
          onChange={(_, checked) => onEnabledChange(checked)}
          sx={{ p: 0.25 }}
        />
        <Typography variant="caption" sx={{ color }}>
          Illumination {"≤"}
        </Typography>
        <FormControl
          size="small"
          variant="standard"
          sx={{ minWidth: 56 }}
          disabled={!enabled}
        >
          <Select
            value={maxIllumination}
            onChange={(e) => onMaxIlluminationChange(Number(e.target.value))}
            sx={selectSx}
          >
            {[0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100].map((v) => (
              <MenuItem key={v} value={v}>{v}%</MenuItem>
            ))}
          </Select>
        </FormControl>
      </Stack>

      <ToggleButtonGroup
        size="small"
        exclusive
        value={moonCombine}
        onChange={(_, v) => { if (v) onMoonCombineChange(v); }}
        disabled={!enabled}
        sx={{
          "& .MuiToggleButton-root": {
            textTransform: "none",
            fontSize: "0.7rem",
            px: 1,
            py: 0.125,
            lineHeight: 1.4,
          },
        }}
      >
        <ToggleButton value="and">AND</ToggleButton>
        <ToggleButton value="or">OR</ToggleButton>
      </ToggleButtonGroup>

      <Stack direction="row" alignItems="center" gap={0.5}>
        <Typography variant="caption" sx={{ color }}>
          Separation {"≥"}
        </Typography>
        <FormControl
          size="small"
          variant="standard"
          sx={{ minWidth: 56 }}
          disabled={!enabled}
        >
          <Select
            value={minSeparation}
            onChange={(e) => onMinSeparationChange(Number(e.target.value))}
            sx={selectSx}
          >
            {[0, 15, 30, 45, 60, 75, 90, 120].map((v) => (
              <MenuItem key={v} value={v}>{v}°</MenuItem>
            ))}
          </Select>
        </FormControl>
      </Stack>
    </Stack>
  );
}
