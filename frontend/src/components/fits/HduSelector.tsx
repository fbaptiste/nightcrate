import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import type { HduInfo } from "@/api/fits";

interface Props {
  hdus: HduInfo[];
  selected: number;
  onChange: (index: number) => void;
}

export function HduSelector({ hdus, selected, onChange }: Props) {
  return (
    <FormControl size="small" sx={{ minWidth: 220 }}>
      <InputLabel id="hdu-label">HDU</InputLabel>
      <Select
        labelId="hdu-label"
        label="HDU"
        value={selected}
        onChange={(e) => onChange(Number(e.target.value))}
      >
        {hdus.map((h) => (
          <MenuItem key={h.index} value={h.index}>
            {h.index}: {h.name} ({h.type}){h.has_image ? " — image" : ""}
          </MenuItem>
        ))}
      </Select>
    </FormControl>
  );
}
