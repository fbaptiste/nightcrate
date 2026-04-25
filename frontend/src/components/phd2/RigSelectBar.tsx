/**
 * Rig picker for the PHD2 Analyzer page. Selection persists per-log
 * via phd2RecentFiles; "No rig" is a first-class option that falls
 * back to the heuristic worm-marker.
 */
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Select, { type SelectChangeEvent } from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useQuery } from "@tanstack/react-query";

import { fetchRigs, type Rig } from "@/api/rigs";

interface Props {
  rigId: number | null;
  onChange: (rigId: number | null) => void;
}

const NONE_VALUE = "__none__";

export default function RigSelectBar({ rigId, onChange }: Props) {
  const { data: rigs, isLoading } = useQuery<Rig[]>({
    queryKey: ["rigs", "phd2-rig-select"],
    queryFn: () => fetchRigs(true),
  });

  const handleChange = (event: SelectChangeEvent<string>) => {
    const value = event.target.value;
    onChange(value === NONE_VALUE ? null : Number(value));
  };

  if (isLoading) {
    return (
      <Typography variant="caption" color="text.secondary">
        Loading rigs…
      </Typography>
    );
  }

  if ((rigs?.length ?? 0) === 0) {
    return (
      <Typography variant="caption" color="text.secondary">
        Build a rig on the Rigs page to enable rig-aware spectrum
        markers.
      </Typography>
    );
  }

  // A rig deleted since selection shouldn't crash the select — fall
  // back to "No rig" visually while leaving the stored id alone.
  const selectableValue =
    rigId !== null && rigs!.some((r) => r.id === rigId)
      ? String(rigId)
      : NONE_VALUE;

  return (
    <Stack direction="row" spacing={1} alignItems="center">
      <FormControl size="small" sx={{ minWidth: 220 }}>
        <InputLabel id="phd2-rig-select-label">Rig</InputLabel>
        <Select
          labelId="phd2-rig-select-label"
          label="Rig"
          value={selectableValue}
          onChange={handleChange}
          sx={{ "& .MuiSelect-select": { py: 0.5, fontSize: 13 } }}
        >
          <MenuItem value={NONE_VALUE}>
            <Typography variant="body2" color="text.secondary">
              No rig
            </Typography>
          </MenuItem>
          {rigs!.map((rig) => (
            <MenuItem key={rig.id} value={String(rig.id)}>
              <Stack>
                <Typography variant="body2">{rig.name}</Typography>
                <Typography variant="caption" color="text.secondary">
                  {rig.telescope_name} · {rig.camera_name}
                </Typography>
              </Stack>
            </MenuItem>
          ))}
        </Select>
      </FormControl>
    </Stack>
  );
}
