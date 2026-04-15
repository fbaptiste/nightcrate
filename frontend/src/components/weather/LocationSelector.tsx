import { useQuery } from "@tanstack/react-query";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import { fetchLocations, type Location } from "../../api/locations";

interface LocationSelectorProps {
  selectedId: number | null;
  onChange: (locationId: number) => void;
}

export default function LocationSelector({
  selectedId,
  onChange,
}: LocationSelectorProps) {
  const { data: locations = [] } = useQuery<Location[]>({
    queryKey: ["locations"],
    queryFn: fetchLocations,
  });

  const defaultLoc = locations.find((l) => l.is_default);
  const effectiveId =
    selectedId ?? defaultLoc?.id ?? locations[0]?.id ?? "";

  return (
    <FormControl size="small" sx={{ minWidth: 220 }}>
      <InputLabel id="location-select-label">Location</InputLabel>
      <Select
        labelId="location-select-label"
        label="Location"
        value={effectiveId}
        onChange={(e) => onChange(e.target.value as number)}
      >
        {locations.map((loc) => (
          <MenuItem key={loc.id} value={loc.id}>
            {loc.name}
            {loc.is_default ? " (default)" : ""}
          </MenuItem>
        ))}
      </Select>
    </FormControl>
  );
}
