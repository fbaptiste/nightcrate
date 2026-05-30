import { useMemo } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import Autocomplete from "@mui/material/Autocomplete";
import Box from "@mui/material/Box";
import TextField from "@mui/material/TextField";
import { type Location, fetchLocations } from "@/api/locations";
import { fetchRigs } from "@/api/rigs";
import { type Project, setProjectRigs, updateProject } from "@/api/projects";

interface Props {
  project: Project;
  onUpdated: (p: Project) => void;
}

export default function ProjectMetadataSection({ project, onUpdated }: Props) {
  const { data: locations = [] } = useQuery({
    queryKey: ["locations"],
    queryFn: fetchLocations,
  });
  const { data: rigs = [] } = useQuery({ queryKey: ["rigs"], queryFn: () => fetchRigs(true) });

  const locationMut = useMutation({
    mutationFn: (locationId: number | null) =>
      updateProject(project.id, { location_id: locationId }),
    onSuccess: onUpdated,
  });
  const rigsMut = useMutation({
    mutationFn: (rigIds: number[]) => setProjectRigs(project.id, rigIds),
    onSuccess: onUpdated,
  });

  // fetchLocations returns active locations only. If the project's location was
  // later retired, keep it in the options so the association stays visible.
  const locationOptions = useMemo(() => {
    if (project.location_id != null && !locations.some((l) => l.id === project.location_id)) {
      return [
        ...locations,
        {
          id: project.location_id,
          name: `${project.location_name ?? "Unknown"} (retired)`,
        } as unknown as Location,
      ];
    }
    return locations;
  }, [locations, project.location_id, project.location_name]);

  const selectedLocation = locationOptions.find((l) => l.id === project.location_id) ?? null;
  const selectedRigs = rigs.filter((r) => project.rigs.some((pr) => pr.id === r.id));

  return (
    <Box sx={{ display: "flex", flexWrap: "wrap", gap: 2, alignItems: "flex-start" }}>
      <Autocomplete
        sx={{ minWidth: 220, flex: "0 1 260px" }}
        size="small"
        options={locationOptions}
        value={selectedLocation}
        onChange={(_e, v) => locationMut.mutate(v?.id ?? null)}
        getOptionLabel={(l) => l.name}
        isOptionEqualToValue={(o, v) => o.id === v.id}
        renderInput={(params) => (
          <TextField
            {...params}
            label="Location"
            placeholder="Set location"
            inputProps={{ ...params.inputProps, readOnly: true }}
          />
        )}
      />

      <Autocomplete
        multiple
        sx={{ minWidth: 220, flex: "0 1 260px" }}
        size="small"
        options={rigs}
        value={selectedRigs}
        onChange={(_e, vals) => rigsMut.mutate(vals.map((r) => r.id))}
        getOptionLabel={(r) => r.name}
        isOptionEqualToValue={(o, v) => o.id === v.id}
        // Smaller chips so the multi-select doesn't sit taller than the
        // single-select Location next to it.
        ChipProps={{ size: "small", sx: { height: 22 } }}
        renderInput={(params) => (
          <TextField
            {...params}
            label="Rigs"
            placeholder={selectedRigs.length === 0 ? "Add rigs" : undefined}
            inputProps={{ ...params.inputProps, readOnly: true }}
          />
        )}
      />
    </Box>
  );
}
