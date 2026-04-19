import { useEffect } from "react";
import { Link as RouterLink } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import Link from "@mui/material/Link";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import { fetchLocations, type Location } from "@/api/locations";
import { useCalculatorsStore } from "@/stores/calculatorsStore";

/**
 * Shared header strip for location-aware calculators. Defaults to the user's
 * default location; stores the active selection in the calculators Zustand
 * slice so it persists across calculator switches within the page session.
 */
export default function CalculatorLocationBar() {
  const selectedId = useCalculatorsStore((s) => s.selectedLocationId);
  const setSelectedId = useCalculatorsStore((s) => s.setSelectedLocationId);

  const { data: locations = [] } = useQuery<Location[]>({
    queryKey: ["locations"],
    queryFn: fetchLocations,
  });

  const defaultLocation = locations.find((l) => l.is_default);

  useEffect(() => {
    if (selectedId === null && defaultLocation) {
      setSelectedId(defaultLocation.id);
    }
  }, [selectedId, defaultLocation, setSelectedId]);

  if (locations.length === 0) {
    return (
      <Alert severity="info" sx={{ mb: 2 }}>
        <Link component={RouterLink} to="/locations">
          Add a Location
        </Link>
        {" first — the location-aware calculators need lat/lon/elevation."}
      </Alert>
    );
  }

  if (selectedId === null && !defaultLocation) {
    return (
      <Alert severity="info" sx={{ mb: 2 }}>
        {"No default location set. "}
        <Link component={RouterLink} to="/locations">
          Set one here
        </Link>
        {" or pick one below."}
        <Box sx={{ mt: 1, maxWidth: 320 }}>
          <LocationSelect
            locations={locations}
            value={null}
            onChange={setSelectedId}
          />
        </Box>
      </Alert>
    );
  }

  return (
    <Box sx={{ mb: 2, maxWidth: 360 }}>
      <LocationSelect
        locations={locations}
        value={selectedId}
        onChange={setSelectedId}
      />
    </Box>
  );
}

function LocationSelect({
  locations,
  value,
  onChange,
}: {
  locations: Location[];
  value: number | null;
  onChange: (id: number) => void;
}) {
  return (
    <FormControl size="small" fullWidth>
      <InputLabel id="calc-location-label">Location</InputLabel>
      <Select
        labelId="calc-location-label"
        label="Location"
        value={value ?? ""}
        onChange={(e) => onChange(Number(e.target.value))}
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

/** Hook helper for calculator components that need the active location. */
export function useCalculatorLocation() {
  const selectedId = useCalculatorsStore((s) => s.selectedLocationId);
  const { data: locations = [] } = useQuery<Location[]>({
    queryKey: ["locations"],
    queryFn: fetchLocations,
  });
  return {
    locationId: selectedId,
    location: locations.find((l) => l.id === selectedId) ?? null,
    allLocations: locations,
  };
}
